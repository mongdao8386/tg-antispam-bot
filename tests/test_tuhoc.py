"""Kiểm thử vân tay ảnh (pHash) và bộ tự học từ những lần gỡ ban."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot.anhhash import AVAILABLE, van_tay_anh
from antispam_bot.storage import Storage
from antispam_bot.tuhoc import CONG_TAC_CUA_LUAT, ten_luat
from antispam_bot.vantay import giong_nhau, lech, van_tay

cv2 = pytest.importorskip("cv2") if AVAILABLE else None
np = pytest.importorskip("numpy") if AVAILABLE else None
can_anh = pytest.mark.skipif(not AVAILABLE, reason="cần OpenCV")


def _db() -> Storage:
    return Storage(Path(tempfile.mkdtemp()) / "thu.db")


def _anh(seed: int):
    """Một tấm ảnh quảng cáo giả lập, khác nhau theo seed."""
    r = np.random.default_rng(seed)
    im = np.full((600, 800, 3), 240, np.uint8)
    for i in range(6):
        y = 60 + i * 80
        cv2.rectangle(im, (40, y), (40 + int(r.integers(200, 700)), y + 50),
                      tuple(int(x) for x in r.integers(0, 200, 3)), -1)
    cv2.putText(im, "SAN XYZ UY TIN", (60, 560), cv2.FONT_HERSHEY_SIMPLEX,
                1.6, (10, 10, 10), 4)
    return im


def _jpg(im, q: int = 92) -> bytes:
    return cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()


# --- Vân tay ảnh ----------------------------------------------------------

@can_anh
def test_cung_anh_du_bi_bien_dang():
    """Tải lên lại là Telegram cấp file_unique_id mới, nên phải nhận ra bằng mắt."""
    goc = _anh(1)
    v0 = van_tay_anh(_jpg(goc))
    bien = {
        "nén JPEG q=15": _jpg(goc, 15),
        "thu nhỏ một nửa": _jpg(cv2.resize(goc, (400, 300))),
        "phóng to 150%": _jpg(cv2.resize(goc, (1200, 900))),
        "chỉnh sáng +20": _jpg(cv2.add(goc, 20)),
    }
    for ten, data in bien.items():
        v = van_tay_anh(data)
        assert giong_nhau(v0, v), f"{ten}: lệch {lech(v0, v)} bit, đáng lẽ phải gộp"


@can_anh
def test_anh_khac_thi_khong_gop():
    v0 = van_tay_anh(_jpg(_anh(1)))
    for seed in (2, 3, 4, 5):
        v = van_tay_anh(_jpg(_anh(seed)))
        assert not giong_nhau(v0, v), f"gộp nhầm hai ảnh khác (lệch {lech(v0, v)})"


@can_anh
def test_anh_phang_thi_bo_qua():
    """Ảnh gần một màu cho vân tay vô nghĩa và đụng nhau hàng loạt."""
    phang = {
        "trắng trơn": np.full((400, 400, 3), 255, np.uint8),
        "đen trơn": np.zeros((400, 400, 3), np.uint8),
        "xám nhạt": np.full((400, 400, 3), 128, np.uint8),
    }
    for ten, im in phang.items():
        assert van_tay_anh(_jpg(im)) is None, ten
    assert van_tay_anh(b"") is None
    assert van_tay_anh(b"khong phai anh") is None


@can_anh
def test_van_tay_anh_khong_lan_voi_van_tay_chu():
    """Hai loại dùng chung bảng nên PHẢI đếm riêng, không được cộng vào nhau."""
    db = _db()
    va = van_tay_anh(_jpg(_anh(1)))
    vc = van_tay("San XYZ uy tin nhat 2026, dang ky nhan ngay 100k trai nghiem")
    db._ghi_noi_dung(va, "", 1, -100, "a")
    db._ghi_noi_dung(va, "", 2, -100, "a")
    _, n_chu = db._ghi_noi_dung(vc, "x", 3, -100, "t")
    assert n_chu == 1, "vân tay chữ bị cộng nhầm vào vân tay ảnh"

    # Cùng giá trị số nhưng khác loại thì vẫn là hai mối riêng.
    _, n_a = db._ghi_noi_dung(va, "", 9, -100, "a")
    _, n_t = db._ghi_noi_dung(va, "y", 9, -100, "t")
    assert (n_a, n_t) == (3, 1), (n_a, n_t)


@can_anh
def test_chien_dich_bang_anh():
    db = _db()
    goc = _anh(7)
    # Bốn tài khoản, bốn nhóm, cùng tấm ảnh nhưng nén khác nhau.
    dem = [db._ghi_noi_dung(van_tay_anh(_jpg(goc, q)), "", uid, -100 * uid, "a")[1]
           for uid, q in ((1, 95), (2, 70), (3, 45), (4, 20))]
    assert dem == [1, 2, 3, 4], dem
    cds = db._cac_chien_dich(3, 10)
    assert len(cds) == 1 and cds[0][3] == "a", cds


@can_anh
def test_tha_anh():
    db = _db()
    v = van_tay_anh(_jpg(_anh(3)))
    db._ghi_noi_dung(v, "", 1, -100, "a")
    assert not db._noi_dung_duoc_tha(v, "a")
    db._tha_noi_dung(v, "a")
    assert db._noi_dung_duoc_tha(v, "a")
    assert not db._noi_dung_duoc_tha(v, "t"), "tha ảnh mà tha luôn cả chữ"


# --- Tự học ---------------------------------------------------------------

def test_rut_ten_luat():
    """Lý do có chi tiết thay đổi mỗi lần, phải quy về một tên để cộng dồn."""
    mau = {
        "link lạ: kubet88.xyz, abc.top": ["link lạ"],
        "12 tài khoản khác nhau cùng đăng bài này (chiến dịch rải)": ["chiến dịch rải"],
        "4 tài khoản khác nhau cùng đăng một tấm ảnh (chiến dịch rải)": ["chiến dịch rải"],
        "đồng phạm trong chiến dịch rải hàng loạt": ["chiến dịch rải"],
        "rải 12 tin trong 10 giây": ["dồn tin"],
        "gửi lại cùng một nội dung 4 lần": ["lặp nội dung"],
        "tin nhắn chuyển tiếp từ kênh ABC": ["tin nhắn chuyển tiếp"],
        "số điện thoại lạ: 0912345678": ["số điện thoại lạ"],
        "nhắc @ không được phép: @abc": ["nhắc @ không được phép"],
    }
    for ly_do, mong in mau.items():
        assert ten_luat(ly_do) == mong, (ly_do, ten_luat(ly_do))


def test_nhieu_luat_trong_mot_lan_ban():
    ra = ten_luat("link lạ: abc.com; nhắc @ không được phép: @x; tin chia sẻ story")
    assert ra == ["link lạ", "nhắc @ không được phép", "tin chia sẻ story"], ra


def test_chi_tu_tat_cong_tac_admin_bat_lai_duoc():
    """Ranh giới an toàn: bot không được tắt thứ mà admin không bật lại được."""
    from antispam_bot.control import CONG_TAC
    for luat, ct in CONG_TAC_CUA_LUAT.items():
        assert ct in CONG_TAC, f"'{luat}' tắt {ct} nhưng /panel không có nút bật lại"


def test_dem_phieu_va_xoa():
    db = _db()
    for i in range(1, 4):
        assert db._ghi_phan_hoi("link lạ", f"vi du {i}") == i
    assert db._ghi_phan_hoi("dồn tin", "") == 1
    ph = dict((l, n) for l, n, _, _ in db._cac_phan_hoi(10))
    assert ph == {"link lạ": 3, "dồn tin": 1}, ph

    assert db._xoa_phan_hoi("link lạ") == 1
    assert [l for l, *_ in db._cac_phan_hoi(10)] == ["dồn tin"]
    db._xoa_phan_hoi(None)
    assert db._cac_phan_hoi(10) == []


def test_vi_du_khong_bi_ghi_de_bang_rong():
    db = _db()
    db._ghi_phan_hoi("link lạ", "câu ví dụ có ích")
    db._ghi_phan_hoi("link lạ", "")
    assert db._cac_phan_hoi(1)[0][3] == "câu ví dụ có ích"
