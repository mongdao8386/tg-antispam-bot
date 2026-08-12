"""Đọc chữ nằm trong ảnh (OCR) để soi từ cấm.

Vì sao cần: tờ rơi quảng cáo lừa đảo thường KHÔNG có caption - toàn bộ chữ
("lô nóng", "cầm giấy tờ", "hỗ trợ 24h") nằm trong pixel. Không có OCR thì bot
mù hoàn toàn trước loại này.

Tự tắt êm nếu thiếu Tesseract, giống qrscan - bot vẫn chạy bình thường.

Tối ưu tốc độ, theo thứ tự quan trọng:
  1. Nhớ kết quả theo file_unique_id. Spam thường rải CÙNG một ảnh hàng chục
     lần; lần thứ hai trở đi tốn 0ms.
  2. Thu ảnh về OCR_MAX_SIDE trước khi nhận dạng. Tesseract tỉ lệ thuận với số
     điểm ảnh, mà chữ quảng cáo vốn to nên thu nhỏ gần như không mất độ chính xác.
  3. Chỉ chạy MỘT lượt nhận dạng: tự xác định nền tối hay sáng rồi đảo màu nếu
     cần, thay vì thử cả hai chiều.
  4. --oem 1 --psm 6: dùng bộ LSTM, coi ảnh là một khối chữ. Nhanh hơn hẳn chế
     độ dò bố cục đầy đủ và hợp với tờ rơi.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
from collections import OrderedDict

log = logging.getLogger("antispam.ocr")

# Giới hạn số ảnh nhận dạng cùng lúc.
# pytesseract chạy tesseract bằng subprocess nên KHÔNG vướng GIL - chạy song
# song thật. Nhưng nó ngốn CPU, nên mở quá số nhân chỉ tổ tranh nhau và ngốn
# RAM: một đợt rải spam có thể đẻ ra hàng chục tiến trình tesseract cùng lúc
# và làm chết droplet 1GB. Đo được: 4 ảnh song song trên máy 4 nhân nhanh gấp
# 3.2 lần chạy lần lượt; quá 4 thì tổng thời gian tăng tuyến tính.
_MAX_PARALLEL = max(2, os.cpu_count() or 2)
_sem: asyncio.Semaphore | None = None


def _limiter() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_MAX_PARALLEL)
    return _sem

AVAILABLE = False
UNAVAILABLE_REASON = ""

LANGS: set[str] = set()

# Trên Windows, bộ cài không tự thêm vào PATH nên pytesseract không thấy.
# Dò sẵn mấy chỗ cài mặc định để người dùng khỏi phải sửa biến môi trường.
_WINDOWS_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
)


# Thư mục tessdata đi kèm project. Dùng khi không có quyền ghi vào chỗ cài
# Tesseract (Program Files cần admin) - đặt ở đây thì chép cả thư mục bot sang
# máy khác là chạy được ngay, không phải cài lại gói ngôn ngữ.
_LOCAL_TESSDATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tessdata")


def _locate(pytesseract) -> None:
    """Chỉ đường tới tesseract.exe và thư mục dữ liệu ngôn ngữ."""
    import shutil

    if not shutil.which("tesseract"):
        for path in _WINDOWS_PATHS:
            if path and os.path.isfile(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

    # TESSDATA_PREFIX thay thế hẳn đường dẫn mặc định, nên thư mục cục bộ phải
    # có đủ cả eng lẫn vie - đã chép sẵn.
    if os.path.isdir(_LOCAL_TESSDATA) and os.path.isfile(
        os.path.join(_LOCAL_TESSDATA, "vie.traineddata")
    ):
        os.environ["TESSDATA_PREFIX"] = _LOCAL_TESSDATA


try:  # pragma: no cover - phụ thuộc môi trường
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import cv2
        import numpy as np
        import pytesseract

        _locate(pytesseract)
        # Gọi thử: pytesseract nạp được không có nghĩa là có sẵn Tesseract.
        _ver = pytesseract.get_tesseract_version()
        try:
            LANGS = set(pytesseract.get_languages(config=""))
        except Exception:  # noqa: BLE001 - bản cũ không có hàm này
            LANGS = set()
    AVAILABLE = True
except Exception as exc:  # noqa: BLE001 - môi trường có thể lỗi đủ kiểu
    detail = str(exc).strip().splitlines()
    UNAVAILABLE_REASON = detail[-1] if detail else exc.__class__.__name__


def resolve_lang(want: str) -> str:
    """Bỏ bớt ngôn ngữ chưa cài, tránh Tesseract lỗi rồi trả về rỗng âm thầm.

    Thiếu vie mà vẫn yêu cầu 'vie+eng' thì Tesseract báo lỗi và bot mất luôn OCR
    thay vì chạy đỡ bằng eng.
    """
    if not LANGS:
        return want
    parts = [p for p in want.split("+") if p]
    have = [p for p in parts if p in LANGS]
    missing = [p for p in parts if p not in LANGS]
    if missing:
        log.warning(
            "Thiếu dữ liệu ngôn ngữ OCR: %s. Đang dùng: %s. "
            "Chữ tiếng Việt có dấu sẽ đọc sai nhiều.",
            "+".join(missing), "+".join(have) or "eng",
        )
    return "+".join(have) or "eng"

# Ảnh đã đọc rồi thì không đọc lại. Đủ lớn để chống đợt rải spam,
# đủ nhỏ để không phình bộ nhớ.
_CACHE_MAX = 512
_cache: OrderedDict[str, str] = OrderedDict()


def cache_stats() -> tuple[int, int]:
    return len(_cache), _CACHE_MAX


def _prep(data: bytes, max_side: int):
    """Giải mã, thu nhỏ, tự xoay chiều sáng-tối, nhị phân hoá."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None

    longest = max(img.shape[:2])
    if longest > max_side:
        f = max_side / longest
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    elif longest < 320:
        # Ảnh quá bé thì phóng lên, không Tesseract không thấy nét chữ.
        f = 320 / max(longest, 1)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)

    # Tờ rơi hay dùng chữ sáng trên nền tối; Tesseract cần chữ tối trên nền sáng.
    if img.mean() < 110:
        img = cv2.bitwise_not(img)

    return cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def _read_sync(data: bytes, lang: str, max_side: int) -> str:
    img = _prep(data, max_side)
    if img is None:
        return ""
    try:
        return pytesseract.image_to_string(img, lang=lang, config="--oem 1 --psm 6")
    except Exception as exc:  # noqa: BLE001
        log.debug("OCR lỗi: %s", exc)
        return ""


async def read(
    data: bytes,
    key: str | None = None,
    lang: str = "vie+eng",
    max_side: int = 1600,
) -> str:
    """Chữ đọc được trong ảnh. Chuỗi rỗng nếu không có gì hoặc OCR không chạy được.

    `key` là file_unique_id của Telegram - truyền vào để dùng bộ nhớ đệm.
    """
    if not AVAILABLE or not data:
        return ""

    if key is not None:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit

    # Tesseract nặng thật (hàng trăm ms) nên đẩy sang thread là đúng,
    # khác hẳn các truy vấn SQLite vốn chỉ vài µs.
    async with _limiter():
        text = await asyncio.to_thread(_read_sync, data, resolve_lang(lang), max_side)
    text = " ".join(text.split())

    if key is not None:
        _cache[key] = text
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return text
