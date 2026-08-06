"""Kiểm thử giải mã QR đầu-cuối: tạo ảnh QR -> mã hoá PNG -> qrscan.decode().

Tự bỏ qua nếu máy không có OpenCV.
Chạy: python tests/test_qrscan.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot import qrscan
from antispam_bot.config import Config
from antispam_bot.detector import MessageFacts, analyse

CFG = Config(token="x", whitelist_domains={"t.me", "github.com", "youtube.com"})

PAYLOADS = [
    ("https://kubet-vip.top/dangky?ref=99", True),
    ("bitcoin:bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh?amount=0.5", True),
    ("https://t.me/+AbCdEfGhIjKlMn", True),
    ("Tuyen CTV online thu nhap 500k/ngay lien he zalo 0912345678", True),
    ("https://github.com/foo/bar", False),
    ("WIFI:S:PhongHop;T:WPA;P:matkhau123;;", False),
]


def make_qr_png(text: str, scale: int = 8) -> bytes | None:
    """Tạo ảnh PNG chứa mã QR. Trả về None nếu bản OpenCV không có encoder."""
    import cv2
    import numpy as np

    if not hasattr(cv2, "QRCodeEncoder_create"):
        return None
    encoder = cv2.QRCodeEncoder_create()
    qr = encoder.encode(text)              # ảnh nhị phân 0/255, mỗi ô 1 pixel
    qr = cv2.resize(qr, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    qr = cv2.copyMakeBorder(qr, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    ok, buf = cv2.imencode(".png", qr)
    return bytes(buf) if ok else None


async def run() -> int:
    if not qrscan.AVAILABLE:
        print(f"BỎ QUA: không nạp được OpenCV ({qrscan.UNAVAILABLE_REASON})")
        return 0

    probe = make_qr_png("test")
    if probe is None:
        print("BỎ QUA: bản OpenCV này không có QRCodeEncoder để tạo ảnh thử")
        return 0

    failures = 0
    print("== Giải mã QR từ ảnh thật ==")
    for payload, should_block in PAYLOADS:
        png = make_qr_png(payload)
        has_qr, decoded = await qrscan.decode(png)

        if not has_qr or not decoded:
            print(f"  [FAIL] không dò ra QR: {payload[:50]}")
            failures += 1
            continue
        if decoded[0] != payload:
            print(f"  [FAIL] giải sai:\n         mong đợi: {payload}\n         nhận được: {decoded[0]}")
            failures += 1
            continue

        v = analyse(MessageFacts(has_qr=True, qr_payloads=decoded), CFG)
        ok = v.is_spam == should_block
        failures += not ok
        verdict = "CHẶN" if v.is_spam else "cho qua"
        expect = "CHẶN" if should_block else "cho qua"
        print(f"  [{'OK ' if ok else 'FAIL'}] giải OK, {verdict} ({v.score}/{v.threshold}) "
              f"| mong đợi {expect} | {payload[:45]}")
        if not ok:
            print(f"         lý do: {v.reasons}")

    # Ảnh không có QR thì không được báo nhầm.
    import cv2
    import numpy as np

    blank = np.full((400, 400), 200, dtype=np.uint8)
    cv2.circle(blank, (200, 200), 90, 60, -1)
    png = bytes(cv2.imencode(".png", blank)[1])
    has_qr, decoded = await qrscan.decode(png)
    ok = not has_qr
    failures += not ok
    print(f"  [{'OK ' if ok else 'FAIL'}] ảnh thường không bị nhận nhầm là QR")

    print(f"\n{'TẤT CẢ ĐỀU ĐẠT' if failures == 0 else f'{failures} trường hợp SAI'}")
    return failures


def test_qr_roundtrip():
    assert asyncio.run(run()) == 0


if __name__ == "__main__":
    raise SystemExit(1 if asyncio.run(run()) else 0)
