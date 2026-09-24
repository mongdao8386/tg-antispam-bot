"""Acc seeding không bao giờ được coi là chiến dịch, và nội dung họ đăng được tha.

Các con số trong file này là từ sự cố thật 24/09: 5 acc seeding cùng đăng một
tấm quảng cáo, bộ nhớ chiến dịch đếm đủ ngưỡng, acc thứ 6 chưa kịp vào danh
sách bị ban ở 20 nhóm trong 18 giây. 176 lượt ban acc seeding trong 30 ngày,
168 trong số đó do luật chiến dịch.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot.storage import GLOBAL, Storage
from antispam_bot.vantay import van_tay

QC = "San XYZ uy tin nhat 2026, dang ky nhan ngay 100k trai nghiem - quang cao cua chu bot"


def _db() -> Storage:
    return Storage(Path(tempfile.mkdtemp()) / "thu.db")


def test_tha_noi_dung_cua_seeding():
    """Bài nào có acc seeding từng đăng thì được tha, bài khác thì không."""
    db = _db()
    v = van_tay(QC)
    for uid in (101, 102, 103):            # 3 acc đăng trước khi thành seeding
        db._ghi_noi_dung(v, QC, uid, -100 * uid)
    khac = "Hom nay troi dep qua moi nguoi oi, di ca phe khong ai di cung minh"
    v2 = van_tay(khac)
    db._ghi_noi_dung(v2, khac, 201, -100)
    db._ghi_noi_dung(v2, khac, 202, -100)

    assert not db._noi_dung_duoc_tha(v)
    n = db._tha_noi_dung_cua({102})        # chỉ một trong ba là seeding
    assert n == 1, n
    assert db._noi_dung_duoc_tha(v), "bài có acc seeding đăng phải được tha"
    assert not db._noi_dung_duoc_tha(v2), "bài không dính seeding thì không được tha nhầm"
    # Gọi lại không tha thêm gì (idempotent), không nổ.
    assert db._tha_noi_dung_cua({102, 999}) == 0
    assert db._tha_noi_dung_cua(set()) == 0


def test_tha_theo_ca_chu_lan_anh():
    db = _db()
    v_chu = van_tay(QC)
    v_anh = 0x5A5A5A5A5A5A5A5A            # giả một pHash
    db._ghi_noi_dung(v_chu, QC, 7, -1, "t")
    db._ghi_noi_dung(v_anh, "", 7, -1, "a")
    assert db._tha_noi_dung_cua({7}) == 2
    assert db._noi_dung_duoc_tha(v_chu, "t") and db._noi_dung_duoc_tha(v_anh, "a")
    assert not db._noi_dung_duoc_tha(v_anh, "t"), "tha ảnh không được tha nhầm sang chữ"


def test_chien_dich_khong_con_sau_khi_tha():
    """Sau khi tha, bài của chủ bot biến khỏi danh sách chiến dịch."""
    db = _db()
    v = van_tay(QC)
    for uid in range(1, 6):
        db._ghi_noi_dung(v, QC, uid, -100 * uid)
    assert len(db._cac_chien_dich(3, 10)) == 1
    db._tha_noi_dung_cua({3})
    assert db._cac_chien_dich(3, 10) == []


def test_them_seeding_roi_van_ghi_duoc_luot_dang_moi():
    """Tha rồi thì acc mới đăng lại bài đó vẫn được ghi (để /campaigns đếm), nhưng
    noi_dung_duoc_tha vẫn True nên scan() sẽ không ban."""
    db = _db()
    v = van_tay(QC)
    db._ghi_noi_dung(v, QC, 1, -1)
    db._tha_noi_dung_cua({1})
    _, n = db._ghi_noi_dung(v, QC, 2, -1)
    assert n == 2 and db._noi_dung_duoc_tha(v)


def test_tra_username_cuc_bo_tu_starters():
    """Acc đã bấm Start thì /add_user @nick phải ra ID mà không cần hỏi Telegram."""
    db = _db()
    db._add_starter(8261190651, "Minh Quân 94", "onalswas")
    assert db._tim_uid_theo_username("@onalswas") == 8261190651
    assert db._tim_uid_theo_username("ONALSWAS") == 8261190651, "không phân biệt hoa thường"
    assert db._tim_uid_theo_username("@khong_co") is None
    assert db._tim_uid_theo_username("") is None
