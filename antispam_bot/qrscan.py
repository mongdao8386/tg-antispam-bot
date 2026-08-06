"""Giải mã mã QR trong ảnh.

Dùng OpenCV (pip cài được trên Windows, không cần DLL ngoài như pyzbar).
Nếu OpenCV không có sẵn thì module tự tắt và bot vẫn chạy bình thường -
chỉ mất khả năng đọc QR.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging

log = logging.getLogger("antispam.qr")

UNAVAILABLE_REASON = ""

try:
    # cv2 in thẳng ra stdout khi import hỏng; nuốt đi để log của bot sạch.
    with contextlib.redirect_stdout(io.StringIO()):
        import cv2
        import numpy as np

    AVAILABLE = True
except Exception as _exc:  # pragma: no cover - phụ thuộc tuỳ chọn
    # Không chỉ ImportError: trên Windows có Smart App Control / WDAC, DLL của
    # numpy bị chặn nạp và lỗi có thể ở dạng khác. Thiếu QR thì bot vẫn phải chạy.
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    AVAILABLE = False
    # Dòng cuối của traceback thường là nguyên nhân thật ("DLL load failed...").
    _lines = [ln.strip() for ln in str(_exc).splitlines() if ln.strip()]
    UNAVAILABLE_REASON = _lines[-1][:200] if _lines else type(_exc).__name__


def _build_detectors() -> list:
    """Bộ dò xếp theo độ nhạy giảm dần.

    QRCodeDetectorAruco (OpenCV >= 4.7) khoẻ hơn hẳn bản cổ điển - bản cũ bỏ sót
    QR ở ảnh nhỏ hoặc độ tương phản thấp, đúng kiểu ảnh spam hay gặp.
    """
    detectors = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    detectors.append(cv2.QRCodeDetector())
    return detectors


def _try_decode(detector, img) -> tuple[list[str], bool]:
    """Trả về (nội dung giải được, có nhìn thấy khung QR không)."""
    seen = False

    # detectAndDecodeMulti bắt được nhiều QR trong một ảnh ghép.
    try:
        ok, decoded, points, _straight = detector.detectAndDecodeMulti(img)
        if ok:
            seen = True
            texts = [s for s in decoded if s]
            if texts:
                return texts, True
    except cv2.error:
        pass

    try:
        text, points, _ = detector.detectAndDecode(img)
        if text:
            return [text], True
        if points is not None and len(points):
            seen = True
    except cv2.error:
        pass

    return [], seen


def _decode_sync(data: bytes) -> list[str]:
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []

    # Ảnh chụp màn hình điện thoại thường rất to: thu nhỏ cho nhanh.
    # Ảnh nhỏ thì phóng to - bộ dò cần vài pixel cho mỗi ô của mã.
    longest = max(img.shape[:2])
    if longest > 1600:
        img = cv2.resize(img, None, fx=1600 / longest, fy=1600 / longest,
                         interpolation=cv2.INTER_AREA)
    elif longest < 600:
        factor = 600 / max(longest, 1)
        img = cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)

    # Biến thể thứ hai cho ảnh mờ / chụp nghiêng / nền màu.
    variants = [img]
    try:
        variants.append(cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
    except cv2.error:
        pass

    detectors = _build_detectors()
    for variant in variants:
        for detector in detectors:
            texts, _seen = _try_decode(detector, variant)
            if texts:
                return texts

    # CỐ Ý không báo gì khi chỉ "dò ra khung QR mà không đọc được".
    # Bộ dò của OpenCV nhận nhầm hoa văn ảnh thường (hạt cơm, viền bát, vân
    # vải, lá cây) thành khung định vị QR. Thực tế đo trên nhóm: 15/15 lần ban
    # vì QR đều đến từ nhánh này và đều là oan - không lần nào là QR thật.
    # QR spam vốn phải quét được thì mới lừa được ai, nên luôn giải mã ra chữ.
    return []


async def decode(data: bytes) -> tuple[bool, list[str]]:
    """Trả về (có thấy QR không, danh sách nội dung giải được).

    Nội dung có thể rỗng khi dò ra khung QR nhưng không đọc được - trường hợp
    đó vẫn cần biết là "ảnh này có QR".
    """
    if not AVAILABLE or not data:
        return False, []
    try:
        results = await asyncio.to_thread(_decode_sync, data)
    except Exception as exc:  # ảnh hỏng, định dạng lạ...
        log.debug("Không giải mã được ảnh: %s", exc)
        return False, []
    payloads = [r for r in results if r]
    return bool(results), payloads
