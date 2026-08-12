"""Soi vì sao một ảnh cụ thể không bị bắt là có QR.

Cách dùng:
    python tools/test-qr.py duong-dan-anh.jpg

Lưu ảnh spam về máy (bấm giữ ảnh trong Telegram -> Lưu ảnh), rồi chạy lệnh trên.
Script chạy đúng bộ giải mà bot đang dùng, sau đó thử thêm vài cách xử lý ảnh
để xem có cứu được không.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Không thấy file: {path}")
        return 2

    from antispam_bot import qrscan

    if not qrscan.AVAILABLE:
        print(f"OpenCV không nạp được: {qrscan.UNAVAILABLE_REASON}")
        print("Cài lại: pip install opencv-python-headless")
        return 1

    import cv2
    import numpy as np

    data = path.read_bytes()
    print(f"File   : {path.name}  ({len(data) / 1024:.0f} KB)")

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        print("Không giải mã được ảnh - file hỏng hoặc không phải ảnh.")
        return 1
    h, w = img.shape[:2]
    print(f"Kích cỡ: {w} x {h}")
    print()

    # 1) Đúng đường đi mà bot đang dùng.
    has, payloads = asyncio.run(qrscan.decode(data))
    print("=== Bộ giải của bot ===")
    if payloads and payloads[0]:
        print(f"  ĐỌC ĐƯỢC: {payloads[0][:120]}")
        print("\n  Bot đáng lẽ phải bắt được ảnh này. Nếu trong nhóm vẫn lọt,")
        print("  vấn đề nằm ở chỗ khác (SCAN_QR, quyền bot, hoặc người gửi được miễn trừ).")
        return 0
    print("  KHÔNG đọc được.")
    print()

    # 2) Thử các cách xử lý ảnh khác nhau để tìm hướng cải thiện.
    print("=== Thử thêm các cách xử lý ===")
    dets = []
    for name, factory in (("Aruco", cv2.QRCodeDetectorAruco), ("thường", cv2.QRCodeDetector)):
        try:
            dets.append((name, factory()))
        except Exception:
            pass
    try:
        dets.append(("WeChat", cv2.wechat_qrcode_WeChatQRCode()))
    except Exception:
        pass  # chỉ có trong opencv-contrib, không bắt buộc

    def try_all(im) -> str | None:
        for name, d in dets:
            try:
                if name == "WeChat":
                    res, _ = d.detectAndDecode(im)
                    if res and res[0]:
                        return f"{name}: {res[0][:90]}"
                    continue
                t, _, _ = d.detectAndDecode(im)
                if t:
                    return f"{name}: {t[:90]}"
                ok, dec, _, _ = d.detectAndDecodeMulti(im)
                if ok:
                    for s in dec:
                        if s:
                            return f"{name}: {s[:90]}"
            except cv2.error:
                pass
        return None

    variants: list[tuple[str, object]] = [("ảnh gốc", img)]
    for f in (1.5, 2.0, 3.0):
        variants.append((f"phóng to x{f}", cv2.resize(img, None, fx=f, fy=f,
                                                      interpolation=cv2.INTER_CUBIC)))
    variants.append(("nhị phân Otsu",
                     cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]))
    variants.append(("tăng tương phản", cv2.createCLAHE(2.0, (8, 8)).apply(img)))
    variants.append(("làm nét", cv2.filter2D(img, -1, np.array(
        [[0, -1, 0], [-1, 5, -1], [0, -1, 0]]))))

    # Cắt ảnh thành lưới 3x3 rồi soi từng ô: QR nhỏ nằm trong tờ rơi to
    # hay bị bộ dò bỏ sót khi soi toàn ảnh.
    for i in range(3):
        for j in range(3):
            y0, y1 = h * i // 3, h * (i + 1) // 3
            x0, x1 = w * j // 3, w * (j + 1) // 3
            pad_y, pad_x = (y1 - y0) // 6, (x1 - x0) // 6
            crop = img[max(0, y0 - pad_y):min(h, y1 + pad_y),
                       max(0, x0 - pad_x):min(w, x1 + pad_x)]
            crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            variants.append((f"cắt ô hàng{i + 1} cột{j + 1}", crop))

    found = False
    for label, im in variants:
        got = try_all(im)
        if got:
            print(f"  [ĐỌC ĐƯỢC] {label:24} -> {got}")
            found = True
        else:
            print(f"  [   -    ] {label}")

    print()
    if found:
        print("KẾT LUẬN: giải được nếu xử lý thêm. Gửi kết quả này để tôi thêm bước đó vào bot.")
    else:
        print("KẾT LUẬN: không bộ giải nào đọc nổi mã này.")
        print("Chữ quảng cáo trên ảnh cũng nằm trong pixel, bot không có OCR nên không đọc.")
        print("Muốn bắt loại tờ rơi này thì phải thêm OCR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
