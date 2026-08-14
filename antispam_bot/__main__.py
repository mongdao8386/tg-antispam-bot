"""Điểm khởi chạy: python -m antispam_bot"""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.error import TimedOut

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
    try:
        app.run_polling(
            allowed_updates=[
                Update.MESSAGE,
                Update.EDITED_MESSAGE,
                Update.CHAT_MEMBER,
                Update.MY_CHAT_MEMBER,
            ],
            drop_pending_updates=True,
            # Mạng ở VN hay bóp băng thông tới Telegram, bắt tay TCP có khi mất
            # cả chục giây. Thử lại thay vì chết ngay ở lần đầu.
            bootstrap_retries=cfg.bootstrap_retries,
        )
    except TimedOut:
        _bao_loi_mang(cfg)
        raise SystemExit(1)


def _bao_loi_mang(cfg: Config) -> None:
    """In chẩn đoán dễ hiểu thay vì để traceback 200 dòng của thư viện."""
    log = logging.getLogger("antispam")
    log.error(
        "\n"
        "==================================================================\n"
        " KHÔNG KẾT NỐI ĐƯỢC TỚI TELEGRAM\n"
        "==================================================================\n"
        " Bot không gọi nổi api.telegram.org. Máy vẫn vào được mạng bình\n"
        " thường, nhưng riêng đường tới Telegram bị chặn hoặc bóp rất chậm -\n"
        " chuyện thường gặp với mạng dân dụng ở Việt Nam.\n"
        "\n"
        " Cách xử lý, theo thứ tự nên thử:\n"
        "\n"
        " 1. CHẠY TRÊN DROPLET (khuyến nghị). Máy chủ ở Singapore không dính\n"
        "    chặn này. Bạn đã cài sẵn, chỉ cần đẩy code lên GitHub là xong.\n"
        "\n"
        " 2. Dùng proxy: thêm vào .env rồi chạy lại\n"
        "       PROXY_URL=socks5://127.0.0.1:1080\n"
        "    (hoặc http://... nếu proxy của bạn là HTTP)\n"
        "\n"
        " 3. Bật VPN trên máy này rồi chạy lại.\n"
        "\n"
        " 4. Mạng chỉ chậm chứ không chặn hẳn thì nới thời gian chờ:\n"
        "       CONNECT_TIMEOUT=%s   (đang dùng, thử tăng lên 60)\n"
        "       BOOTSTRAP_RETRIES=%s (đang dùng, -1 là thử lại mãi)\n"
        "==================================================================",
        cfg.connect_timeout, cfg.bootstrap_retries,
    )


if __name__ == "__main__":
    main()
