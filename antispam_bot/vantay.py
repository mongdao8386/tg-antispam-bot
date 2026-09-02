"""Vân tay nội dung chịu được sửa đổi nhỏ (SimHash).

VẤN ĐỀ
Chống rải cũ so khớp CHÍNH XÁC tuyệt đối: kẻ spam chỉ cần thêm một emoji hay
đổi một chữ là thoát sạch. Trong khi chiến dịch thật luôn là cùng một bài
quảng cáo được xào lại vài chữ cho mỗi lần đăng.

CÁCH LÀM
SimHash 64 bit trên các cụm 3 ký tự liền nhau (shingle). Điểm mấu chốt: đổi
vài chữ chỉ làm LẬT VÀI BIT, chứ không đổi hẳn vân tay như hàm băm thường.
Hai bài giống nhau thì khoảng cách Hamming nhỏ.

    "Sàn XYZ uy tín nhất 2026, đăng ký nhận 100k"   ->  ...1011010
    "Sàn XYZ uy tín nhất 2026, đăng ký nhận 200k!"  ->  ...1011011   lệch 1 bit

TÌM NHANH TRONG DATABASE
Không thể quét toàn bộ bảng để tính Hamming với từng dòng. Nên cắt 64 bit
thành 4 băng 16 bit và đánh chỉ mục từng băng. Theo nguyên lý chuồng bồ câu:
nếu hai vân tay lệch nhau KHÔNG QUÁ 3 bit thì với 4 băng, chắc chắn có ít
nhất một băng trùng khít. Vậy chỉ cần tra 4 khoá chính xác là ra hết ứng
viên, rồi mới tính Hamming cho vài dòng đó.

Nhờ vậy tra cứu vẫn là tra khoá chính, không phải quét bảng.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from .normalize import squeeze_keep_accents

# Độ dài shingle. 3 ký tự là mức thường dùng cho văn bản ngắn: đủ nhỏ để một
# câu ngắn vẫn sinh ra nhiều đặc trưng, đủ lớn để không nhiễu.
CUM = 3

# Số băng và độ rộng mỗi băng. 8 x 8 = 64 bit.
SO_BANG = 8
RONG_BANG = 8

# Lệch tối đa bao nhiêu bit thì vẫn coi là một nội dung. Phải NHỎ HƠN số băng,
# nếu không nguyên lý chuồng bồ câu không còn đúng và sẽ bỏ sót ứng viên.
#
# Đo trên biến thể thật: thêm emoji / đổi hoa thường / thêm dấu chấm than đều
# lệch 0 bit; đổi con số tiền lệch 6; thêm một cụm ngắn lệch 5. Trong khi hai
# câu NỘI DUNG KHÁC HẲN lệch 24-35 bit. Khoảng cách giữa hai vùng rất rộng
# nên đặt 6 vẫn còn xa mức nhầm lẫn.
LECH_TOI_DA = 6

# Nội dung ngắn hơn mức này không lấy vân tay.
#
# Ngưỡng này là thứ giữ cho luật "nhiều tài khoản cùng đăng" không bắt oan.
# Câu chào hỏi, "cảm ơn mọi người", "chúc buổi sáng tốt lành" nhiều người
# cùng nói là chuyện thường ngày; 25 ký tự (khoảng 6-8 chữ tiếng Việt) đã
# vượt xa mấy câu xã giao đó.
TOI_THIEU = 25


# Mỗi bộ đếm chiếm 12 bit trong một số nguyên lớn duy nhất. Nhờ vậy cộng dồn
# 64 bộ đếm chỉ là MỘT phép cộng số nguyên, thay vì vòng lặp 64 bước cho từng
# cụm - đo được nhanh hơn 6 lần. 12 bit đếm tới 4095, mà tin nhắn đã bị cắt
# còn tối đa TOI_DA_KY_TU ký tự nên không bao giờ tràn.
_RONG_DEM = 12
_MAT_DEM = (1 << _RONG_DEM) - 1

# Chỉ lấy vân tay trên phần đầu tin nhắn. Bài quảng cáo nào cũng đã lộ hết
# trong vài dòng đầu, mà cắt lại thì một tin dài bất thường không kéo chậm
# cả nhóm.
TOI_DA_KY_TU = 400


# Băm từng cụm là phần tốn nhất, mà tiếng Việt chỉ có chừng vài nghìn cụm 3 ký
# tự hay gặp - nhớ lại là gần như luôn trúng.
@lru_cache(maxsize=100_000)
def _bam(cum: str) -> int:
    """Cụm ký tự -> đóng góp đã đóng gói sẵn cho 64 bộ đếm.

    Bit nào của hàm băm bằng 1 thì cộng 1 vào bộ đếm tương ứng. Bit bằng 0 thì
    không cộng gì - cuối cùng chỉ cần so bộ đếm với một nửa tổng số cụm là ra
    dấu, nên không cần trừ.
    """
    h = int.from_bytes(hashlib.blake2b(cum.encode(), digest_size=8).digest(), "big")
    goi = 0
    for b in range(64):
        if (h >> b) & 1:
            goi += 1 << (b * _RONG_DEM)
    return goi


def van_tay(chu: str) -> int | None:
    """SimHash 64 bit của một đoạn chữ. None nếu quá ngắn để đáng tính.

    Dùng bản dồn chữ GIỮ DẤU: "MUA NGAY!!!" và "mua ngay" ra cùng vân tay,
    nhưng "lựa đào" và "lừa đảo" vẫn khác nhau.
    """
    nen = squeeze_keep_accents(chu or "")[:TOI_DA_KY_TU]
    so_cum = len(nen) - CUM + 1
    if len(nen) < TOI_THIEU or so_cum < 1:
        return None

    goi = 0
    for i in range(so_cum):
        goi += _bam(nen[i:i + CUM])

    # Bit bật khi quá nửa số cụm có bit đó bằng 1.
    ket = 0
    for b in range(64):
        if ((goi >> (b * _RONG_DEM)) & _MAT_DEM) * 2 > so_cum:
            ket |= 1 << b
    return ket


def cac_bang(vt: int) -> list[tuple[int, int]]:
    """Cắt vân tay thành các (số băng, giá trị băng) để tra database."""
    mat = (1 << RONG_BANG) - 1
    return [(b, (vt >> (b * RONG_BANG)) & mat) for b in range(SO_BANG)]


def lech(a: int, b: int) -> int:
    """Số bit khác nhau giữa hai vân tay."""
    return (a ^ b).bit_count()


def giong_nhau(a: int, b: int) -> bool:
    return lech(a, b) <= LECH_TOI_DA


# SQLite lưu số nguyên có dấu 64 bit, mà vân tay của ta là 64 bit KHÔNG dấu.
# Số nào có bit cao nhất bằng 1 sẽ tràn khi ghi. Hai hàm này đổi qua lại.
_DAU = 1 << 63
_TRAN = 1 << 64


def sang_sqlite(vt: int) -> int:
    return vt - _TRAN if vt >= _DAU else vt


def tu_sqlite(vt: int) -> int:
    return vt + _TRAN if vt < 0 else vt
