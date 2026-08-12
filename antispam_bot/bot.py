"""Bot chống spam Telegram - hoạt động im lặng.

Nguyên tắc: bot không bao giờ nhắn gì trong nhóm. Tin spam bị xoá, người gửi
bị xử lý, và toàn bộ dấu vết chỉ xuất hiện ở LOG_CHAT_ID (nếu có cấu hình).
Lệnh quản trị cũng tự xoá sau vài giây để nhóm luôn sạch.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time
from datetime import datetime, timedelta, timezone

from telegram import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    Chat,
    ChatPermissions,
    Message,
    MessageEntity,
    Update,
)
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest, Conflict, Forbidden, NetworkError, TelegramError
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import ocr, presets, qrscan
from .config import Config
from .detector import MessageFacts, Verdict, analyse
from .normalize import looks_like_question, normalize, squeeze
from .storage import GLOBAL, Storage

log = logging.getLogger("antispam")

ADMIN_CACHE_TTL = 300  # giây
RULES_CACHE_TTL = 60   # giây - lệnh admin xoá cache ngay nên đây chỉ là lưới an toàn
SELF_DESTRUCT = 20     # giây - thời gian sống của phản hồi lệnh quản trị

MUTED = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------


def _cfg(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["cfg"]


def _db(context: ContextTypes.DEFAULT_TYPE) -> Storage:
    return context.application.bot_data["db"]


def _write_scope(update: Update) -> int | None:
    """Phạm vi ghi cho các lệnh add/del.

    Gõ trong nhóm  → chỉ nhóm đó.
    Nhắn riêng bot → GLOBAL, áp dụng cho MỌI nhóm (kể cả nhóm thêm sau này).
    """
    msg = update.effective_message
    if msg is None:
        return None
    return GLOBAL if msg.chat.type == ChatType.PRIVATE else msg.chat_id


async def _bot_admin_ids(context: ContextTypes.DEFAULT_TYPE) -> set[int]:
    """Bot admin (toàn cục). Cache vì được hỏi trên mọi tin nhắn."""
    bd = context.application.bot_data
    hit = bd.get("bot_admin_cache")
    now = time.monotonic()
    if hit and now - hit[0] < RULES_CACHE_TTL:
        return hit[1]
    ids = set(await _db(context).get_bot_admins())
    bd["bot_admin_cache"] = (now, ids)
    return ids


class ChatRules:
    """Toàn bộ danh sách của một nhóm, gom sẵn để không phải hỏi DB mỗi tin.

    Từ cấm được chuẩn hoá TRƯỚC và lưu lại: chuẩn hoá lại 70 cụm cho từng tin
    nhắn tốn ~1.2ms, còn so khớp trên bản đã chuẩn hoá chỉ mất ~30µs.
    """

    __slots__ = ("cfg", "keywords", "seeding", "blocked", "at_ok")

    def __init__(self, cfg: Config, keywords, seeding, blocked, at_ok):
        self.cfg = cfg
        self.keywords = keywords  # [(gốc, đã normalize, đã squeeze)]
        self.seeding = seeding
        self.blocked = blocked
        self.at_ok = at_ok


def _invalidate_rules(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xoá cache sau khi admin sửa danh sách, để lệnh có hiệu lực ngay."""
    context.application.bot_data.get("rules_cache", {}).clear()
    context.application.bot_data.pop("bot_admin_cache", None)


async def _chat_rules(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> ChatRules:
    cache: dict[int, tuple[float, ChatRules]] = context.application.bot_data.setdefault(
        "rules_cache", {}
    )
    hit = cache.get(chat_id)
    now = time.monotonic()
    if hit and now - hit[0] < RULES_CACHE_TTL:
        return hit[1]

    cfg = _cfg(context)
    db = _db(context)

    ats = await db.get_usernames(chat_id)
    ats |= await _admin_usernames(chat_id, context)
    if context.bot.username:
        ats.add(context.bot.username.lower())

    eff = Config(**{
        **cfg.__dict__,
        "whitelist_domains": cfg.whitelist_domains | await db.get_whitelist(chat_id),
        "allowed_usernames": cfg.allowed_usernames | ats,
    })
    rules = ChatRules(
        cfg=eff,
        keywords=[(k, normalize(k), squeeze(k)) for k in await db.get_keywords_effective(chat_id)],
        seeding=set(await db.get_fwd_whitelist(chat_id)) | set(await db.get_fwd_whitelist(GLOBAL)),
        blocked=set(await db.get_blacklist(chat_id)) | set(await db.get_blacklist(GLOBAL)),
        at_ok=ats,
    )
    cache[chat_id] = (now, rules)
    return rules


async def _service_kinds_for(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    """Loại tin dịch vụ cần xoá ở nhóm này.

    Ưu tiên: cài riêng nhóm → cài chung (/services từ chat riêng) → file .env.
    """
    db = _db(context)
    for key in (f"svc:{chat_id}", f"svc:{GLOBAL}"):
        raw = await db.get_setting(key)
        if raw is not None:
            return {k for k in raw.split(",") if k}
    return _cfg(context).delete_service


async def _drop_group(chat_id: int, context: ContextTypes.DEFAULT_TYPE, ly_do: str) -> None:
    """Bỏ một nhóm khỏi danh sách quản lý và dọn cache liên quan.

    Gọi khi bot bị kick/đuổi. Không dọn thì mỗi lần /status hay kiểm tra quyền
    lại đâm vào nhóm không còn vào được, sinh cảnh báo rác không dứt.
    Dữ liệu của nhóm (từ cấm, seeding...) vẫn giữ nguyên trong DB, thêm bot
    vào lại là dùng tiếp được.
    """
    db = _db(context)
    groups = await _managed_groups(context)
    if chat_id not in groups:
        return
    groups.remove(chat_id)
    await db.set_setting("home_group", ",".join(str(g) for g in groups))
    context.application.bot_data.get("rules_cache", {}).pop(chat_id, None)
    context.application.bot_data.get("admin_cache", {}).pop(chat_id, None)
    context.application.bot_data.setdefault("rights_warned", set()).discard(chat_id)
    log.info(
        "Đã bỏ nhóm %s khỏi danh sách quản lý (%s). Còn %d nhóm. "
        "Thêm bot vào lại là nhóm tự quay lại danh sách.",
        chat_id, ly_do, len(groups),
    )


async def _managed_groups(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    """Danh sách nhóm đã đăng ký bằng /setgroup."""
    raw = await _db(context).get_setting("home_group")
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return out


async def _target_chat_ids(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    """Nhóm cụ thể để thao tác (dùng cho /unban, /trust, /status).

    Trong nhóm → chính nhóm đó. Nhắn riêng → mọi nhóm đã đăng ký.
    """
    msg = update.effective_message
    if msg is None:
        return []
    if msg.chat.type != ChatType.PRIVATE:
        return [msg.chat_id]
    return await _managed_groups(context)


async def _fetch_admins(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[set[int], set[str]]:
    """(id admin, @username admin) của nhóm. Cache 5 phút để đỡ gọi API."""
    cache: dict[int, tuple[float, set[int], set[str]]] = context.application.bot_data.setdefault(
        "admin_cache", {}
    )
    hit = cache.get(chat_id)
    now = time.monotonic()
    if hit and now - hit[0] < ADMIN_CACHE_TTL:
        return hit[1], hit[2]
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        ids = {a.user.id for a in admins}
        names = {a.user.username.lower() for a in admins if a.user.username}
    except Forbidden as exc:
        await _drop_group(chat_id, context, str(exc))
        ids, names = set(), set()
    except TelegramError as exc:
        log.warning("Không lấy được danh sách admin của %s: %s", chat_id, exc)
        ids = hit[1] if hit else set()
        names = hit[2] if hit else set()
    cache[chat_id] = (now, ids, names)
    return ids, names


async def _admin_ids(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> set[int]:
    ids, _ = await _fetch_admins(chat_id, context)
    return ids


async def _admin_usernames(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    _, names = await _fetch_admins(chat_id, context)
    return names


async def _bot_rights(
    chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> tuple[bool, bool, bool, bool]:
    """(là admin, xoá được tin, cấm được người, đang ẩn danh) của bot trong nhóm."""
    try:
        me = await context.bot.get_chat_member(chat_id, context.bot.id)
    except Forbidden as exc:
        # Bot đã bị kick/đuổi. Đây là chuyện bình thường, không phải sự cố:
        # dọn nhóm khỏi danh sách rồi im, thay vì cảnh báo mỗi lần gọi.
        await _drop_group(chat_id, context, str(exc))
        return False, False, False, False
    except TelegramError as exc:
        log.warning("Không kiểm tra được quyền của bot trong %s: %s", chat_id, exc)
        return False, False, False, False
    is_admin = me.status == ChatMemberStatus.ADMINISTRATOR
    return (
        is_admin,
        bool(getattr(me, "can_delete_messages", False)),
        bool(getattr(me, "can_restrict_members", False)),
        bool(getattr(me, "is_anonymous", False)),
    )


async def _warn_if_crippled(chat: Chat, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cảnh báo một lần mỗi nhóm nếu bot thiếu quyền để làm việc.

    Không có quyền thì bot im lặng theo đúng nghĩa đen - không xoá, không ban được gì.
    Đây là nguyên nhân phổ biến nhất của 'bot chạy mà không thấy tác dụng'.
    """
    warned: set[int] = context.application.bot_data.setdefault("rights_warned", set())
    if chat.id in warned:
        return
    warned.add(chat.id)

    is_admin, can_delete, can_restrict, anon = await _bot_rights(chat.id, context)
    cfg = _cfg(context)
    if not is_admin:
        log.error(
            "Nhóm %r (%s): bot KHÔNG phải admin nên không xoá/ban được gì. "
            "Vào phần quản lý nhóm, cấp quyền admin cho bot.",
            chat.title or chat.id, chat.id,
        )
        return
    missing = []
    if not can_delete:
        missing.append("Delete messages (xoá tin nhắn)")
    if not can_restrict and cfg.action in ("ban", "mute"):
        missing.append("Ban users (cấm thành viên)")
    if missing:
        log.error(
            "Nhóm %r (%s): bot là admin nhưng THIẾU quyền: %s. Bật thêm trong phần "
            "chỉnh quyền admin của bot.",
            chat.title or chat.id, chat.id, "; ".join(missing),
        )
    else:
        log.info("Nhóm %r (%s): bot có đủ quyền.", chat.title or chat.id, chat.id)

    # Ẩn danh chỉ là tuỳ chọn thẩm mỹ, không ảnh hưởng khả năng chặn spam.
    # Không cảnh báo, chỉ ghi nhận - ai cần thì gõ /anon để xem.
    log.debug("Nhóm %s: bot ẩn danh = %s", chat.id, anon)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot được thêm vào nhóm / đổi quyền: báo ngay tình trạng quyền hạn."""
    upd = update.my_chat_member
    if upd is None or upd.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if upd.new_chat_member.user.id != context.bot.id:
        return

    chat = upd.chat
    status = upd.new_chat_member.status
    if status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        log.info("Bot đã rời/bị đuổi khỏi nhóm %r (%s)", chat.title or chat.id, chat.id)
        await _drop_group(chat.id, context, "bị kick khỏi nhóm")
        return

    # Quyền vừa đổi -> kiểm tra lại từ đầu.
    context.application.bot_data.setdefault("rights_warned", set()).discard(chat.id)
    context.application.bot_data.setdefault("admin_cache", {}).pop(chat.id, None)
    log.info("Bot được thêm/cập nhật quyền ở nhóm %r (%s)", chat.title or chat.id, chat.id)
    await _warn_if_crippled(chat, context)

    # Tự thêm vào danh sách nhóm quản lý để owner thao tác được từ chat riêng ngay.
    if status == ChatMemberStatus.ADMINISTRATOR:
        db = _db(context)
        groups = await _managed_groups(context)
        if chat.id not in groups:
            groups.append(chat.id)
            await db.set_setting("home_group", ",".join(str(g) for g in groups))
            log.info("Đã thêm nhóm %s (%r) vào danh sách quản lý", chat.id, chat.title or chat.id)


async def _is_exempt(msg: Message, context: ContextTypes.DEFAULT_TYPE) -> bool:
    cfg = _cfg(context)
    user = msg.from_user
    chat = msg.chat

    # Bài đăng của kênh tự động chuyển sang nhóm thảo luận liên kết.
    if msg.is_automatic_forward:
        return True
    # Admin ẩn danh gửi dưới tên nhóm.
    if msg.sender_chat and msg.sender_chat.id == chat.id:
        return True
    # Kênh liên kết của chính nhóm này.
    if msg.sender_chat and chat.linked_chat_id and msg.sender_chat.id == chat.linked_chat_id:
        return True
    # Tin gửi dưới danh nghĩa một kênh lạ: from_user là "Channel_Bot" giả,
    # nên phải xét trước khi loại trừ bot.
    if msg.sender_chat is not None:
        return False
    if user is None:
        return False
    if user.is_bot:
        return True
    if user.id in cfg.owner_ids:
        return True
    # Bot admin do owner chỉ định (nick thật) — không quét tin của họ.
    if user.id in await _bot_admin_ids(context):
        return True
    if user.id in await _admin_ids(chat.id, context):
        return True
    return False


def _extract_facts(
    msg: Message,
    is_new: bool,
    offences: int,
    has_qr: bool = False,
    qr_payloads: list[str] | None = None,
    fwd_exempt: bool = False,
    ocr_text: str = "",
    is_question: bool = False,
) -> MessageFacts:
    text = " ".join(p for p in (msg.text, msg.caption) if p)

    urls: list[str] = []
    mentions: list[str] = []
    for getter, ents in (
        (msg.parse_entities, msg.entities),
        (msg.parse_caption_entities, msg.caption_entities),
    ):
        if not ents:
            continue
        parsed = getter([MessageEntity.URL, MessageEntity.TEXT_LINK, MessageEntity.MENTION])
        for ent, value in parsed.items():
            if ent.type == MessageEntity.TEXT_LINK and ent.url:
                urls.append(ent.url)
            elif ent.type == MessageEntity.URL:
                urls.append(value)
            elif ent.type == MessageEntity.MENTION:
                mentions.append(value)

    origin = msg.forward_origin
    label = None
    if origin is not None:
        label = {
            "user": "người dùng",
            "hidden_user": "người dùng ẩn danh",
            "chat": "nhóm khác",
            "channel": "kênh khác",
        }.get(getattr(origin, "type", ""), "nguồn khác")

    user = msg.from_user
    return MessageFacts(
        text=text,
        entity_urls=urls,
        mentions=mentions,
        is_forward=origin is not None and not fwd_exempt,
        forward_label=label,
        via_bot=msg.via_bot is not None,
        from_channel=msg.sender_chat is not None,
        has_buttons=msg.reply_markup is not None,
        has_media=bool(msg.photo or msg.video or msg.document or msg.animation),
        is_new_member=is_new,
        has_username=bool(user and user.username),
        prior_offences=offences,
        has_qr=has_qr,
        qr_payloads=qr_payloads or [],
        ocr_text=ocr_text,
        is_question=is_question,
    )


def _image_ref(msg: Message, max_bytes: int) -> tuple[str, str] | None:
    """(file_id, file_unique_id) của ảnh trong tin, nếu có và đủ nhỏ để tải về.

    file_unique_id giữ nguyên với cùng một ảnh, kể cả do người khác gửi lại -
    dùng làm khoá nhớ kết quả OCR.
    """
    if msg.photo:
        # photo là danh sách nhiều kích cỡ; lấy bản lớn nhất còn nằm dưới hạn mức
        # vì QR càng nhiều pixel càng dễ giải.
        usable = [p for p in msg.photo if (p.file_size or 0) <= max_bytes]
        if usable:
            best = max(usable, key=lambda p: (p.width or 0) * (p.height or 0))
            return best.file_id, best.file_unique_id
        return None

    doc = msg.document
    if doc and (doc.mime_type or "").startswith("image/") and (doc.file_size or 0) <= max_bytes:
        return doc.file_id, doc.file_unique_id

    sticker = msg.sticker
    if sticker and not sticker.is_animated and not sticker.is_video:
        if (sticker.file_size or 0) <= max_bytes:
            return sticker.file_id, sticker.file_unique_id
    return None


async def _scan_image(
    msg: Message, context: ContextTypes.DEFAULT_TYPE
) -> tuple[bool, list[str], str]:
    """Soi ảnh trong tin nhắn: (có QR, nội dung QR, chữ đọc được trong ảnh).

    Tải ảnh về ĐÚNG MỘT LẦN rồi dùng chung cho cả QR lẫn OCR - trước đây mỗi
    thứ tải riêng là phí băng thông và thời gian.
    """
    cfg = _cfg(context)
    want_qr = cfg.scan_qr and qrscan.AVAILABLE
    want_ocr = cfg.scan_ocr and ocr.AVAILABLE
    if not want_qr and not want_ocr:
        return False, [], ""

    ref = _image_ref(msg, max(cfg.qr_max_bytes, cfg.ocr_max_bytes))
    if ref is None:
        return False, [], ""
    file_id, unique_id = ref

    try:
        tg_file = await context.bot.get_file(file_id)
        data = bytes(await tg_file.download_as_bytearray())
    except TelegramError as exc:
        log.warning("Không tải được ảnh %s: %s", file_id, exc)
        return False, [], ""

    # Chạy SONG SONG: hai việc độc lập nhau, và cả hai đều nằm ở thread riêng
    # (OpenCV thả GIL, tesseract là tiến trình riêng) nên chồng lấn được thật.
    # Đo được: 430ms tuần tự -> 355ms song song.
    async def _qr():
        if want_qr and len(data) <= cfg.qr_max_bytes:
            return await qrscan.decode(data)
        return False, []

    async def _ocr():
        if want_ocr and len(data) <= cfg.ocr_max_bytes:
            return await ocr.read(
                data, key=unique_id, lang=cfg.ocr_lang, max_side=cfg.ocr_max_side
            )
        return ""

    (has_qr, payloads), text = await asyncio.gather(_qr(), _ocr())
    return has_qr, payloads, text


async def _report(
    context: ContextTypes.DEFAULT_TYPE, chat: Chat, msg: Message, verdict, action: str
) -> None:
    """Ghi log ra console và (nếu có) kênh log riêng. Không bao giờ nhắn vào nhóm."""
    user = msg.from_user
    who = f"{user.full_name} (@{user.username})" if user and user.username else (
        user.full_name if user else (msg.sender_chat.title if msg.sender_chat else "?")
    )
    uid = user.id if user else (msg.sender_chat.id if msg.sender_chat else 0)
    excerpt = (msg.text or msg.caption or "<không có chữ>")[:300]

    log.info("[%s] %s | %s (%s) | %s", action.upper(), chat.title or chat.id, who, uid, verdict.summary())

    cfg = _cfg(context)
    if not cfg.log_chat_id:
        return
    body = (
        f"🛡 <b>{html.escape(action.upper())}</b>\n"
        f"Nhóm: {html.escape(chat.title or str(chat.id))} (<code>{chat.id}</code>)\n"
        f"Người gửi: {html.escape(who)} (<code>{uid}</code>)\n"
        f"Điểm: <b>{verdict.score}</b>/{verdict.threshold}\n"
        f"Lý do: {html.escape('; '.join(verdict.reasons))}\n"
        f"Nội dung:\n<pre>{html.escape(excerpt)}</pre>"
    )
    try:
        await context.bot.send_message(
            cfg.log_chat_id, body, parse_mode="HTML", disable_web_page_preview=True
        )
    except TelegramError as exc:
        goi_y = ""
        if "not found" in str(exc).lower():
            goi_y = " — bot chưa được thêm vào chat này (thêm bot vào đó và cấp quyền admin)"
        log.warning("Không gửi được log tới %s: %s%s", cfg.log_chat_id, exc, goi_y)


async def _punish(context: ContextTypes.DEFAULT_TYPE, msg: Message) -> str:
    """Thực thi hình phạt. Trả về hành động thực tế đã làm."""
    cfg = _cfg(context)
    chat_id = msg.chat_id

    # Luôn xoá tin trước - kể cả khi các bước sau thất bại.
    try:
        await msg.delete()
    except (BadRequest, Forbidden) as exc:
        log.warning("Không xoá được tin nhắn %s: %s", msg.message_id, exc)

    if cfg.action == "delete":
        return "delete"

    # Người gửi là một kênh -> chặn cả kênh đó.
    if msg.sender_chat is not None:
        try:
            await context.bot.ban_chat_sender_chat(chat_id, msg.sender_chat.id)
            return "ban"
        except TelegramError as exc:
            log.warning("Không chặn được kênh %s: %s", msg.sender_chat.id, exc)
            return "delete"

    if msg.from_user is None:
        return "delete"
    uid = msg.from_user.id

    try:
        if cfg.action == "ban":
            await context.bot.ban_chat_member(chat_id, uid, revoke_messages=True)
            return "ban"
        if cfg.action == "mute":
            until = datetime.now(timezone.utc) + timedelta(seconds=cfg.mute_seconds)
            await context.bot.restrict_chat_member(chat_id, uid, MUTED, until_date=until)
            return "mute"
    except (BadRequest, Forbidden) as exc:
        log.warning("Không xử lý được user %s trong %s: %s", uid, chat_id, exc)
        return "delete"
    return cfg.action


# ---------------------------------------------------------------------------
# Handler chính
# ---------------------------------------------------------------------------


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    # Chạy một lần cho mỗi nhóm: báo ngay nếu bot thiếu quyền.
    await _warn_if_crippled(chat, context)

    if await _is_exempt(msg, context):
        return

    cfg = _cfg(context)
    db = _db(context)
    rules = await _chat_rules(chat.id, context)

    # Kiểm tra blacklist sớm — ghi đè cả trạng thái "tin cậy".
    sender_id = msg.sender_chat.id if msg.sender_chat else (
        msg.from_user.id if msg.from_user else None
    )
    force_punish = sender_id is not None and sender_id in rules.blocked
    force_reason = "trong danh sách chặn cứng"
    fwd_exempt = False

    is_new = False
    offences = 0
    if msg.sender_chat is None and msg.from_user is not None:
        first_seen, msg_count, trusted = await db.touch_member(chat.id, msg.from_user.id)
        if trusted and not force_punish:
            return
        is_new = (time.time() - first_seen) < cfg.new_member_seconds or msg_count <= 3
        offences = await db.count_offences(chat.id, msg.from_user.id)
        if not force_punish:
            fwd_exempt = msg.from_user.id in rules.seeding

    has_qr, qr_payloads, ocr_text = await _scan_image(msg, context)

    # Người HỎI "nhóm này có lừa đảo không?" là người cẩn thận, không phải spam.
    # Chỉ miễn khi tin nhắn thuần chữ: không link, không ảnh, không QR, không @.
    # Nếu không, kẻ spam chỉ cần thêm dấu ? vào cuối là thoát hết mọi luật.
    plain_text = not (
        msg.photo or msg.video or msg.document or msg.animation or msg.sticker
        or msg.entities or msg.caption_entities or msg.reply_markup or has_qr
    )
    benign_question = plain_text and looks_like_question(msg.text or "")

    # Từ cấm: soi sau khi có QR + OCR để gộp cả chữ nằm trong ảnh.
    if not force_punish and not benign_question and rules.keywords:
        combined = " ".join(filter(None, [msg.text, msg.caption, *qr_payloads, ocr_text]))
        if combined:
            norm_combined = normalize(combined)
            # squeeze bắt cả kiểu viết cách chữ để né lọc: "l ừ a  đ ả o"
            sq_combined = squeeze(combined)
            matched = [
                raw for raw, kn, ks in rules.keywords
                if kn in norm_combined or ks in sq_combined
            ]
            if matched:
                force_punish = True
                force_reason = f"từ bị cấm: {', '.join(sorted(matched)[:3])}"

    facts = _extract_facts(
        msg, is_new, offences, has_qr, qr_payloads, fwd_exempt=fwd_exempt,
        ocr_text=ocr_text, is_question=benign_question,
    )

    if force_punish:
        verdict = Verdict(score=9999, reasons=[force_reason], threshold=1)
    else:
        # rules.cfg đã gộp sẵn whitelist domain + @ của admin nhóm.
        verdict = analyse(facts, rules.cfg)

    if not verdict.is_spam:
        return

    action = "report" if cfg.action == "report" else await _punish(context, msg)
    uid = msg.sender_chat.id if msg.sender_chat else (msg.from_user.id if msg.from_user else 0)
    await db.log_offence(
        chat.id, uid, verdict.score, action, "; ".join(verdict.reasons), msg.text or msg.caption or ""
    )
    await _report(context, chat, msg, verdict, action)


# Tin nhắn dịch vụ: thuộc tính trên Message ứng với từng nhóm.
SERVICE_FIELDS: dict[str, tuple[str, ...]] = {
    "join": ("new_chat_members",),
    "leave": ("left_chat_member",),
    "pin": ("pinned_message",),
    "title": ("new_chat_title",),
    "photo": ("new_chat_photo", "delete_chat_photo"),
    "videochat": (
        "video_chat_started",
        "video_chat_ended",
        "video_chat_scheduled",
        "video_chat_participants_invited",
    ),
    "forum": (
        "forum_topic_created",
        "forum_topic_edited",
        "forum_topic_closed",
        "forum_topic_reopened",
        "general_forum_topic_hidden",
        "general_forum_topic_unhidden",
    ),
    "other": (
        "message_auto_delete_timer_changed",
        "proximity_alert_triggered",
        "write_access_allowed",
        "users_shared",
        "chat_shared",
        "giveaway_created",
        "giveaway_completed",
        "chat_background_set",
        "boost_added",
        "group_chat_created",
        "supergroup_chat_created",
        "channel_chat_created",
    ),
}


def _service_kind(msg: Message) -> str | None:
    """Tin này thuộc nhóm dịch vụ nào (nếu có)."""
    for kind, fields in SERVICE_FIELDS.items():
        if any(getattr(msg, f, None) for f in fields):
            return kind
    return None


async def on_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ghi mốc gia nhập, rồi xoá tin dịch vụ theo cấu hình."""
    msg = update.effective_message
    if msg is None or msg.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    await _warn_if_crippled(msg.chat, context)

    # Ghi mốc thời gian vào nhóm TRƯỚC khi xoá - cần để biết ai là thành viên mới.
    if msg.new_chat_members:
        db = _db(context)
        for member in msg.new_chat_members:
            if not member.is_bot:
                await db.mark_joined(msg.chat_id, member.id)

    kinds = await _service_kinds_for(msg.chat_id, context)
    if not kinds:
        return
    kind = _service_kind(msg)
    if kind is None or kind not in kinds:
        return
    try:
        await msg.delete()
    except (BadRequest, Forbidden) as exc:
        log.warning("Không xoá được tin dịch vụ (%s) trong %s: %s", kind, msg.chat_id, exc)


# ---------------------------------------------------------------------------
# Lệnh quản trị (im lặng: tự xoá sau SELF_DESTRUCT giây)
# ---------------------------------------------------------------------------


async def _delete_later(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id, message_ids = context.job.data
    for mid in message_ids:
        try:
            await context.bot.delete_message(chat_id, mid)
        except TelegramError:
            pass


async def _quiet_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Trả lời rồi tự xoá sau SELF_DESTRUCT giây, để nhóm luôn sạch.

    Trong chat riêng thì giữ lại - người dùng cần đọc và copy nội dung.
    """
    # Điểm chốt duy nhất để làm mới cache: mọi lệnh đều kết thúc ở đây, nên
    # lệnh vừa sửa danh sách sẽ có hiệu lực ngay. Đặt ở một chỗ thay vì rải
    # _invalidate_rules() ra 15 chỗ ghi - thêm lệnh mới không lo quên.
    # Lệnh chỉ đọc cũng xoá cache, nhưng dựng lại chỉ tốn ~60µs nên không sao.
    _invalidate_rules(context)

    msg = update.effective_message
    ids = [msg.message_id]
    try:
        sent = await msg.reply_html(text, disable_web_page_preview=True)
        ids.append(sent.message_id)
    except TelegramError as exc:
        log.warning("Không trả lời được lệnh: %s", exc)

    if msg.chat.type == ChatType.PRIVATE:
        return
    if context.job_queue:
        context.job_queue.run_once(_delete_later, SELF_DESTRUCT, data=(msg.chat_id, ids))


def _require_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Chỉ owner (OWNER_IDS) — dùng cho lệnh /addadm, /deladm, /setgroup."""
    user = update.effective_user
    return user is not None and user.id in _cfg(context).owner_ids


async def _require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True nếu người dùng là owner, bot admin (DB), hoặc admin Telegram của nhóm."""
    msg = update.effective_message
    user = update.effective_user
    if msg is None or user is None:
        return False
    # Owner luôn được phép.
    if user.id in _cfg(context).owner_ids:
        return True
    # Bot admin toàn cục (được thêm bởi /addadm).
    if await _db(context).is_bot_admin(user.id):
        return True
    # Trong chat riêng chỉ owner/bot_admin mới được; những người khác bị chặn im lặng.
    if msg.chat.type == ChatType.PRIVATE:
        return False
    # Trong nhóm: admin Telegram của nhóm cũng được.
    if user.id in await _admin_ids(msg.chat_id, context):
        return True
    # Không đủ quyền: xoá lệnh, không phản hồi.
    try:
        await msg.delete()
    except TelegramError:
        pass
    return False


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_admin(update, context):
        return
    cfg = _cfg(context)
    db = _db(context)

    targets = await _target_chat_ids(update, context)
    if not targets:
        await _quiet_reply(
            update, context,
            "Chưa đăng ký nhóm nào.\nDùng: <code>/setgroup -100XXXXXXXXX</code>",
        )
        return

    # Phần cấu hình chung — giống nhau cho mọi nhóm.
    header = (
        "🛡 <b>Trạng thái chống spam</b>\n"
        f"Hành động: <code>{cfg.action}</code>"
        + (f" ({cfg.mute_seconds}s)" if cfg.action == "mute" else "")
        + f" · ngưỡng <code>{cfg.spam_threshold}</code>"
        f" (mới: <code>{cfg.new_member_threshold}</code>)\n"
        f"Chặn forward: <code>{cfg.block_forwards}</code> · link: <code>{cfg.block_links}</code> · "
        f"kênh: <code>{cfg.block_channel_senders}</code> · "
        f"@: <code>{cfg.block_mentions}</code> · "
        f"QR: <code>{cfg.scan_qr and qrscan.AVAILABLE}</code> · "
        f"OCR: <code>{cfg.scan_ocr and ocr.AVAILABLE}</code>"
        + (f" (nhớ {ocr.cache_stats()[0]} ảnh)" if ocr.AVAILABLE else "")
        + "\n"
    )

    # Danh sách dùng chung cho mọi nhóm.
    g_kw = await db.count_keywords(GLOBAL)
    g_fw = await db.count_fwd_whitelist(GLOBAL)
    g_link = len(await db.get_whitelist_own(GLOBAL))
    g_at = await db.count_usernames(GLOBAL)
    header += (
        f"<b>Chung mọi nhóm</b> — từ cấm: <code>{g_kw}</code> · "
        f"acc seeding: <code>{g_fw}</code> · domain: <code>{g_link}</code> · "
        f"@: <code>{g_at}</code>\n"
    )

    blocks: list[str] = []
    for gid in targets:
        try:
            g = await context.bot.get_chat(gid)
            title = html.escape(g.title or str(gid))
        except TelegramError:
            title = str(gid)

        is_admin, can_delete, can_restrict, anon = await _bot_rights(gid, context)
        if not is_admin:
            quyen = "⚠️ bot chưa là admin"
        else:
            thieu = []
            if not can_delete:
                thieu.append("Delete messages")
            if not can_restrict and cfg.action in ("ban", "mute"):
                thieu.append("Ban users")
            quyen = f"⚠️ thiếu: {', '.join(thieu)}" if thieu else "✅ đủ quyền"
            quyen += " · ẩn danh: " + ("✅" if anon else "❌ chưa bật")

        total, bans, last_day = await db.stats(gid)
        kw = await db.count_keywords(gid)
        fw = await db.count_fwd_whitelist(gid)
        bl = await db.count_blacklist(gid)
        svc = await _service_kinds_for(gid, context)
        blocks.append(
            f"\n<b>{title}</b> (<code>{gid}</code>)\n"
            f"  {quyen}\n"
            f"  riêng nhóm — từ cấm: <code>{kw}</code> · seeding: <code>{fw}</code> · "
            f"chặn cứng: <code>{bl}</code>\n"
            f"  xoá tin dịch vụ: <code>{', '.join(sorted(svc)) or 'tắt'}</code>\n"
            f"  đã xử lý: <b>{total}</b> (ban: {bans}, 24h: {last_day})"
        )

    await _quiet_reply(update, context, header + "".join(blocks))


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Chấm điểm thử một tin nhắn (reply vào tin đó) mà không xử lý."""
    if not await _require_admin(update, context):
        return
    target = update.effective_message.reply_to_message
    if target is None:
        await _quiet_reply(update, context, "Hãy reply vào tin nhắn cần kiểm tra.")
        return
    cfg = _cfg(context)
    db = _db(context)
    uid = target.from_user.id if target.from_user else 0
    sender_id = target.sender_chat.id if target.sender_chat else uid
    offences = await db.count_offences(target.chat_id, uid) if uid else 0
    is_bl = await db.in_blacklist(target.chat_id, sender_id) if sender_id else False
    is_fwd = await db.in_fwd_whitelist(target.chat_id, uid) if uid else False
    has_qr, qr_payloads, ocr_text = await _scan_image(target, context)
    facts = _extract_facts(target, False, offences, has_qr, qr_payloads, ocr_text=ocr_text)
    verdict = analyse(facts, cfg)
    verdict_text = "SPAM" if verdict.is_spam else "sạch"
    reasons = html.escape("; ".join(verdict.reasons) or "không có dấu hiệu nào")
    # Nói rõ vì sao ảnh không bị bắt, thay vì chỉ báo "sạch" khó hiểu.
    co_anh = bool(target.photo or target.sticker or (
        target.document and (target.document.mime_type or "").startswith("image/")
    ))
    qr_note = ""
    if has_qr and qr_payloads:
        decoded = html.escape(" | ".join(qr_payloads)[:200])
        qr_note = f"\nQR: <code>{decoded}</code>"
    elif co_anh:
        if not cfg.scan_qr:
            qr_note = "\n⚠️ <b>Quét QR đang TẮT</b> (SCAN_QR=false) — ảnh không được kiểm tra."
        elif not qrscan.AVAILABLE:
            qr_note = (
                "\n⚠️ <b>Quét QR KHÔNG chạy được</b> — thiếu OpenCV: "
                f"<code>{html.escape(str(qrscan.UNAVAILABLE_REASON or 'không rõ'))}</code>\n"
                "Cài lại: <code>pip install opencv-python-headless</code>"
            )
        else:
            qr_note = "\nQR: không tìm thấy mã QR nào trong ảnh."

    if co_anh:
        if ocr_text:
            qr_note += f"\nOCR đọc được: <code>{html.escape(ocr_text[:250])}</code>"
        elif not cfg.scan_ocr:
            qr_note += "\n⚠️ <b>OCR đang TẮT</b> (SCAN_OCR=false) — chữ trong ảnh không được soi."
        elif not ocr.AVAILABLE:
            qr_note += (
                "\n⚠️ <b>OCR KHÔNG chạy được</b>: "
                f"<code>{html.escape(str(ocr.UNAVAILABLE_REASON or 'không rõ'))}</code>\n"
                "Cài: <code>apt install tesseract-ocr tesseract-ocr-vie</code>"
            )
        else:
            qr_note += "\nOCR: không đọc được chữ nào trong ảnh."
    # Từ cấm cũng phải được phản ánh, nếu không /check sẽ báo "sạch" cho tin sẽ bị ban.
    kw_list = await db.get_keywords_effective(target.chat_id)
    combined = " ".join(filter(None, [target.text, target.caption, *qr_payloads]))
    matched_kw = [
        kw for kw in kw_list
        if normalize(kw) in normalize(combined) or squeeze(kw) in squeeze(combined)
    ]

    list_note = ""
    if matched_kw:
        hits = html.escape(", ".join(sorted(matched_kw)[:5]))
        list_note = f"\n⛔ <b>Chứa từ cấm</b>: <code>{hits}</code> — sẽ bị ban ngay"
        verdict_text = "SPAM (từ cấm)"
    elif is_bl:
        list_note = "\n⛔ <b>Đang trong danh sách chặn cứng</b> — sẽ bị xử lý bất kể điểm số"
        verdict_text = "SPAM (chặn cứng)"
    elif is_fwd:
        list_note = "\n✅ <b>Được phép chuyển tiếp</b> — forward sẽ không bị tính điểm"
    await _quiet_reply(
        update,
        context,
        f"Kết quả: <b>{verdict_text}</b> — {verdict.score}/{verdict.threshold}\n{reasons}{qr_note}{list_note}",
    )


async def cmd_trust(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Đánh dấu một người là tin cậy (bot bỏ qua hoàn toàn).

    Trong nhóm: reply vào tin nhắn của người đó.
    Trong chat riêng: /trust <user_id>
    """
    if not await _require_admin(update, context):
        return
    msg = update.effective_message
    targets = await _target_chat_ids(update, context)
    if not targets:
        await _quiet_reply(update, context, "Chưa đăng ký nhóm nào. Dùng /setgroup")
        return

    uid: int | None = None
    if context.args:
        try:
            uid = int(context.args[0])
        except ValueError:
            pass
    if uid is None and msg.reply_to_message and msg.reply_to_message.from_user:
        uid = msg.reply_to_message.from_user.id

    if uid is None:
        await _quiet_reply(
            update, context,
            "Hãy reply vào tin nhắn của người cần tin cậy,\n"
            "hoặc dùng: <code>/trust &lt;user_id&gt;</code>",
        )
        return
    db = _db(context)
    for gid in targets:
        await db.set_trusted(gid, uid, True)
        await db.clear_offences(gid, uid)
    where = "nhóm này" if len(targets) == 1 else f"{len(targets)} nhóm"
    await _quiet_reply(
        update, context, f"Đã tin cậy <code>{uid}</code> ở {where} và xoá lịch sử vi phạm."
    )


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unban <user_id> hoặc reply vào tin của người đó."""
    if not await _require_admin(update, context):
        return
    msg = update.effective_message
    targets = await _target_chat_ids(update, context)
    if not targets:
        await _quiet_reply(update, context, "Chưa đăng ký nhóm nào. Dùng /setgroup")
        return
    uid: int | None = None
    if context.args:
        try:
            uid = int(context.args[0])
        except ValueError:
            uid = None
    elif msg.reply_to_message and msg.reply_to_message.from_user:
        uid = msg.reply_to_message.from_user.id
    if uid is None:
        await _quiet_reply(update, context, "Dùng: <code>/unban &lt;user_id&gt;</code> hoặc reply.")
        return

    db = _db(context)
    ok, failed = 0, 0
    for gid in targets:
        try:
            await context.bot.unban_chat_member(gid, uid, only_if_banned=True)
            await db.clear_offences(gid, uid)
            ok += 1
        except TelegramError:
            failed += 1
    tail = f" ({failed} nhóm không gỡ được)" if failed else ""
    await _quiet_reply(update, context, f"Đã gỡ chặn <code>{uid}</code> ở {ok} nhóm{tail}.")


def _parse_uid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Lấy user_id từ tham số đầu tiên hoặc từ tin nhắn được reply."""
    args = context.args or []
    if args:
        try:
            return int(args[0])
        except ValueError:
            return None
    target = update.effective_message.reply_to_message
    if target and target.from_user:
        return target.from_user.id
    return None


def _parse_eid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Lấy entity_id (user hoặc kênh) từ tham số đầu hoặc tin nhắn được reply."""
    args = context.args or []
    if args:
        try:
            return int(args[0])
        except ValueError:
            return None
    target = update.effective_message.reply_to_message
    if target:
        if target.sender_chat:
            return target.sender_chat.id
        if target.from_user:
            return target.from_user.id
    return None


# ---------------------------------------------------------------------------
# Chặn cứng người/kênh — /blockuser /unblockuser /blocked
# ---------------------------------------------------------------------------


async def cmd_blockuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/blockuser [id|reply] — chặn cứng người/kênh, ban bất kể điểm số."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    eid = _parse_eid(update, context)
    if eid is None:
        await _quiet_reply(
            update, context,
            "Reply vào tin của người/kênh đó, hoặc: <code>/blockuser &lt;id&gt;</code>\n\n"
            "Nhắn riêng bot → chặn ở <b>mọi nhóm</b>.",
        )
        return
    await _db(context).add_blacklist(scope, eid)
    await _quiet_reply(
        update, context,
        f"⛔ Đã chặn cứng <code>{eid}</code> ở {_scope_label(scope)} — "
        "mọi tin nhắn sẽ bị xoá và ban ngay.",
    )


async def cmd_unblockuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unblockuser [id|reply] — bỏ chặn cứng."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    eid = _parse_eid(update, context)
    if eid is None:
        await _quiet_reply(update, context, "Dùng: <code>/unblockuser &lt;id&gt;</code> hoặc reply.")
        return
    n = await _db(context).remove_blacklist(scope, eid)
    await _quiet_reply(
        update, context,
        f"Đã bỏ chặn <code>{eid}</code> ở {_scope_label(scope)}." if n
        else f"<code>{eid}</code> không có trong danh sách của {_scope_label(scope)}.",
    )


async def cmd_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/blocked — danh sách bị chặn cứng (chung + riêng nhóm)."""
    if not await _require_admin(update, context):
        return
    db = _db(context)
    shared = await db.get_blacklist(GLOBAL)
    block = f"<b>Chặn ở mọi nhóm</b> ({len(shared)}):\n" + (
        "\n".join(f"• <code>{e}</code>" for e in sorted(shared)) or "  (trống)"
    )
    msg = update.effective_message
    if msg.chat.type != ChatType.PRIVATE:
        own = await db.get_blacklist(msg.chat_id)
        block += f"\n\n<b>Riêng nhóm này</b> ({len(own)}):\n" + (
            "\n".join(f"• <code>{e}</code>" for e in sorted(own)) or "  (trống)"
        )
    await _quiet_reply(update, context, block)



async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xem chat_id và user_id. Ai cũng dùng được.

    Trong nhóm thì cả lệnh lẫn phản hồi tự xoá sau 20 giây; nhắn riêng cho bot
    thì phản hồi được giữ lại để copy.
    """
    msg = update.effective_message
    user = update.effective_user
    uid = user.id if user else "?"
    if msg.chat.type == ChatType.PRIVATE:
        await _quiet_reply(update, context, f"ID của bạn: <code>{uid}</code>")
        return
    await _quiet_reply(
        update,
        context,
        f"chat_id: <code>{msg.chat_id}</code>\nuser_id: <code>{uid}</code>",
    )


# ---------------------------------------------------------------------------
# Acc seeding (forward whitelist) — /adduser /deluser /users
# ---------------------------------------------------------------------------


def _scope_label(scope: int) -> str:
    return "mọi nhóm" if scope == GLOBAL else f"nhóm <code>{scope}</code>"


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/adduser [user_id|reply] — thêm acc seeding được phép chuyển tiếp."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    uid = _parse_uid(update, context)
    if uid is None:
        await _quiet_reply(
            update, context,
            "Reply vào tin nhắn của acc đó, hoặc: <code>/adduser &lt;user_id&gt;</code>",
        )
        return
    await _db(context).add_fwd_whitelist(scope, uid)
    await _quiet_reply(
        update, context,
        f"✅ Acc seeding <code>{uid}</code> — được phép chuyển tiếp ở {_scope_label(scope)}.",
    )


async def cmd_deluser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/deluser [user_id|reply] — xoá acc seeding."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    uid = _parse_uid(update, context)
    if uid is None:
        await _quiet_reply(update, context, "Dùng: <code>/deluser &lt;user_id&gt;</code> hoặc reply.")
        return
    n = await _db(context).remove_fwd_whitelist(scope, uid)
    await _quiet_reply(
        update, context,
        f"Đã xoá <code>{uid}</code> khỏi {_scope_label(scope)}." if n
        else f"<code>{uid}</code> không có trong danh sách của {_scope_label(scope)}.",
    )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/users — danh sách acc seeding (chung + riêng nhóm)."""
    if not await _require_admin(update, context):
        return
    db = _db(context)
    shared = await db.get_fwd_whitelist(GLOBAL)
    block = f"<b>Chung mọi nhóm</b> ({len(shared)}):\n" + (
        "\n".join(f"• <code>{u}</code>" for u in sorted(shared)) or "  (trống)"
    )
    msg = update.effective_message
    if msg.chat.type != ChatType.PRIVATE:
        own = await db.get_fwd_whitelist(msg.chat_id)
        block += f"\n\n<b>Riêng nhóm này</b> ({len(own)}):\n" + (
            "\n".join(f"• <code>{u}</code>" for u in sorted(own)) or "  (trống)"
        )
    await _quiet_reply(update, context, block)


# ---------------------------------------------------------------------------
# Bot admin — /addadm /deladm /admins  (chỉ owner mới thêm/xoá được)
# ---------------------------------------------------------------------------


async def cmd_addadm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addadm [user_id|reply] — thêm bot admin (chỉ owner)."""
    if not _require_owner(update, context):
        try:
            await update.effective_message.delete()
        except TelegramError:
            pass
        return
    msg = update.effective_message
    uid = _parse_uid(update, context)
    if uid is None:
        await _quiet_reply(
            update, context,
            "Reply vào tin nhắn của người đó, hoặc: <code>/addadm &lt;user_id&gt;</code>\n"
            "Người đó gõ /id để lấy ID của mình.",
        )
        return
    if uid in _cfg(context).owner_ids:
        await _quiet_reply(update, context, f"<code>{uid}</code> đã là owner, không cần thêm.")
        return

    # Không nhận tài khoản bot: bot không nhắn riêng cho bot khác được,
    # nên chúng không thể dùng bảng điều khiển.
    target = msg.reply_to_message
    if target and target.from_user and target.from_user.id == uid and target.from_user.is_bot:
        await _quiet_reply(
            update, context,
            "Không thêm được tài khoản bot làm admin. Hãy dùng nick thật (nick người)."
        )
        return

    # Lấy tên để xác nhận rõ đang thêm đúng người.
    ten = f"<code>{uid}</code>"
    try:
        info = await context.bot.get_chat(uid)
        if getattr(info, "is_bot", False) or info.type != ChatType.PRIVATE:
            await _quiet_reply(
                update, context,
                "ID này không phải nick người dùng thật. Hãy dùng nick thật (không phải bot/kênh)."
            )
            return
        ho_ten = html.escape(info.full_name or info.first_name or str(uid))
        ten = f"<b>{ho_ten}</b> (<code>{uid}</code>)"
    except TelegramError:
        pass  # Chưa từng chat với bot — vẫn thêm được, chỉ không hiện tên.

    await _db(context).add_bot_admin(uid)
    ok = await _apply_admin_menu(context.bot, uid, is_owner=False)
    note = "" if ok else (
        "\n\n⚠️ Người này chưa bấm Start với bot nên chưa thấy menu. "
        "Bảo họ mở chat riêng với bot và bấm Start — lệnh vẫn dùng được ngay bằng cách gõ tay."
    )
    await _quiet_reply(update, context, f"✅ Đã thêm bot admin {ten}.{note}")


async def cmd_deladm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/deladm [user_id|reply] — xoá bot admin (chỉ owner)."""
    if not _require_owner(update, context):
        try:
            await update.effective_message.delete()
        except TelegramError:
            pass
        return
    uid = _parse_uid(update, context)
    if uid is None:
        await _quiet_reply(update, context, "Dùng: <code>/deladm &lt;user_id&gt;</code> hoặc reply.")
        return
    n = await _db(context).remove_bot_admin(uid)
    if n:
        await _clear_admin_menu(context.bot, uid)
    await _quiet_reply(
        update, context,
        f"Đã xoá bot admin <code>{uid}</code>." if n else f"<code>{uid}</code> không có trong danh sách.",
    )


async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admins — danh sách bot admin."""
    if not await _require_admin(update, context):
        return
    ids = await _db(context).get_bot_admins()
    owner_list = ", ".join(f"<code>{o}</code>" for o in sorted(_cfg(context).owner_ids))
    if not ids:
        adm_text = "Bot admin: <b>trống</b>"
    else:
        rows = []
        for uid in ids:
            try:
                info = await context.bot.get_chat(uid)
                ten = html.escape(info.full_name or info.first_name or "?")
                tag = f" @{info.username}" if info.username else ""
                rows.append(f"• {ten}{tag} — <code>{uid}</code>")
            except TelegramError:
                rows.append(f"• <code>{uid}</code> — <i>chưa bấm Start với bot</i>")
        adm_text = f"Bot admin ({len(ids)} người):\n" + "\n".join(rows)
    await _quiet_reply(update, context, f"Owner: {owner_list or 'chưa đặt'}\n{adm_text}")


# ---------------------------------------------------------------------------
# Keyword blacklist — /addblacklist /delblacklist /bwords
# ---------------------------------------------------------------------------


async def cmd_addblacklist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addblacklist <cụm từ>[, <cụm từ>...] — thêm từ ban ngay khi gửi.

    Nhắn riêng bot → áp dụng mọi nhóm. Gõ trong nhóm → chỉ nhóm đó.
    Nhiều cụm một lúc: ngăn cách bằng dấu phẩy.
    """
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    if not context.args:
        await _quiet_reply(
            update, context,
            "Dùng: <code>/addblacklist lừa đảo</code>\n"
            "Nhiều cụm: <code>/addblacklist lừa đảo, scam, tuyển ctv</code>\n\n"
            "Nhắn riêng bot → cấm ở <b>mọi nhóm</b>.\n"
            "Gõ trong nhóm → chỉ cấm ở nhóm đó.",
        )
        return
    phrases = [p.strip() for p in " ".join(context.args).split(",") if p.strip()]
    if not phrases:
        await _quiet_reply(update, context, "Không có cụm từ nào hợp lệ.")
        return
    db = _db(context)
    for p in phrases:
        await db.add_keyword(scope, p)
    listed = "\n".join(f"• <code>{html.escape(p)}</code>" for p in phrases)
    await _quiet_reply(
        update, context,
        f"⛔ Đã cấm {len(phrases)} cụm ở {_scope_label(scope)}:\n{listed}\n\n"
        "Ai gửi tin chứa các cụm này sẽ bị xoá tin và ban ngay.",
    )


async def cmd_delblacklist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/delblacklist <cụm từ>[, <cụm từ>...] — xoá từ khỏi danh sách cấm."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    if not context.args:
        await _quiet_reply(update, context, "Dùng: <code>/delblacklist &lt;cụm từ&gt;</code>")
        return
    phrases = [p.strip() for p in " ".join(context.args).split(",") if p.strip()]
    db = _db(context)
    removed = [p for p in phrases if await db.remove_keyword(scope, p)]
    missing = [p for p in phrases if p not in removed]
    parts = []
    if removed:
        parts.append(
            f"Đã xoá khỏi {_scope_label(scope)}:\n"
            + "\n".join(f"• <code>{html.escape(p)}</code>" for p in removed)
        )
    if missing:
        parts.append(
            "Không tìm thấy:\n"
            + "\n".join(f"• <code>{html.escape(p)}</code>" for p in missing)
        )
    await _quiet_reply(update, context, "\n\n".join(parts))


async def cmd_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/preset [tên...] — nạp bộ từ cấm dựng sẵn."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    db = _db(context)
    args = [a.lower().strip(",") for a in (context.args or [])]

    if not args:
        rows = []
        for key, (label, phrases) in presets.PRESETS.items():
            rows.append(f"• <code>{key}</code> — {label} ({len(phrases)} cụm)")
        await _quiet_reply(
            update, context,
            "<b>Bộ từ cấm dựng sẵn</b>\n" + "\n".join(rows) + "\n\n"
            "<code>/preset all</code> — nạp bộ khuyến nghị\n"
            "<code>/preset cobac dautu</code> — nạp bộ chọn\n"
            "<code>/preset xem cobac</code> — xem nội dung trước khi nạp\n\n"
            "Đã bỏ dấu tự động: thêm <i>lừa đảo</i> là bắt luôn <i>lua dao, LỪA ĐẢO</i>.",
        )
        return

    # Xem trước nội dung một bộ.
    if args[0] in ("xem", "show", "list"):
        if len(args) < 2 or args[1] not in presets.PRESETS:
            await _quiet_reply(update, context, "Dùng: <code>/preset xem cobac</code>")
            return
        label, phrases = presets.PRESETS[args[1]]
        listed = "\n".join(f"• <code>{html.escape(p)}</code>" for p in phrases)
        await _quiet_reply(update, context, f"<b>{label}</b> ({len(phrases)} cụm)\n{listed}")
        return

    if args[0] in ("all", "tatca", "khuyennghi"):
        names = list(presets.DEFAULT_SET)
    else:
        names = [a for a in args if a in presets.PRESETS]
        unknown = [a for a in args if a not in presets.PRESETS]
        if unknown:
            await _quiet_reply(
                update, context,
                f"Không có bộ: <code>{html.escape(', '.join(unknown))}</code>\n"
                f"Gõ <code>/preset</code> để xem danh sách.",
            )
            return
    if not names:
        await _quiet_reply(update, context, "Chưa chọn bộ nào. Gõ <code>/preset</code> để xem.")
        return

    phrases = presets.all_phrases(names)
    existing = set(await db.get_keywords(scope))
    added = [p for p in phrases if p not in existing]
    for p in added:
        await db.add_keyword(scope, p)

    labels = ", ".join(presets.PRESETS[n][0] for n in names)
    canh_bao = ""
    if "tocao" in names:
        canh_bao = (
            "\n\n⚠️ <b>Bộ 'tocao' đã được nạp.</b> Đây là từ người dùng nói khi "
            "cảnh báo nhau về lừa đảo. Từ giờ ai nhắn <i>\"cái này lừa đảo đấy\"</i> "
            "sẽ bị ban ngay, kể cả khi họ đang nói đúng và giúp nhóm.\n"
            "Gỡ bằng: <code>/unpreset tocao</code>"
        )
    await _quiet_reply(
        update, context,
        f"✅ Đã nạp <b>{labels}</b> vào {_scope_label(scope)}\n"
        f"Thêm mới: <b>{len(added)}</b> cụm (đã có sẵn: {len(phrases) - len(added)})\n"
        f"Xem tất cả: /bwords{canh_bao}",
    )


async def cmd_unpreset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unpreset <tên> — gỡ một bộ từ cấm đã nạp."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    args = [a.lower().strip(",") for a in (context.args or [])]
    names = [a for a in args if a in presets.PRESETS]
    if not names:
        await _quiet_reply(
            update, context,
            "Dùng: <code>/unpreset cobac</code>\nGõ <code>/preset</code> để xem danh sách.",
        )
        return
    db = _db(context)
    removed = 0
    for p in presets.all_phrases(names):
        removed += await db.remove_keyword(scope, p)
    labels = ", ".join(presets.PRESETS[n][0] for n in names)
    await _quiet_reply(
        update, context, f"Đã gỡ <b>{labels}</b> khỏi {_scope_label(scope)} — {removed} cụm."
    )


async def cmd_bwords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/bwords — danh sách từ cấm (chung + riêng nhóm)."""
    if not await _require_admin(update, context):
        return
    db = _db(context)
    shared = await db.get_keywords(GLOBAL)
    block = f"<b>Cấm ở mọi nhóm</b> ({len(shared)}):\n" + (
        "\n".join(f"• <code>{html.escape(p)}</code>" for p in shared) or "  (trống)"
    )
    msg = update.effective_message
    if msg.chat.type != ChatType.PRIVATE:
        own = await db.get_keywords(msg.chat_id)
        block += f"\n\n<b>Riêng nhóm này</b> ({len(own)}):\n" + (
            "\n".join(f"• <code>{html.escape(p)}</code>" for p in own) or "  (trống)"
        )
    await _quiet_reply(update, context, block)


# ---------------------------------------------------------------------------
# Domain whitelist — /addlink /dellink /links
# ---------------------------------------------------------------------------


def _clean_domain(raw: str) -> str:
    """Chuẩn hoá một mục whitelist. GIỮ đường dẫn nếu có.

    "example.com"      -> "example.com"      (cho phép cả tên miền)
    "t.me/kenh-abc"    -> "t.me/kenh-abc"    (chỉ cho phép đúng link đó)
    """
    d = raw.strip().lower().lstrip(".")
    d = d.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    d = d.split("?")[0].split("#")[0].rstrip("/")
    return d


async def cmd_addlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addlink <domain>[, <domain>...] — thêm domain được phép xuất hiện."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    if not context.args:
        await _quiet_reply(
            update, context,
            "Dùng: <code>/addlink example.com</code>\n"
            "Nhiều domain: <code>/addlink shopee.vn, tiki.vn</code>\n\n"
            "Nhắn riêng bot → cho phép ở <b>mọi nhóm</b>.",
        )
        return
    raw_parts = " ".join(context.args).replace(",", " ").split()
    domains = [d for d in (_clean_domain(p) for p in raw_parts) if d and "." in d]
    if not domains:
        await _quiet_reply(update, context, "Domain không hợp lệ. VD: <code>/addlink example.com</code>")
        return
    db = _db(context)
    for d in domains:
        await db.add_whitelist(scope, d)
    listed = "\n".join(f"• <code>{html.escape(d)}</code>" for d in domains)
    await _quiet_reply(
        update, context, f"✅ Cho phép {len(domains)} domain ở {_scope_label(scope)}:\n{listed}"
    )


async def cmd_dellink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/dellink <domain>[, <domain>...] — xoá domain khỏi whitelist."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    if not context.args:
        await _quiet_reply(update, context, "Dùng: <code>/dellink example.com</code>")
        return
    raw_parts = " ".join(context.args).replace(",", " ").split()
    domains = [d for d in (_clean_domain(p) for p in raw_parts) if d]
    db = _db(context)
    removed = [d for d in domains if await db.remove_whitelist(scope, d)]
    if removed:
        listed = "\n".join(f"• <code>{html.escape(d)}</code>" for d in removed)
        await _quiet_reply(update, context, f"Đã xoá khỏi {_scope_label(scope)}:\n{listed}")
    else:
        await _quiet_reply(update, context, f"Không có domain nào trong {_scope_label(scope)}.")


async def cmd_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/links — danh sách domain được phép (chung + riêng nhóm + config)."""
    if not await _require_admin(update, context):
        return
    db = _db(context)
    shared = await db.get_whitelist_own(GLOBAL)
    block = f"<b>Cho phép ở mọi nhóm</b> ({len(shared)}):\n" + (
        "\n".join(f"• <code>{d}</code>" for d in sorted(shared)) or "  (trống)"
    )
    msg = update.effective_message
    if msg.chat.type != ChatType.PRIVATE:
        own = await db.get_whitelist_own(msg.chat_id)
        block += f"\n\n<b>Riêng nhóm này</b> ({len(own)}):\n" + (
            "\n".join(f"• <code>{d}</code>" for d in sorted(own)) or "  (trống)"
        )
    cfg_domains = ", ".join(f"<code>{d}</code>" for d in sorted(_cfg(context).whitelist_domains))
    block += f"\n\n<b>Từ file cấu hình</b>: {cfg_domains or '(trống)'}"
    await _quiet_reply(update, context, block)


# ---------------------------------------------------------------------------
# Tin nhắn dịch vụ — /services
# ---------------------------------------------------------------------------

_KIND_LABELS = {
    "join": "vào nhóm",
    "leave": "rời nhóm",
    "pin": "ghim tin",
    "title": "đổi tên nhóm",
    "photo": "đổi ảnh nhóm",
    "videochat": "gọi nhóm",
    "forum": "chủ đề forum",
    "other": "khác (boost, giveaway…)",
}


async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/services — chọn loại tin dịch vụ cần tự xoá.

    /services                  → xem cài đặt hiện tại
    /services all              → xoá tất cả
    /services off              → không xoá gì
    /services join,leave,pin   → chỉ xoá các loại này
    """
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    db = _db(context)
    args = context.args or []

    if not args:
        # Hiện trạng thái thực tế đang áp dụng.
        msg = update.effective_message
        if msg.chat.type == ChatType.PRIVATE:
            raw = await db.get_setting(f"svc:{GLOBAL}")
            active = (
                {k for k in raw.split(",") if k} if raw is not None
                else _cfg(context).delete_service
            )
            nguon = "cài chung" if raw is not None else "file .env"
        else:
            active = await _service_kinds_for(msg.chat_id, context)
            own = await db.get_setting(f"svc:{msg.chat_id}")
            nguon = "riêng nhóm này" if own is not None else "cài chung / .env"

        lines = "\n".join(
            f"{'✅' if k in active else '⬜'} <code>{k}</code> — {v}"
            for k, v in _KIND_LABELS.items()
        )
        await _quiet_reply(
            update, context,
            f"<b>Tự xoá tin dịch vụ</b> (nguồn: {nguon})\n{lines}\n\n"
            "<code>/services all</code> — xoá tất cả\n"
            "<code>/services off</code> — không xoá gì\n"
            "<code>/services join,leave,pin</code> — chọn loại\n\n"
            + ("Nhắn riêng bot → áp dụng <b>mọi nhóm</b>."
               if update.effective_message.chat.type == ChatType.PRIVATE
               else "Cài ở đây chỉ áp dụng nhóm này."),
        )
        return

    raw = " ".join(args).lower().replace(" ", "")
    if raw in ("all", "on", "tatca", "tất cả", "true", "1"):
        chosen = set(_KIND_LABELS)
    elif raw in ("off", "none", "khong", "không", "false", "0", "tat", "tắt"):
        chosen = set()
    else:
        parts = [p for p in raw.replace(";", ",").split(",") if p]
        invalid = [p for p in parts if p not in _KIND_LABELS]
        if invalid:
            await _quiet_reply(
                update, context,
                f"Không hiểu: <code>{html.escape(', '.join(invalid))}</code>\n"
                f"Chọn trong: <code>{', '.join(_KIND_LABELS)}</code>",
            )
            return
        chosen = set(parts)

    await db.set_setting(f"svc:{scope}", ",".join(sorted(chosen)))
    if chosen:
        listed = ", ".join(f"<code>{k}</code>" for k in sorted(chosen))
        await _quiet_reply(
            update, context, f"✅ Sẽ tự xoá {listed} ở {_scope_label(scope)}."
        )
    else:
        await _quiet_reply(
            update, context, f"✅ Không xoá tin dịch vụ nào ở {_scope_label(scope)}."
        )


async def _show_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    groups = await _managed_groups(context)
    if not groups:
        await _quiet_reply(
            update, context,
            "Chưa đăng ký nhóm nào.\n\n"
            "<code>/setgroup -100111 -100222</code> — đặt danh sách\n"
            "<code>/setgroup add -100333</code> — thêm một nhóm\n"
            "<code>/setgroup del -100333</code> — bỏ một nhóm\n\n"
            "Lấy chat_id bằng cách gõ /id trong nhóm đó.",
        )
        return
    lines = []
    for gid in groups:
        try:
            g = await context.bot.get_chat(gid)
            lines.append(f"• <code>{gid}</code> — {html.escape(g.title or '?')}")
        except TelegramError:
            lines.append(f"• <code>{gid}</code> — <i>không truy cập được</i>")
    await _quiet_reply(
        update, context,
        f"<b>Nhóm đang quản lý</b> ({len(groups)}):\n" + "\n".join(lines) +
        "\n\n<code>/setgroup add|del &lt;chat_id&gt;</code> để sửa danh sách.",
    )


# ---------------------------------------------------------------------------
# @username được phép — /addat /delat /ats
# ---------------------------------------------------------------------------


def _clean_at(raw: str) -> str:
    return raw.strip().lstrip("@").rstrip(",").lower()


async def cmd_addat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addat @user [@user2...] — cho phép nhắc tới các @ này."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    msg = update.effective_message

    raws = " ".join(context.args or []).replace(",", " ").split()
    names = [n for n in (_clean_at(r) for r in raws) if n]
    # Reply vào tin của ai đó thì lấy luôn @ của họ.
    if not names and msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user.username
        if u:
            names = [u.lower()]
    if not names:
        await _quiet_reply(
            update, context,
            "Dùng: <code>/addat @kenhcuaban</code>\n"
            "Nhiều cái: <code>/addat @a, @b</code>\n"
            "Hoặc reply vào tin nhắn của người đó.\n\n"
            "@ của admin nhóm đã tự được phép, không cần thêm.",
        )
        return
    db = _db(context)
    for n in names:
        await db.add_username(scope, n)
    listed = ", ".join(f"<code>@{html.escape(n)}</code>" for n in names)
    await _quiet_reply(update, context, f"✅ Cho phép nhắc {listed} ở {_scope_label(scope)}.")


async def cmd_delat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/delat @user — bỏ khỏi danh sách @ được phép."""
    if not await _require_admin(update, context):
        return
    scope = _write_scope(update)
    raws = " ".join(context.args or []).replace(",", " ").split()
    names = [n for n in (_clean_at(r) for r in raws) if n]
    if not names:
        await _quiet_reply(update, context, "Dùng: <code>/delat @kenhcuaban</code>")
        return
    db = _db(context)
    removed = [n for n in names if await db.remove_username(scope, n)]
    if removed:
        listed = ", ".join(f"<code>@{html.escape(n)}</code>" for n in removed)
        await _quiet_reply(update, context, f"Đã bỏ {listed} khỏi {_scope_label(scope)}.")
    else:
        await _quiet_reply(update, context, f"Không có @ nào trong {_scope_label(scope)}.")


async def cmd_ats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ats — danh sách @ được phép nhắc."""
    if not await _require_admin(update, context):
        return
    db = _db(context)
    msg = update.effective_message
    shared = await db.get_usernames_own(GLOBAL)
    block = f"<b>Cho phép ở mọi nhóm</b> ({len(shared)}):\n" + (
        "\n".join(f"• <code>@{n}</code>" for n in sorted(shared)) or "  (trống)"
    )
    if msg.chat.type != ChatType.PRIVATE:
        own = await db.get_usernames_own(msg.chat_id)
        block += f"\n\n<b>Riêng nhóm này</b> ({len(own)}):\n" + (
            "\n".join(f"• <code>@{n}</code>" for n in sorted(own)) or "  (trống)"
        )
        adm = await _admin_usernames(msg.chat_id, context)
        block += f"\n\n<b>Admin nhóm</b> (tự động, {len(adm)}):\n" + (
            "\n".join(f"• <code>@{n}</code>" for n in sorted(adm)) or "  (không ai đặt @)"
        )
    cfg_ats = ", ".join(f"<code>@{n}</code>" for n in sorted(_cfg(context).allowed_usernames))
    block += f"\n\n<b>Từ file cấu hình</b>: {cfg_ats or '(trống)'}"
    await _quiet_reply(update, context, block)


async def cmd_anon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/anon — kiểm tra trạng thái ẩn danh của bot và hướng dẫn bật."""
    if not await _require_admin(update, context):
        return
    targets = await _target_chat_ids(update, context)
    if not targets:
        await _quiet_reply(update, context, "Chưa đăng ký nhóm nào. Dùng /setgroup")
        return

    huong_dan = (
        "\n<b>Cách bật</b> (Telegram không cho bot tự làm):\n"
        "Mở nhóm → <b>Quản trị viên</b> → chọn con bot này →\n"
        "bật <b>Ẩn danh</b> (Remain Anonymous) → Lưu.\n\n"
        "Sau khi bật, tên bot biến mất khỏi danh sách admin mà thành viên thường thấy."
    )

    rows = []
    for gid in targets:
        try:
            g = await context.bot.get_chat(gid)
            title = html.escape(g.title or str(gid))
        except TelegramError:
            title = str(gid)
        is_admin, _, _, anon = await _bot_rights(gid, context)
        if not is_admin:
            rows.append(f"• {title}: ⚠️ bot chưa là admin")
        elif anon:
            rows.append(f"• {title}: ✅ đã ẩn danh")
        else:
            rows.append(f"• {title}: ❌ chưa ẩn danh")

    can_thiet = any("❌" in r for r in rows)
    await _quiet_reply(
        update, context,
        "<b>Trạng thái ẩn danh của bot</b>\n" + "\n".join(rows)
        + (huong_dan if can_thiet else ""),
    )


async def cmd_setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/setgroup — quản lý danh sách nhóm (chỉ owner, trong chat riêng).

    /setgroup                      → xem danh sách
    /setgroup -100111 -100222      → đặt lại toàn bộ danh sách
    /setgroup add -100333          → thêm
    /setgroup del -100333          → bỏ
    """
    msg = update.effective_message
    if msg is None:
        return
    # Gõ trong nhóm: tiện lợi — tự thêm chính nhóm đó vào danh sách.
    in_group = msg.chat.type != ChatType.PRIVATE
    if not _require_owner(update, context):
        try:
            await msg.delete()
        except TelegramError:
            pass
        return

    db = _db(context)
    args = context.args or []

    if in_group and not args:
        groups = await _managed_groups(context)
        if msg.chat_id not in groups:
            groups.append(msg.chat_id)
            await db.set_setting("home_group", ",".join(str(g) for g in groups))
            await _quiet_reply(update, context, f"✅ Đã thêm nhóm này (<code>{msg.chat_id}</code>).")
        else:
            await _quiet_reply(update, context, "Nhóm này đã có trong danh sách.")
        return

    if not args:
        await _show_groups(update, context)
        return

    sub = args[0].lower()
    groups = await _managed_groups(context)

    if sub in ("add", "them", "thêm", "del", "remove", "xoa", "xoá"):
        raw_ids = args[1:] or ([str(msg.chat_id)] if in_group else [])
        ids: list[int] = []
        for r in raw_ids:
            try:
                ids.append(int(r))
            except ValueError:
                continue
        if not ids:
            await _quiet_reply(update, context, "Thiếu chat_id. VD: <code>/setgroup add -100111</code>")
            return
        if sub in ("add", "them", "thêm"):
            added = [i for i in ids if i not in groups]
            groups.extend(added)
            note = f"Đã thêm {len(added)} nhóm." if added else "Các nhóm này đã có sẵn."
        else:
            before = len(groups)
            groups = [g for g in groups if g not in ids]
            note = f"Đã bỏ {before - len(groups)} nhóm."
        await db.set_setting("home_group", ",".join(str(g) for g in groups))
        await _quiet_reply(update, context, f"{note}\nCòn lại: <b>{len(groups)}</b> nhóm.")
        return

    # Đặt lại toàn bộ danh sách: /setgroup -100111 -100222 -100333
    ids = []
    for r in args:
        try:
            ids.append(int(r))
        except ValueError:
            await _quiet_reply(
                update, context,
                f"<code>{html.escape(r)}</code> không phải chat_id hợp lệ (dạng -100...).",
            )
            return
    await db.set_setting("home_group", ",".join(str(i) for i in ids))
    listed = "\n".join(f"• <code>{i}</code>" for i in ids)
    await _quiet_reply(update, context, f"✅ Đang quản lý {len(ids)} nhóm:\n{listed}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Chào hỏi khi người dùng bấm Start trong chat riêng."""
    msg = update.effective_message
    if msg.chat.type != ChatType.PRIVATE:
        return
    user = update.effective_user
    uid = user.id if user else "?"

    # Owner / bot admin → hiện bảng điều khiển
    db = _db(context)
    is_owner = user is not None and user.id in _cfg(context).owner_ids
    if is_owner or (user and await db.is_bot_admin(user.id)):
        groups = await _managed_groups(context)
        group_line = (
            f"Đang quản lý <b>{len(groups)}</b> nhóm — /setgroup để xem"
            if groups
            else "Chưa có nhóm nào — thêm bot vào nhóm, hoặc <code>/setgroup -100XXX</code>"
        )
        owner_only = (
            "\n<b>Chỉ owner</b>\n"
            "/addadm · /deladm — bot admin\n"
            "/setgroup — danh sách nhóm\n"
            if is_owner else ""
        )
        await _quiet_reply(
            update, context,
            f"🛡 <b>Bot chống spam — Bảng điều khiển</b>\n"
            f"ID của bạn: <code>{uid}</code>\n"
            f"{group_line}\n\n"
            "⚠️ <b>Nhắn ở đây = áp dụng cho MỌI nhóm.</b>\n"
            "Muốn chỉ một nhóm thì gõ lệnh trong nhóm đó.\n\n"
            "<b>Từ cấm</b> — ai gửi là ban ngay\n"
            "/preset — nạp bộ dựng sẵn (nên bắt đầu từ đây)\n"
            "<code>/addblacklist cụm từ, cụm từ</code>\n"
            "/delblacklist · /bwords\n\n"
            "<b>Acc seeding</b> — được phép forward\n"
            "/adduser &lt;id&gt; · /deluser · /users\n\n"
            "<b>Link được phép</b>\n"
            "<code>/addlink t.me/kenhcuaban</code>\n"
            "/dellink · /links\n\n"
            "<b>@ được phép nhắc</b> — @ khác là ban\n"
            "<code>/addat @kenhcuaban</code>\n"
            "/delat · /ats  (admin nhóm tự được phép)\n\n"
            "<b>Chặn cứng người/kênh</b>\n"
            "/blockuser &lt;id&gt; · /unblockuser · /blocked\n\n"
            "<b>Tin dịch vụ</b> — vào/rời/ghim nhóm\n"
            "<code>/services join,leave,pin</code> · /services off\n\n"
            "<b>Khác</b>\n"
            "/status · /admins · /trust &lt;id&gt; · /unban &lt;id&gt;\n"
            f"{owner_only}",
        )
        return

    # Người thường → chỉ hiện ID
    await _quiet_reply(
        update,
        context,
        "Đây là bot chống spam cho nhóm. Bot chỉ làm việc bên trong nhóm và không "
        "nhắn gì ra nhóm cả.\n\n"
        f"ID của bạn: <code>{uid}</code>\n\n"
        "Bấm vào dãy số trên để copy. Gõ /id bất cứ lúc nào để xem lại.",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    # Lỗi thường gặp, in gọn một dòng thay vì cả traceback dài.
    if isinstance(err, Conflict):
        log.error(
            "Đang có một instance khác của bot này chạy song song (cùng BOT_TOKEN). "
            "Tắt bớt đi, chỉ được chạy một bản."
        )
        return
    if isinstance(err, NetworkError):
        log.warning("Lỗi mạng, sẽ tự thử lại: %s", err)
        return
    log.error("Lỗi khi xử lý update", exc_info=err)


# ---------------------------------------------------------------------------


_OWNER_CMDS = [
    BotCommand("status", "Trạng thái mọi nhóm"),
    BotCommand("preset", "Nạp bộ từ cấm dựng sẵn"),
    BotCommand("unpreset", "Gỡ bộ từ cấm"),
    BotCommand("addblacklist", "Cấm từ/cụm từ (mọi nhóm)"),
    BotCommand("delblacklist", "Bỏ từ cấm"),
    BotCommand("bwords", "Danh sách từ cấm"),
    BotCommand("adduser", "Thêm acc seeding (được forward)"),
    BotCommand("deluser", "Xoá acc seeding"),
    BotCommand("users", "Danh sách acc seeding"),
    BotCommand("addlink", "Cho phép domain"),
    BotCommand("dellink", "Bỏ domain"),
    BotCommand("links", "Danh sách domain"),
    BotCommand("addat", "Cho phép nhắc @username"),
    BotCommand("delat", "Bỏ @username được phép"),
    BotCommand("ats", "Danh sách @ được phép"),
    BotCommand("blockuser", "Chặn cứng người/kênh"),
    BotCommand("unblockuser", "Bỏ chặn cứng"),
    BotCommand("blocked", "Danh sách chặn cứng"),
    BotCommand("services", "Tự xoá tin vào/rời/ghim nhóm"),
    BotCommand("anon", "Kiểm tra bot đã ẩn danh chưa"),
    BotCommand("addadm", "Thêm bot admin"),
    BotCommand("deladm", "Xoá bot admin"),
    BotCommand("admins", "Danh sách bot admin"),
    BotCommand("setgroup", "Quản lý danh sách nhóm"),
    BotCommand("id", "Xem ID Telegram của bạn"),
]

_GROUP_ADMIN_CMDS = [
    BotCommand("status", "Trạng thái và thống kê"),
    BotCommand("preset", "Nạp bộ từ cấm dựng sẵn"),
    BotCommand("addblacklist", "Cấm từ ở nhóm này"),
    BotCommand("adduser", "Thêm acc seeding (reply hoặc id)"),
    BotCommand("addlink", "Cho phép domain ở nhóm này"),
    BotCommand("addat", "Cho phép nhắc @username"),
    BotCommand("ats", "Danh sách @ được phép"),
    BotCommand("blockuser", "Chặn cứng (reply hoặc id)"),
    BotCommand("services", "Tự xoá tin vào/rời/ghim nhóm"),
    BotCommand("anon", "Kiểm tra bot đã ẩn danh chưa"),
    BotCommand("check", "Chấm điểm thử tin nhắn (reply)"),
    BotCommand("trust", "Tin cậy hoàn toàn (reply hoặc id)"),
    BotCommand("unban", "Gỡ chặn người dùng"),
    BotCommand("id", "Xem chat_id / user_id"),
]


# Lệnh chỉ owner mới dùng được — ẩn khỏi menu của bot admin thường.
_OWNER_ONLY = {"addadm", "deladm", "setgroup"}


async def _apply_admin_menu(bot, user_id: int, is_owner: bool = False) -> bool:
    """Đặt bảng điều khiển cho một người trong chat riêng với bot.

    Chỉ thành công nếu người đó đã bấm Start với bot. Nếu chưa, Telegram báo
    'chat not found' — menu sẽ được đặt lại ở lần khởi động sau.
    """
    cmds = _OWNER_CMDS if is_owner else [c for c in _OWNER_CMDS if c.command not in _OWNER_ONLY]
    try:
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=user_id))
        return True
    except TelegramError as exc:
        log.info("Chưa đặt được menu cho %s (có thể chưa bấm Start): %s", user_id, exc)
        return False


async def _clear_admin_menu(bot, user_id: int) -> None:
    """Gỡ bảng điều khiển khi một người bị xoá khỏi danh sách admin."""
    try:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
    except TelegramError:
        pass


async def _check_log_chat(app: Application) -> None:
    """Kiểm tra LOG_CHAT_ID ngay lúc khởi động, báo rõ nếu không dùng được.

    Không kiểm tra thì lỗi chỉ lộ ra khi có vi phạm đầu tiên - lúc đó log
    đã mất và người dùng không biết vì sao.
    """
    cfg: Config = app.bot_data["cfg"]
    if not cfg.log_chat_id:
        log.info("LOG_CHAT_ID: chưa đặt — chỉ ghi log ra màn hình.")
        return

    cid = cfg.log_chat_id
    try:
        chat = await app.bot.get_chat(cid)
    except TelegramError as exc:
        if "not found" in str(exc).lower():
            log.error(
                "LOG_CHAT_ID=%s: KHÔNG GỬI ĐƯỢC LOG — 'Chat not found'.\n"
                "  Telegram báo vậy khi bot CHƯA ở trong chat đó (không phải do sai ID).\n"
                "  Cách sửa: mở kênh/nhóm log → Thêm thành viên → thêm chính con bot này\n"
                "  → cấp quyền admin (kênh cần quyền 'Post Messages').\n"
                "  Nếu là kênh vừa tạo, nhớ bấm Lưu sau khi cấp quyền.",
                cid,
            )
        else:
            log.error("LOG_CHAT_ID=%s: không truy cập được — %s", cid, exc)
        return

    # Truy cập được rồi, nhưng còn phải gửi được.
    try:
        me = await app.bot.get_chat_member(cid, app.bot.id)
        if me.status == ChatMemberStatus.LEFT:
            log.error("LOG_CHAT_ID=%s (%r): bot đã rời khỏi đây, thêm lại đi.", cid, chat.title)
            return
        if chat.type == ChatType.CHANNEL and me.status != ChatMemberStatus.ADMINISTRATOR:
            log.error(
                "LOG_CHAT_ID=%s (%r): bot chưa là admin của kênh nên không đăng bài được. "
                "Cấp quyền admin kèm 'Post Messages'.",
                cid, chat.title,
            )
            return
    except TelegramError as exc:
        log.warning("LOG_CHAT_ID=%s: không kiểm tra được quyền — %s", cid, exc)

    log.info("LOG_CHAT_ID=%s (%r): ✅ gửi log được.", cid, chat.title or chat.type)


async def _setup_commands(app: Application) -> None:
    """Menu lệnh theo từng đối tượng.

    - Người thường (mặc định + chat riêng): trống — bot ẩn hoàn toàn.
    - Admin nhóm: bộ lệnh quản trị đầy đủ trong nhóm.
    - Owner (chat riêng với bot): bộ lệnh quản trị + /setgroup.
    """
    cfg: Config = app.bot_data["cfg"]
    db: Storage = app.bot_data["db"]
    try:
        await app.bot.set_my_commands([], scope=BotCommandScopeDefault())
        await app.bot.set_my_commands([], scope=BotCommandScopeAllPrivateChats())
        await app.bot.set_my_commands(_GROUP_ADMIN_CMDS, scope=BotCommandScopeAllChatAdministrators())
    except TelegramError as exc:
        log.warning("Không đặt được menu lệnh: %s", exc)

    # Menu riêng cho owner + bot admin trong chat riêng với bot.
    for uid in cfg.owner_ids:
        await _apply_admin_menu(app.bot, uid, is_owner=True)
    for uid in await db.get_bot_admins():
        if uid not in cfg.owner_ids:
            await _apply_admin_menu(app.bot, uid, is_owner=False)


async def _post_init(app: Application) -> None:
    cfg: Config = app.bot_data["cfg"]
    me = await app.bot.get_me()
    log.info("Bot @%s đã sẵn sàng (chế độ: %s)", me.username, cfg.action)
    await _setup_commands(app)
    await _check_log_chat(app)

    # Privacy mode bật thì bot không đọc được tin nhắn thường -> không lọc được gì.
    if not getattr(me, "can_read_all_group_messages", False):
        log.error(
            "PRIVACY MODE ĐANG BẬT: bot không đọc được tin nhắn thường trong nhóm nên "
            "KHÔNG lọc được spam. Vào @BotFather -> /setprivacy -> chọn bot -> Disable, "
            "rồi kick bot ra khỏi nhóm và thêm lại thì mới có hiệu lực."
        )
    else:
        log.info("Privacy mode: đã tắt (bot đọc được tin nhắn trong nhóm)")

    if cfg.delete_service:
        log.info("Tự xoá tin dịch vụ: %s", ", ".join(sorted(cfg.delete_service)))
    else:
        log.info("Tự xoá tin dịch vụ: TẮT")

    if cfg.scan_qr and qrscan.AVAILABLE:
        log.info("Quét mã QR trong ảnh: BẬT")
    elif cfg.scan_qr:
        log.warning(
            "Quét mã QR: TẮT - không nạp được OpenCV (%s). "
            "Cài bằng: pip install opencv-python-headless. "
            "Ảnh chứa QR sẽ không bị kiểm tra.",
            qrscan.UNAVAILABLE_REASON or "không rõ nguyên nhân",
        )
    else:
        log.info("Quét mã QR trong ảnh: TẮT theo cấu hình")

    if cfg.scan_ocr and ocr.AVAILABLE:
        log.info("Đọc chữ trong ảnh (OCR): BẬT — ngôn ngữ %s, thu về %dpx",
                 cfg.ocr_lang, cfg.ocr_max_side)
    elif cfg.scan_ocr:
        log.warning(
            "OCR: TẮT - không dùng được Tesseract (%s). "
            "Cài: apt install tesseract-ocr tesseract-ocr-vie && pip install pytesseract. "
            "Chữ nằm trong ảnh sẽ không bị soi từ cấm.",
            ocr.UNAVAILABLE_REASON or "không rõ nguyên nhân",
        )
    else:
        log.info("Đọc chữ trong ảnh (OCR): TẮT theo cấu hình")


async def _post_shutdown(app: Application) -> None:
    db: Storage | None = app.bot_data.get("db")
    if db:
        db.close()


def build_application(cfg: Config) -> Application:
    app = (
        ApplicationBuilder()
        .token(cfg.token)
        .rate_limiter(AIORateLimiter())
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["cfg"] = cfg
    app.bot_data["db"] = Storage(cfg.db_path)

    # Nhóm 0: lệnh quản trị.
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("trust", cmd_trust))
    app.add_handler(CommandHandler("unban", cmd_unban))
    # Acc seeding
    app.add_handler(CommandHandler("adduser", cmd_adduser))
    app.add_handler(CommandHandler("deluser", cmd_deluser))
    app.add_handler(CommandHandler("users", cmd_users))
    # Bot admin
    app.add_handler(CommandHandler("addadm", cmd_addadm))
    app.add_handler(CommandHandler("deladm", cmd_deladm))
    app.add_handler(CommandHandler("admins", cmd_admins))
    # Keyword blacklist
    app.add_handler(CommandHandler("addblacklist", cmd_addblacklist))
    app.add_handler(CommandHandler("delblacklist", cmd_delblacklist))
    app.add_handler(CommandHandler("bwords", cmd_bwords))
    app.add_handler(CommandHandler("preset", cmd_preset))
    app.add_handler(CommandHandler("unpreset", cmd_unpreset))
    # Domain whitelist
    app.add_handler(CommandHandler("addlink", cmd_addlink))
    app.add_handler(CommandHandler("dellink", cmd_dellink))
    app.add_handler(CommandHandler("links", cmd_links))
    # @username được phép
    app.add_handler(CommandHandler("addat", cmd_addat))
    app.add_handler(CommandHandler("delat", cmd_delat))
    app.add_handler(CommandHandler("ats", cmd_ats))
    # Chặn cứng người/kênh
    app.add_handler(CommandHandler("blockuser", cmd_blockuser))
    app.add_handler(CommandHandler("unblockuser", cmd_unblockuser))
    app.add_handler(CommandHandler("blocked", cmd_blocked))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("anon", cmd_anon))
    app.add_handler(CommandHandler("setgroup", cmd_setgroup))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("start", cmd_start))

    # Nhóm 1: quét mọi tin nhắn (kể cả tin đã chỉnh sửa).
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL, scan), group=1
    )
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, on_service), group=1)
    app.add_handler(
        ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER), group=1
    )

    app.add_error_handler(on_error)
    return app
