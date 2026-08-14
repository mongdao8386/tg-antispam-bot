"""Cấu hình đọc từ biến môi trường / file .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

VALID_ACTIONS = ("ban", "mute", "delete", "report")

# Nhóm tin nhắn dịch vụ có thể tự xoá (xem SERVICE_FIELDS trong bot.py)
SERVICE_KINDS = ("join", "leave", "pin", "title", "photo", "videochat", "forum", "other")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise SystemExit(f"{name} phải là số nguyên, nhận được: {raw!r}") from exc


def _id_list(name: str) -> set[int]:
    raw = os.getenv(name, "")
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError as exc:
            raise SystemExit(f"{name} chứa ID không hợp lệ: {part!r}") from exc
    return out


def _service_kinds(name: str, default: str) -> set[str]:
    """Đọc danh sách nhóm tin dịch vụ cần xoá. Chấp nhận 'all', 'none', hoặc liệt kê."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raw = default
    raw = raw.strip().lower()
    if raw in ("none", "false", "0", "off", "no"):
        return set()
    if raw in ("all", "true", "1", "on", "yes"):
        return set(SERVICE_KINDS)

    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if part not in SERVICE_KINDS:
            raise SystemExit(
                f"{name} chứa giá trị không hợp lệ: {part!r}. "
                f"Chọn trong {SERVICE_KINDS}, hoặc 'all'/'none'."
            )
        out.add(part)
    return out


def _username_list(name: str) -> set[str]:
    """Danh sách @username được phép. Lưu chữ thường, bỏ dấu @."""
    raw = os.getenv(name, "")
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip().lstrip("@").lower()
        if part:
            out.add(part)
    return out


def _phone_list(name: str) -> set[str]:
    """Số điện thoại được phép. Bỏ hết khoảng trắng, dấu chấm, gạch."""
    import re as _re
    raw = os.getenv(name, "")
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        part = _re.sub(r"[\s.\-()]", "", part.strip())
        if part:
            out.add(part)
    return out


def _domain_list(name: str, default: str) -> set[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raw = default
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip().lower().lstrip(".")
        if part.startswith("www."):
            part = part[4:]
        if part:
            out.add(part)
    return out


@dataclass(frozen=True)
class Config:
    token: str
    owner_ids: set[int] = field(default_factory=set)
    log_chat_id: int | None = None

    action: str = "ban"
    mute_seconds: int = 86400
    spam_threshold: int = 5
    new_member_threshold: int = 3
    new_member_hours: int = 24

    block_forwards: bool = True
    block_forwards_new_only: bool = False
    block_links: bool = True
    block_links_new_only: bool = False
    block_channel_senders: bool = True
    block_mentions: bool = True
    block_phones: bool = True

    # Phanh tự động: ban quá nhiều trong thời gian ngắn thường là dấu hiệu một
    # luật mới đang bắt oan hàng loạt, chứ không phải bị tấn công thật.
    brake_limit: int = 5
    brake_window: int = 60

    scan_qr: bool = True
    qr_max_bytes: int = 5_000_000

    scan_ocr: bool = True
    ocr_max_bytes: int = 5_000_000
    ocr_lang: str = "vie+eng"
    ocr_max_side: int = 1600

    delete_service: set[str] = field(default_factory=set)

    whitelist_domains: set[str] = field(default_factory=set)
    allowed_usernames: set[str] = field(default_factory=set)
    allowed_phones: set[str] = field(default_factory=set)

    web_enabled: bool = False
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    web_url: str = ""
    web_session_hours: int = 12

    db_path: Path = Path("antispam.db")
    log_level: str = "INFO"

    @property
    def new_member_seconds(self) -> int:
        return self.new_member_hours * 3600

    @classmethod
    def load(cls, env_file: str | os.PathLike[str] | None = None) -> "Config":
        load_dotenv(env_file or ".env")

        token = (os.getenv("BOT_TOKEN") or "").strip()
        if not token:
            raise SystemExit(
                "Thiếu BOT_TOKEN. Copy .env.example thành .env rồi điền token từ @BotFather."
            )

        action = (os.getenv("ACTION") or "ban").strip().lower()
        if action not in VALID_ACTIONS:
            raise SystemExit(f"ACTION phải là một trong {VALID_ACTIONS}, nhận được: {action!r}")

        log_chat_raw = (os.getenv("LOG_CHAT_ID") or "").strip()
        log_chat_id: int | None = None
        if log_chat_raw:
            try:
                log_chat_id = int(log_chat_raw)
            except ValueError as exc:
                raise SystemExit(f"LOG_CHAT_ID phải là số, nhận được: {log_chat_raw!r}") from exc

        return cls(
            token=token,
            owner_ids=_id_list("OWNER_IDS"),
            log_chat_id=log_chat_id,
            action=action,
            mute_seconds=_int("MUTE_SECONDS", 86400),
            spam_threshold=_int("SPAM_THRESHOLD", 5),
            new_member_threshold=_int("NEW_MEMBER_THRESHOLD", 3),
            new_member_hours=_int("NEW_MEMBER_HOURS", 24),
            block_forwards=_bool("BLOCK_FORWARDS", True),
            block_forwards_new_only=_bool("BLOCK_FORWARDS_NEW_ONLY", False),
            block_links=_bool("BLOCK_LINKS", True),
            block_links_new_only=_bool("BLOCK_LINKS_NEW_ONLY", False),
            block_channel_senders=_bool("BLOCK_CHANNEL_SENDERS", True),
            block_mentions=_bool("BLOCK_MENTIONS", True),
            block_phones=_bool("BLOCK_PHONES", True),
            brake_limit=_int("BRAKE_LIMIT", 5),
            brake_window=_int("BRAKE_WINDOW", 60),
            scan_qr=_bool("SCAN_QR", True),
            qr_max_bytes=_int("QR_MAX_BYTES", 5_000_000),
            scan_ocr=_bool("SCAN_OCR", True),
            ocr_max_bytes=_int("OCR_MAX_BYTES", 5_000_000),
            ocr_lang=(os.getenv("OCR_LANG") or "vie+eng").strip(),
            ocr_max_side=_int("OCR_MAX_SIDE", 1600),
            delete_service=_service_kinds("DELETE_SERVICE_MESSAGES", "join,leave,pin"),
            whitelist_domains=_domain_list(
                "WHITELIST_DOMAINS",
                "t.me,telegram.org,youtube.com,youtu.be,github.com,google.com,wikipedia.org",
            ),
            allowed_usernames=_username_list("ALLOWED_USERNAMES"),
            allowed_phones=_phone_list("ALLOWED_PHONES"),
            web_enabled=_bool("WEB_ENABLED", False),
            web_host=(os.getenv("WEB_HOST") or "127.0.0.1").strip(),
            web_port=_int("WEB_PORT", 8080),
            web_url=(os.getenv("WEB_URL") or "").strip().rstrip("/"),
            web_session_hours=_int("WEB_SESSION_HOURS", 12),
            db_path=Path((os.getenv("DB_PATH") or "antispam.db").strip()),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
        )
