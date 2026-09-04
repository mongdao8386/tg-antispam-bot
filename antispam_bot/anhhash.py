"""Vân tay tri giác cho ảnh (pHash).

VÌ SAO CẦN
19% số lượt ban không có một chữ nào - ảnh, QR, forward. Bộ nhớ chiến dịch
chỉ nhớ được chữ, nên mù hoàn toàn trước kiểu rải bằng ảnh.

`file_unique_id` của Telegram thì vô dụng ở đây: kẻ spam tải ảnh lên lại là
Telegram cấp mã mới, dù mắt người nhìn vẫn đúng tấm đó.

CÁCH LÀM
pHash: đưa ảnh về xám 32x32, biến đổi cosin rời rạc (DCT), lấy góc trên trái
8x8 - phần chứa những nét LỚN của ảnh - rồi so từng hệ số với trung vị. Nén
lại, đổi kích thước, chỉnh sáng nhẹ đều không đụng tới mấy nét lớn đó, nên
vân tay gần như không đổi.

Cùng khuôn 64 bit với vân tay chữ, nên dùng chung được bộ tra băng và phép
đo Hamming trong vantay.py.

ẢNH PHẲNG THÌ BỎ QUA
Đây là chỗ pHash hay bị chê oan. Ảnh gần như một màu (nền trắng, ảnh tối om)
cho vân tay vô nghĩa và đụng nhau hàng loạt. Nên đo độ tương phản trước, dưới
ngưỡng thì trả về None - thà bỏ lọt còn hơn gộp nhầm ba tấm ảnh trắng của ba
người thành một "chiến dịch".
"""

from __future__ import annotations

import logging

from .qrscan import AVAILABLE, cv2, np

log = logging.getLogger("antispam.anh")

# Cạnh ảnh trước khi DCT. 32 là mức chuẩn: đủ để giữ nét lớn, đủ nhỏ để nhanh.
CANH = 32

# Số hệ số DCT lấy làm bit. 8x8 = 64, bỏ hệ số đầu (DC - chỉ là độ sáng trung
# bình, đổi theo độ sáng nên không đáng tin) còn 63 bit.
KHOI = 8

# Độ lệch chuẩn tối thiểu của ảnh xám. Dưới mức này coi là ảnh phẳng.
NGUONG_PHANG = 8.0

# Độ phân tán tối thiểu của các hệ số DCT quanh trung vị. Ảnh có thể tương
# phản cao mà vẫn cho hệ số DCT dồn cục (ví dụ ảnh nhiễu thuần), lúc đó so với
# trung vị chỉ còn là tung đồng xu.
NGUONG_TAN = 1.0


def van_tay_anh(data: bytes) -> int | None:
    """pHash 64 bit của một tấm ảnh. None nếu không đọc được hoặc ảnh quá phẳng."""
    if not AVAILABLE or not data:
        return None
    try:
        anh = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        if anh is None or anh.size == 0:
            return None
        if float(anh.std()) < NGUONG_PHANG:
            return None

        nho = cv2.resize(anh, (CANH, CANH), interpolation=cv2.INTER_AREA)
        he_so = cv2.dct(np.float32(nho))[:KHOI, :KHOI].flatten()[1:]
        trung_vi = float(np.median(he_so))
        if float(np.abs(he_so - trung_vi).mean()) < NGUONG_TAN:
            return None

        vt = 0
        for i, gt in enumerate(he_so):
            if gt > trung_vi:
                vt |= 1 << i
        return vt
    except Exception as exc:  # ảnh hỏng, định dạng lạ - không đáng làm sập bot
        log.debug("Không lấy được vân tay ảnh: %s", exc)
        return None
