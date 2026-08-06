"""Bộ dò spam theo điểm.

Mỗi dấu hiệu cộng một số điểm; tổng điểm vượt ngưỡng thì tin nhắn bị xử lý.
Cách chấm điểm (thay vì chặn cứng theo từ khoá) giúp giảm oan sai: một từ
nhạy cảm đơn lẻ không đủ, nhưng "kèo thơm" + link lạ + tài khoản mới thì đủ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Config
from .normalize import normalize, obfuscation_score, squeeze

# --------------------------------------------------------------------------
# Từ khoá (viết ở dạng đã bỏ dấu, chữ thường - xem normalize.py)
# --------------------------------------------------------------------------

# Điểm 3: gần như chắc chắn là spam/lừa đảo
STRONG = {
    # Việc nhẹ lương cao / tuyển CTV
    "viec nhe luong cao", "tuyen ctv", "tuyen cong tac vien", "ctv online",
    "lam viec tai nha luong", "khong can kinh nghiem luong", "thu nhap khong gioi han",
    # Cờ bạc
    "nha cai uy tin", "ca cuoc", "tai xiu", "no hu", "soi cau", "lo de",
    "keo thom", "chot keo", "dang ky nhan 100k", "hoan tra cao nhat",
    "game bai doi thuong", "link vao nha cai",
    # Đầu tư / crypto lừa đảo
    "cam ket loi nhuan", "bao lai", "loi nhuan khung", "sieu loi nhuan",
    "x2 tai khoan", "x3 tai khoan", "san giao dich uy tin", "tin hieu giao dich",
    "chot lai lien tuc", "khong lo von", "lai suat 0",
    "guaranteed profit", "guaranteed returns", "double your money",
    "free airdrop", "claim airdrop", "elon musk giveaway", "crypto giveaway",
    "pump signal", "insider signal",
    # Vay nặng lãi / tín dụng đen
    "vay tien nhanh", "vay nong", "giai ngan trong ngay", "chi can cmnd",
    "chi can cccd", "ho tro no xau", "vay khong the chap", "alo la co tien",
    # Giấy tờ giả / hàng cấm
    "lam bang gia", "bang cap gia", "lam giay to gia", "mua ban cccd",
    "mua ban data", "hack facebook", "hack tai khoan", "unlock icloud gia re",
    "sim rac gia re", "mua ban tai khoan ngan hang", "thue tai khoan ngan hang",
    # Người lớn
    "gai goi", "check hang gai", "phim sex", "clip nong", "sugar baby tuyen",
    # Chiếm đoạt tài khoản
    "cung cap ma otp", "gui ma otp", "doc ma otp", "tai khoan cua ban bi khoa",
    "xac minh tai khoan ngay", "nhap thong tin the",
}

# Điểm 2: đáng ngờ, cần đi kèm dấu hiệu khác
MEDIUM = {
    "kiem tien online", "kiem tien tai nha", "thu nhap thu dong", "lam giau",
    "co hoi dau tu", "dau tu sinh loi", "von it loi nhieu", "hoa hong cao",
    "rut tien nhanh", "nap rut", "uy tin so 1", "top 1 chau a",
    "san quoc te", "forex", "binary option", "bo tui moi ngay",
    "moi ngay 500k", "moi ngay 1 trieu", "300k ngay", "500k ngay",
    "tang ngay", "nhan ngay", "qua tang khung", "trung thuong",
    "nhan thuong", "ma khuyen mai", "code tan thu",
    "inbox de biet them", "ib de duoc tu van", "lien he zalo",
    "add zalo", "ket ban zalo", "ib rieng", "nhan tin rieng",
    "investment opportunity", "passive income", "work from home earn",
    "make money fast", "financial freedom", "dm me for", "text me on whatsapp",
    "join my channel", "join our vip", "vip signal", "trading bot profit",
    "recover your funds", "recovery expert", "hack recovery",
}

# Điểm 1: chỉ là gia vị, một mình không đủ để xử lý
WEAK = {
    "nhanh tay", "so luong co han", "chi hom nay", "duy nhat hom nay",
    "lien he ngay", "dang ky ngay", "click vao link", "bam vao link",
    "truy cap link", "link duoi day", "xem chi tiet tai", "mien phi 100",
    "cam ket", "uy tin", "bao mat tuyet doi", "rut tien 24 7",
    "limited time", "act now", "click here", "sign up now", "100 free",
}

# Dạng liền không dấu, bắt kiểu "k i e m t i e n o n l i n e".
# Chỉ giữ cụm đủ dài để không khớp nhầm khi nối chữ giữa các từ bình thường.
SQUEEZED_STRONG = {squeeze(k) for k in STRONG if len(squeeze(k)) >= 12}
SQUEEZED_MEDIUM = {squeeze(k) for k in MEDIUM if len(squeeze(k)) >= 12}

# --------------------------------------------------------------------------
# Regex
# --------------------------------------------------------------------------

URL_RE = re.compile(
    r"""(?xi)
    \b
    (?:https?://|www\.)?
    (?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+
    (?:com|net|org|io|co|xyz|top|icu|click|link|work|buzz|cfd|rest|monster|
       shop|site|online|live|vip|win|bet|casino|app|dev|me|tv|info|biz|ru|cn|
       vn|us|uk|asia|pro|store|fun|life|world|space|website|host|art|club)
    \b (?:/[^\s]*)?
    """
)

# Dạng né bộ lọc: "abc (dot) com", "abc [.] com", "abc . com"
OBFUSCATED_URL_RE = re.compile(
    r"(?i)\b[a-z0-9][a-z0-9-]{1,61}\s*(?:\(|\[|\{)?\s*(?:dot|\.|,)\s*(?:\)|\]|\})?\s*"
    r"(?:com|net|org|io|xyz|top|vip|win|club|shop|live|me)\b"
)

INVITE_RE = re.compile(r"(?i)(?:t\.me/\+|t\.me/joinchat/|telegram\.me/\+|telegram\.dog/)")

# @username Telegram: 5-32 ký tự, chữ/số/gạch dưới. Bắt cả khi Telegram không
# tạo entity (ví dụ @ nằm trong caption ảnh hoặc dính dấu câu).
# (?<![\w@/]) tránh khớp phần sau của email hay t.me/@abc.
MENTION_RE = re.compile(r"(?<![\w@/])@([A-Za-z][A-Za-z0-9_]{4,31})\b")

SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "goo.gl", "ow.ly", "rb.gy",
    "shorturl.at", "rebrand.ly", "t.co", "shorte.st", "adf.ly", "bl.ink",
    "s.id", "linktr.ee", "urlz.fr", "v.gd", "tiny.cc", "1link.vn", "vn.link",
}

SUSPICIOUS_TLDS = {
    "xyz", "top", "icu", "click", "link", "work", "buzz", "cfd", "rest",
    "monster", "win", "bet", "casino", "loan", "gq", "tk", "ml", "cf", "ga",
    "fun", "space", "host", "surf", "quest", "sbs", "autos", "bond",
}

CRYPTO_RE = re.compile(
    r"(?:\b(?:bc1|[13])[a-hj-np-z0-9]{25,62}\b)"      # BTC
    r"|(?:\b0x[a-fA-F0-9]{40}\b)"                      # ETH/BSC
    r"|(?:\bT[1-9A-HJ-NP-Za-km-z]{33}\b)"              # TRON
)

BANK_RE = re.compile(r"(?i)\b(?:stk|so tk|s[oố] t[aà]i kho[aả]n|acc?t\.?\s*no)\b\D{0,12}\d{6,20}")

PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:3|5|7|8|9)\d(?:[\s.\-]?\d){7}(?!\d)")

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⬀-⯿]"
)

# QR thanh toán chuẩn EMVCo (VietQR, VNPay, MoMo...): chuỗi bắt đầu bằng
# "000201", có mã tiền tệ (5303) và/hoặc mã quốc gia (5802VN).
EMV_QR_RE = re.compile(r"^000201.*(?:5303\d{3}|58\d{2}[A-Z]{2})", re.DOTALL)

# Ví crypto / ứng dụng ví đặt trong QR.
WALLET_URI_RE = re.compile(
    r"(?i)^(?:bitcoin|ethereum|tron|litecoin|ton|solana|monero|bnb|metamask|trust|wc):"
)

# QR chứa lệnh mở app/kênh Telegram.
TG_URI_RE = re.compile(r"(?i)^(?:tg://|telegram://)")

MONEY_RE = re.compile(
    r"(?i)\b\d{2,4}\s*(?:k|m|usd|\$)\b"          # 500k, 100 usd
    r"|\b\d{1,4}\s*(?:tr|trieu|triệu|củ|cu)\b"    # 1 triệu, 5 củ
    r"|[$₫]\s*\d{3,}"                              # $1000
)


# --------------------------------------------------------------------------


@dataclass
class MessageFacts:
    """Thông tin rút ra từ một tin nhắn Telegram, tách khỏi thư viện telegram."""

    text: str = ""
    entity_urls: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    is_forward: bool = False
    forward_label: str | None = None
    via_bot: bool = False
    from_channel: bool = False
    has_buttons: bool = False
    has_media: bool = False
    is_new_member: bool = False
    has_username: bool = True
    prior_offences: int = 0
    has_qr: bool = False
    qr_payloads: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    threshold: int = 0

    def add(self, points: int, reason: str) -> None:
        if points <= 0:
            return
        self.score += points
        self.reasons.append(f"{reason} (+{points})")

    @property
    def is_spam(self) -> bool:
        return self.score >= self.threshold

    def summary(self) -> str:
        return f"{self.score}/{self.threshold} · " + "; ".join(self.reasons)


def _hostname(url: str) -> str:
    url = url.strip().rstrip(".,;:!?)»\"'")
    url = re.sub(r"(?i)^[a-z][a-z0-9+.\-]*://", "", url)
    host = url.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _split_url(url: str) -> tuple[str, str]:
    """Tách URL thành (host, path). Path đã bỏ dấu / đầu-cuối, viết thường."""
    url = url.strip().rstrip(".,;:!?)»\"'")
    url = re.sub(r"(?i)^[a-z][a-z0-9+.\-]*://", "", url)
    head, _, tail = url.partition("/")
    host = head.split("?", 1)[0].split("#", 1)[0].split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    path = tail.split("?", 1)[0].split("#", 1)[0].strip("/").lower()
    return host, path


def _host_matches(host: str, pattern: str) -> bool:
    return host == pattern or host.endswith("." + pattern)


def _is_whitelisted(host: str, whitelist: set[str]) -> bool:
    """Chỉ xét tên miền. Mục whitelist có đường dẫn không tính ở đây."""
    return any(_host_matches(host, d) for d in whitelist if "/" not in d)


def _url_allowed(url: str, whitelist: set[str]) -> bool:
    """URL có được phép không, xét cả đường dẫn.

    Mục whitelist dạng "t.me"                -> cho phép mọi link t.me/*
    Mục whitelist dạng "t.me/abc"            -> CHỈ cho phép đúng link đó
    Nhờ vậy admin mở một kênh cụ thể mà không mở toàn bộ tên miền.
    """
    host, path = _split_url(url)
    if not host or "." not in host:
        return True  # không phải link thật
    for entry in whitelist:
        e_host, _, e_path = entry.partition("/")
        e_host = e_host.lower()
        e_path = e_path.strip("/").lower()
        if not _host_matches(host, e_host):
            continue
        if not e_path:
            return True  # whitelist cả tên miền
        if path == e_path or path.startswith(e_path + "/"):
            return True
    return False


def _count_keywords(haystack: str, squeezed: str, verdict: Verdict) -> None:
    for weight, bucket, label in ((3, STRONG, "từ khoá lừa đảo"), (2, MEDIUM, "từ khoá đáng ngờ"), (1, WEAK, "từ khoá mồi chài")):
        hits = [k for k in bucket if k in haystack]
        if not hits:
            continue
        # Nhiều từ cùng nhóm chỉ cộng thêm 1 điểm mỗi từ để tránh phóng đại.
        points = weight + min(len(hits) - 1, 2)
        verdict.add(points, f"{label}: {', '.join(sorted(hits)[:3])}")

    # Bắt trường hợp chèn khoảng trắng/ký tự giữa từng chữ cái.
    if not any(k in haystack for k in STRONG) and any(k in squeezed for k in SQUEEZED_STRONG):
        verdict.add(3, "từ khoá lừa đảo bị làm nhiễu")
    elif not any(k in haystack for k in MEDIUM) and any(k in squeezed for k in SQUEEZED_MEDIUM):
        verdict.add(2, "từ khoá đáng ngờ bị làm nhiễu")


def analyse(facts: MessageFacts, cfg: Config) -> Verdict:
    threshold = cfg.new_member_threshold if facts.is_new_member else cfg.spam_threshold
    v = Verdict(threshold=max(1, threshold))

    text = facts.text or ""
    # Nội dung giải từ QR cũng được quét từ khoá như chữ trong tin nhắn.
    scannable = " ".join([text, *facts.qr_payloads]).strip()
    haystack = normalize(scannable)
    squeezed = squeeze(scannable)

    # --- Từ khoá ---
    if haystack:
        _count_keywords(haystack, squeezed, v)

    # --- Chuyển tiếp ---
    if facts.is_forward:
        block_fwd = cfg.block_forwards and (not cfg.block_forwards_new_only or facts.is_new_member)
        if block_fwd:
            label = f" từ {facts.forward_label}" if facts.forward_label else ""
            v.add(v.threshold, f"tin nhắn chuyển tiếp{label}")
        else:
            v.add(1, "tin nhắn chuyển tiếp")

    # --- Gửi dưới danh nghĩa kênh ---
    if facts.from_channel and cfg.block_channel_senders:
        v.add(v.threshold, "gửi dưới danh nghĩa kênh/nhóm khác")

    # --- Link ---
    urls = {u for u in (URL_RE.findall(text) + facts.entity_urls) if u}
    hosts = {h for h in (_hostname(u) for u in urls) if h and "." in h}
    # Xét cả đường dẫn: whitelist "t.me/kenh-a" không mở luôn "t.me/kenh-b".
    unknown_urls = {u for u in urls if not _url_allowed(u, cfg.whitelist_domains)}
    unknown_hosts = {h for h in (_hostname(u) for u in unknown_urls) if h and "." in h}

    if unknown_urls:
        block_link = cfg.block_links and (not cfg.block_links_new_only or facts.is_new_member)

        def _short(u: str) -> str:
            host, path = _split_url(u)
            return f"{host}/{path}" if path else host

        preview = ", ".join(sorted({_short(u) for u in unknown_urls})[:3])
        if block_link:
            v.add(v.threshold, f"link lạ: {preview}")
        else:
            v.add(2, f"link lạ: {preview}")

    if any(h in SHORTENERS for h in hosts):
        v.add(3, "link rút gọn")
    if any(h.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS for h in hosts):
        v.add(2, "tên miền thuộc nhóm rủi ro cao")
    if INVITE_RE.search(text):
        v.add(3, "link mời vào nhóm/kênh riêng")
    if OBFUSCATED_URL_RE.search(text) and not hosts:
        v.add(3, "link viết né bộ lọc (dạng 'abc (dot) com')")

    # --- Mã QR trong ảnh ---
    # Chỉ tính khi ĐỌC ĐƯỢC nội dung. "Có vẻ như là khung QR" không phải bằng
    # chứng: bộ dò nhận nhầm hoa văn ảnh đời thường (đĩa cơm, vân vải) rất nhiều.
    if facts.has_qr and facts.qr_payloads:
        v.add(2, "ảnh có chứa mã QR")
        if facts.is_new_member:
            v.add(2, "thành viên mới gửi mã QR")

    for payload in facts.qr_payloads:
        p = payload.strip()
        if EMV_QR_RE.match(p):
            v.add(v.threshold, "QR chuyển khoản / thanh toán ngân hàng")
            continue
        if WALLET_URI_RE.match(p) or CRYPTO_RE.search(p):
            v.add(v.threshold, "QR chứa địa chỉ ví crypto")
            continue
        if INVITE_RE.search(p) or TG_URI_RE.match(p):
            v.add(v.threshold, "QR dẫn tới nhóm/kênh Telegram")
            continue

        qr_urls = {u for u in URL_RE.findall(p) if _hostname(u) and "." in _hostname(u)}
        if not qr_urls and "://" in p and "." in _hostname(p):
            qr_urls = {p}
        unknown_qr = {u for u in qr_urls if not _url_allowed(u, cfg.whitelist_domains)}
        if unknown_qr:
            names = sorted({_hostname(u) for u in unknown_qr})[:2]
            v.add(v.threshold, f"QR dẫn tới link lạ: {', '.join(names)}")
        elif qr_urls:
            v.add(1, "QR dẫn tới link đã whitelist")

    # --- Nhắc @username ---
    # Gom cả entity do Telegram nhận diện lẫn @ viết thẳng trong chữ.
    handles = {m.strip().lstrip("@").lower() for m in facts.mentions}
    handles |= {m.lower() for m in MENTION_RE.findall(text)}
    handles = {h for h in handles if h}
    unknown_ats = {h for h in handles if h not in cfg.allowed_usernames}

    if unknown_ats and cfg.block_mentions:
        preview = ", ".join("@" + h for h in sorted(unknown_ats)[:3])
        v.add(v.threshold, f"nhắc @ không được phép: {preview}")
    elif len(handles) >= 3:
        v.add(2, f"nhắc tới {len(handles)} tài khoản/kênh")

    # --- Dấu hiệu tài chính ---
    if CRYPTO_RE.search(text):
        v.add(3, "địa chỉ ví crypto")
    if BANK_RE.search(text):
        v.add(3, "số tài khoản ngân hàng")
    if PHONE_RE.search(text) and (haystack or urls):
        v.add(2, "số điện thoại liên hệ")
    if MONEY_RE.search(text):
        v.add(1, "hứa hẹn thu nhập bằng con số")

    # --- Hình thức ---
    v.add(obfuscation_score(text), "ký tự ẩn / chữ giả Latin")

    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 25:
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if caps_ratio > 0.7:
            v.add(1, "viết hoa toàn bộ")

    emoji_count = len(EMOJI_RE.findall(text))
    if emoji_count >= 8:
        v.add(2, f"lạm dụng emoji ({emoji_count})")
    elif emoji_count >= 5:
        v.add(1, f"nhiều emoji ({emoji_count})")

    if facts.has_buttons:
        v.add(3, "tin nhắn kèm nút bấm (dấu hiệu bot spam)")
    if facts.via_bot:
        v.add(1, "gửi qua inline bot")

    # --- Bối cảnh người gửi ---
    if facts.is_new_member and (unknown_hosts or facts.is_forward):
        v.add(1, "thành viên mới đã gửi link/forward")
    if facts.is_new_member and not facts.has_username and urls:
        v.add(1, "tài khoản không username gửi link")
    # Tiền án chỉ LÀM NẶNG THÊM tin đã có dấu hiệu khác, không tự nó kết tội.
    # Nếu không có điều kiện này, người từng vi phạm sẽ bị ban vì cả tin nhắn
    # hoàn toàn sạch - kể cả link đã nằm trong whitelist.
    if facts.prior_offences and v.score > 0:
        v.add(min(facts.prior_offences * 2, 4), f"đã vi phạm {facts.prior_offences} lần trước đó")

    return v
