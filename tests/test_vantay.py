"""Kiểm thử vân tay nội dung và bộ nhớ chiến dịch xuyên nhóm.

Các con số trong file này lấy từ chiến dịch thật đã đo được trong nhóm: 334
tài khoản, 16 nhóm, cùng một bài, kéo dài 27 ngày.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot.storage import Storage
from antispam_bot.vantay import (
    LECH_TOI_DA,
    TOI_THIEU,
    cac_bang,
    giong_nhau,
    lech,
    sang_sqlite,
    tu_sqlite,
    van_tay,
)

BAI = "San XYZ uy tin nhat 2026, dang ky nhan ngay 100k trai nghiem"

# Cách kẻ spam xào lại bài để né so khớp chính xác. Tất cả PHẢI bị gộp chung.
XAO_LAI = [
    ("y hệt", BAI),
    ("thêm emoji", BAI + " 🔥🔥🔥"),
    ("đổi con số", BAI.replace("100k", "200k")),
    ("viết hoa + chấm than", BAI.upper().replace(",", " -") + "!!!"),
    ("thêm một cụm ngắn", BAI + " nhe ban oi"),
    ("chèn dấu chấm giữa chữ", BAI.replace("San", "S.a.n")),
]

# Nội dung thật sự khác. KHÔNG được gộp chung.
KHAC_HAN = [
    "Hom nay troi dep qua moi nguoi oi, di ca phe khong ai di cung minh",
    "Chuc mung sinh nhat ban nhe, chuc ban luon vui ve va thanh cong nhieu",
    "Ban nao biet cach fix loi nay khong, minh doc doc ma van chua hieu gi",
    BAI.replace("XYZ", "ABCD"),  # đổi hẳn tên sàn = bài khác
]


def _db() -> Storage:
    return Storage(Path(tempfile.mkdtemp()) / "thu.db")


# --- Vân tay --------------------------------------------------------------

def test_xao_lai_van_gop_chung():
    goc = van_tay(BAI)
    for ten, bien in XAO_LAI:
        v = van_tay(bien)
        assert giong_nhau(goc, v), f"{ten}: lệch {lech(goc, v)} bit, đáng lẽ phải gộp"


def test_noi_dung_khac_thi_khong_gop():
    goc = van_tay(BAI)
    for chu in KHAC_HAN:
        v = van_tay(chu)
        assert not giong_nhau(goc, v), f"gộp nhầm (lệch {lech(goc, v)}): {chu[:40]}"


def test_qua_ngan_thi_bo_qua():
    """Câu xã giao ngắn không lấy vân tay - nếu không sẽ bắt oan hàng loạt."""
    for chu in ("ok", "cảm ơn nhé", "chào cả nhà", "vâng ạ", ""):
        assert van_tay(chu) is None, chu
    assert len("x" * TOI_THIEU) >= TOI_THIEU


def test_chuong_bo_cau():
    """Lệch <= LECH_TOI_DA thì BẮT BUỘC có ít nhất một băng trùng khít.

    Đây là điều kiện để tra database bằng khoá chính thay vì quét cả bảng.
    Sai điều kiện này là bỏ sót chiến dịch mà không ai biết.
    """
    goc = van_tay(BAI)
    bang_goc = set(cac_bang(goc))
    for ten, bien in XAO_LAI:
        v = van_tay(bien)
        if lech(goc, v) <= LECH_TOI_DA:
            assert bang_goc & set(cac_bang(v)), ten


def test_doi_qua_lai_sqlite():
    """SQLite lưu số có dấu, vân tay là 64 bit không dấu - phải khớp cả hai chiều."""
    for v in (0, 1, van_tay(BAI), 2**63, 2**63 - 1, 2**64 - 1):
        assert tu_sqlite(sang_sqlite(v)) == v


# --- Bộ nhớ chiến dịch ----------------------------------------------------

def test_dem_tai_khoan_xuyen_nhom():
    """Ba tài khoản ở BA NHÓM KHÁC NHAU vẫn phải cộng dồn thành một chiến dịch."""
    db = _db()
    v = van_tay(BAI)
    dem = [db._ghi_noi_dung(v, BAI, uid, nhom)[1]
           for uid, nhom in ((1, -100), (2, -200), (3, -300))]
    assert dem == [1, 2, 3], dem


def test_mot_nguoi_dang_nhieu_lan_van_la_mot():
    db = _db()
    v = van_tay(BAI)
    for _ in range(5):
        _, n = db._ghi_noi_dung(v, BAI, 42, -100)
    assert n == 1, f"một người đăng 5 lần bị tính thành {n} tài khoản"


def test_xao_lai_gop_vao_chien_dich_cu():
    db = _db()
    chinh, _ = db._ghi_noi_dung(van_tay(BAI), BAI, 1, -100)
    for i, (ten, bien) in enumerate(XAO_LAI[1:], start=2):
        vt, n = db._ghi_noi_dung(van_tay(bien), bien, i, -100)
        assert vt == chinh, f"{ten}: tách thành chiến dịch riêng"
    assert n == len(XAO_LAI), n


def test_noi_dung_khac_khong_gop():
    db = _db()
    db._ghi_noi_dung(van_tay(BAI), BAI, 1, -100)
    for i, chu in enumerate(KHAC_HAN, start=2):
        _, n = db._ghi_noi_dung(van_tay(chu), chu, i, -100)
        assert n == 1, f"gộp nhầm vào chiến dịch: {chu[:40]}"


def test_tha_noi_dung():
    db = _db()
    v = van_tay(BAI)
    db._ghi_noi_dung(v, BAI, 1, -100)
    assert not db._noi_dung_duoc_tha(v)
    db._tha_noi_dung(v)
    assert db._noi_dung_duoc_tha(v)


def test_don_dep_giu_lai_chien_dich():
    """Dọn bộ nhớ phải bỏ bài một người đăng, nhưng GIỮ bằng chứng chiến dịch."""
    db = _db()
    v_mot = van_tay(BAI)
    db._ghi_noi_dung(v_mot, BAI, 1, -100)
    chu2 = KHAC_HAN[0]
    v_nhieu = van_tay(chu2)
    for uid in (10, 11, 12):
        db._ghi_noi_dung(v_nhieu, chu2, uid, -100)

    db._conn.execute("UPDATE noi_dung SET lan_cuoi = 0")   # giả vờ đã rất cũ
    db._conn.commit()
    assert db._don_noi_dung(30) == 1, "phải xoá đúng bài chỉ một người đăng"
    assert db._tim_gan_giong(v_mot) is None
    assert db._tim_gan_giong(v_nhieu) == v_nhieu, "đã xoá mất bằng chứng chiến dịch"


def test_liet_ke_chien_dich():
    db = _db()
    for uid in (1, 2, 3, 4):
        db._ghi_noi_dung(van_tay(BAI), BAI, uid, -100 * uid)
    cds = db._cac_chien_dich(3, 10)
    assert len(cds) == 1
    so_acc, so_nhom, _, loai = cds[0]
    assert (so_acc, so_nhom, loai) == (4, 4, "t"), cds

    # Tha rồi thì không còn bị coi là chiến dịch nữa.
    db._tha_noi_dung(van_tay(BAI))
    assert db._cac_chien_dich(3, 10) == []
