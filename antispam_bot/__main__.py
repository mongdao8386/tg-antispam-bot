"""Điểm khởi chạy: python -m antispam_bot"""

from __future__ import annotations

import logging
import sys

from telegram import Update

from .bot import build_application
from .config import Config


def main() -> None:
    # Log có dấu tiếng Việt. Khi chạy trực tiếp thì console Windows hiển thị đúng,
    # nhưng khi chuyển hướng ra file Python lại dùng bảng mã hệ thống -> lỗi font.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    cfg = Config.load()
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        level=getattr(logging, cfg.log_level, logging.INFO),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = build_application(cfg)
    app.run_polling(
        allowed_updates=[
            Update.MESSAGE,
            Update.EDITED_MESSAGE,
            Update.CHAT_MEMBER,
            Update.MY_CHAT_MEMBER,
        ],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
