"""Bật/tắt và đổi chế độ ngay lúc chạy, không cần sửa .env hay khởi động lại.

Trạng thái lưu trong bảng bot_settings nên còn nguyên sau khi bot khởi động lại
- tạm ngưng rồi máy sập giữa chừng thì lúc lên lại vẫn đang ngưng, đúng ý người
dùng hơn là âm thầm bật lại.

Ba khoá dùng ở đây:
    pause_until   - mốc thời gian (epoch) hết tạm ngưng. 0 = không ngưng.
    action        - đè lên ACTION trong .env (ban/mute/delete/report)
    brake_at      - mốc lúc phanh tự động nhảy, để báo cho người dùng biết
"""

from __future__ import annotations

import time

from .config import VALID_ACTIONS, Config
from .storage import Storage


async def is_paused(db: Storage) -> tuple[bool, int]:
    """(đang tạm ngưng?, còn bao nhiêu giây nữa)."""
    raw = await db.get_setting("pause_until")
    if not raw:
        return False, 0
    try:
        until = int(raw)
    except ValueError:
        return False, 0
    con_lai = until - int(time.time())
    return (True, con_lai) if con_lai > 0 else (False, 0)


async def pause(db: Storage, minutes: int) -> int:
    """Tạm ngưng xử phạt. minutes <= 0 nghĩa là ngưng vô thời hạn."""
    if minutes <= 0:
        # 10 năm, coi như vô thời hạn nhưng vẫn là một con số hợp lệ.
        until = int(time.time()) + 315_360_000
    else:
        until = int(time.time()) + minutes * 60
    await db.set_setting("pause_until", str(until))
    return until


async def resume(db: Storage) -> None:
    await db.set_setting("pause_until", "0")


async def effective_action(db: Storage, cfg: Config) -> str:
    """Chế độ đang áp dụng thật sự: ưu tiên cài lúc chạy, sau đó tới .env."""
    raw = (await db.get_setting("action") or "").strip().lower()
    return raw if raw in VALID_ACTIONS else cfg.action


async def set_action(db: Storage, action: str) -> None:
    await db.set_setting("action", action)


async def clear_action(db: Storage) -> None:
    """Bỏ đè, quay về đúng ACTION trong .env."""
    await db.set_setting("action", "")


async def note_brake(db: Storage) -> None:
    await db.set_setting("brake_at", str(int(time.time())))


async def brake_info(db: Storage) -> int:
    raw = await db.get_setting("brake_at")
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0
