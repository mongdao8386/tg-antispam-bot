"""Kiểm thử phần logic thuần của captcha (không cần Telegram)."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot.captcha import (
    NHO_NGAY,
    TRUOT_TOI_DA,
    DangCho,
    SoCaptcha,
    ban_phim,
    noi_dung,
)
from antispam_bot.storage import Storage


def _db() -> Storage:
    return Storage(Path(tempfile.mkdtemp()) / "thu.db")


def test_so_theo_doi_them_lay_xoa():
    so = SoCaptcha()
    so.them(DangCho(-100, 1, 55, time.time() + 60, "A"))
    assert so.lay(-100, 1).message_id == 55
    assert so.lay(-100, 2) is None
    assert so.xoa(-100, 1).ten == "A"
    assert so.lay(-100, 1) is None
    assert so.xoa(-100, 1) is None  # xoá lần hai không nổ


def test_dem_truot_va_quen():
    so = SoCaptcha()
    assert [so.ghi_truot(7) for _ in range(TRUOT_TOI_DA)] == list(range(1, TRUOT_TOI_DA + 1))
    so.quen_truot(7)
    assert so.ghi_truot(7) == 1, "qua captcha rồi phải xoá sạch tiền án trượt"


def test_don_muc_qua_han_lau():
    so = SoCaptcha()
    so.them(DangCho(-1, 1, 1, time.time() - 1000, "cu"))   # quá hạn từ lâu
    so.them(DangCho(-1, 2, 2, time.time() + 100, "moi"))   # còn hạn
    cu = so.don()
    assert [c.ten for c in cu] == ["cu"]
    assert so.lay(-1, 2) is not None


def test_nut_mang_dung_user_id():
    """Nút phải khoá theo user_id để người khác bấm hộ không có tác dụng."""
    kb = ban_phim(123456)
    assert kb.inline_keyboard[0][0].callback_data == "cap:123456"


def test_noi_dung_thoat_html():
    assert "&lt;b&gt;" in noi_dung("<b>x</b>", 120)
    assert "2 phút" in noi_dung("A", 120)
    assert "1 phút" in noi_dung("A", 30), "dưới một phút vẫn phải nói là 1 phút"


def test_nho_nguoi_da_qua_xuyen_nhom():
    db = _db()
    assert not db._da_qua_captcha(9, NHO_NGAY)
    db._ghi_qua_captcha(9)
    assert db._da_qua_captcha(9, NHO_NGAY)
    # Quá hạn nhớ thì hỏi lại.
    db._conn.execute("UPDATE captcha_da_qua SET ts = ?", (int(time.time()) - (NHO_NGAY + 1) * 86400,))
    db._conn.commit()
    assert not db._da_qua_captcha(9, NHO_NGAY)


def test_dot_vao_don_dap():
    """Đếm lượt vào trong cửa sổ trượt; ngoài cửa sổ thì rơi ra."""
    from collections import deque
    from antispam_bot.captcha import CUA_SO_DOT_VAO, ghi_luot_vao
    hang: deque = deque()
    for i in range(7):
        n = ghi_luot_vao(hang, 1000 + i, CUA_SO_DOT_VAO)
    assert n == 7
    # Quá cửa sổ: 7 lượt cũ rơi hết, chỉ còn lượt mới.
    assert ghi_luot_vao(hang, 1000 + CUA_SO_DOT_VAO + 10, CUA_SO_DOT_VAO) == 1


def test_sao_luu_tao_file_va_giu_dung_so_ban():
    """Sao lưu phải ra file mở được, và không giữ quá số bản cho phép."""
    import sqlite3
    db = _db()
    db._set_trusted(-1, 42, True)
    thu_muc = Path(tempfile.mkdtemp()) / "backup"
    # Giả vờ đã có nhiều bản cũ.
    thu_muc.mkdir()
    for d in ("20250101", "20250102", "20250103"):
        (thu_muc / f"antispam-{d}.db").write_bytes(b"cu")
    tep = db._sao_luu(thu_muc, giu=2)
    assert tep.exists() and tep.name.startswith("antispam-")
    con = sqlite3.connect(tep)
    assert con.execute("SELECT trusted FROM members WHERE user_id=42").fetchone()[0] == 1
    con.close()
    con_lai = sorted(f.name for f in thu_muc.glob("antispam-*.db"))
    assert len(con_lai) == 2 and con_lai[-1] == tep.name, con_lai


def test_is_trusted_khong_ghi_gi():
    db = _db()
    assert not db._is_trusted(-1, 5)
    db._set_trusted(-1, 5, True)
    assert db._is_trusted(-1, 5)
    # touch_member cộng msg_count, is_trusted thì không.
    _, dem, _ = db._touch_member(-1, 5)
    assert db._is_trusted(-1, 5)
    assert db._touch_member(-1, 5)[1] == dem + 1
