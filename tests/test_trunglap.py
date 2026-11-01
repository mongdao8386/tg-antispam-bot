"""Chống ảnh/video đăng lại: vân tay, bộ nhớ trong database, và xoá + báo.

Ca quan trọng nhất ở đây là những ca KHÔNG được xoá: người được miễn, chính
người đó vừa đăng lại để sửa chú thích, nhóm không bật, tin sửa, chế độ report.
Chủ bot ghét xoá/ban oan hơn mọi thứ.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Chat, Message, PhotoSize, User, Video

from antispam_bot import bot as B
from antispam_bot import trunglap
from antispam_bot.anhhash import AVAILABLE, van_tay_anh
from antispam_bot.config import Config
from antispam_bot.storage import Storage
from antispam_bot.trunglap import bo_so, giai_ma, giong_nhau, ma_hoa, van_tay_video

cv2 = pytest.importorskip("cv2") if AVAILABLE else None
np = pytest.importorskip("numpy") if AVAILABLE else None
can_anh = pytest.mark.skipif(not AVAILABLE, reason="cần OpenCV")

NHOM, NHOM_KHAC = -1001234567890, -1009999999999
LECH = 5
TUAN = 7 * 86400


def _db() -> Storage:
    return Storage(Path(tempfile.mkdtemp()) / "thu.db")


def _anh(seed: int):
    r = np.random.default_rng(seed)
    im = np.full((600, 800, 3), 240, np.uint8)
    for i in range(6):
        y = 60 + i * 80
        cv2.rectangle(im, (40, y), (40 + int(r.integers(200, 700)), y + 50),
                      tuple(int(x) for x in r.integers(0, 200, 3)), -1)
    cv2.putText(im, "BAN XE MAY CU", (60, 560), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (10, 10, 10), 4)
    return im


def _jpg(im, q: int = 92) -> bytes:
    return cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()


def _video(duong_dan: Path, seed: int, w=320, h=240, fps=25, giay=6, doi_tu: float = 0):
    """Video giả lập: bốn khối tròn trôi ngang. Nội dung là hàm của THỜI GIAN,
    không phải của số khung hay độ phân giải - nên quay lại ở cỡ/fps khác vẫn ra
    đúng những cảnh đó. Từ giây doi_tu (nếu > 0) trở đi thì đổi sang cảnh khác."""
    def ve(f, r_seed, t):
        r = np.random.default_rng(r_seed)
        for k in range(4):
            mau = tuple(int(x) for x in r.integers(40, 255, 3))
            x0, y0 = r.random(), r.random()
            x = int(((x0 + 0.12 * t * (k + 1)) % 1) * w)
            cv2.circle(f, (x, int(y0 * h)), int(min(w, h) * 0.18), mau, -1)

    vw = cv2.VideoWriter(str(duong_dan), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(int(fps * giay)):
        t = i / fps
        f = np.full((h, w, 3), 25, np.uint8)
        ve(f, seed + (1000 if doi_tu and t >= doi_tu else 0), t)
        vw.write(f)
    vw.release()
    return duong_dan


# --- Mã hoá và so sánh ----------------------------------------------------

def test_ma_hoa_giai_ma():
    assert ma_hoa([0xABC]) == "0000000000000abc"
    assert giai_ma(ma_hoa([1, None, 2**63 + 5])) == [1, None, 2**63 + 5]
    assert ma_hoa([None]) == "" and ma_hoa([None, None, None]) == "" and ma_hoa([]) == ""
    assert giai_ma("rac,,0f") == [None, None, 15]


def test_so_video_can_du_khung_va_du_gan():
    a = [0, 0b111, 0]
    assert giong_nhau(a, [0, 0b111, 0b11], LECH)
    assert not giong_nhau(a, [0, 0b111, 2**40 - 1], LECH), "một khung lệch hẳn là video khác"
    # Chỉ một khung so được: chưa nói lên gì (cùng logo mở đầu).
    assert not giong_nhau([0, None, None], [0, 5, 7], LECH)
    assert giong_nhau([0, None, 3], [1, 9, 3], LECH)
    # Ảnh chỉ có một vân tay.
    assert giong_nhau([0], [0b11111], LECH) and not giong_nhau([0], [0b111111], LECH)
    assert not giong_nhau([None], [None], LECH)


def test_lech_thoi_luong_thi_khong_phai_mot():
    so = bo_so([0, 0, 0], 30, LECH)
    h = ma_hoa([0, 0, 0])
    assert so(h, 30) and so(h, 31) and so(h, 0)
    assert not so(h, 32)


# --- Vân tay ảnh ở ngưỡng chống trùng --------------------------------------

@can_anh
def test_anh_dang_lai_qua_nen_doi_co_van_khop():
    goc = _anh(1)
    v0 = van_tay_anh(_jpg(goc))
    for ten, data in {
        "nén JPEG q=40": _jpg(goc, 40),
        "thu nhỏ một nửa": _jpg(cv2.resize(goc, (400, 300))),
        "phóng to 150%": _jpg(cv2.resize(goc, (1200, 900))),
    }.items():
        assert giong_nhau([v0], [van_tay_anh(data)], LECH), ten
    for seed in (2, 3, 4, 5, 6):
        assert not giong_nhau([v0], [van_tay_anh(_jpg(_anh(seed)))], LECH), seed


# --- Vân tay video ----------------------------------------------------------

@can_anh
def test_video_quay_lai_co_khac_van_khop(tmp_path):
    goc = asyncio.run(van_tay_video(str(_video(tmp_path / "a.mp4", 1)), 6))
    assert len(goc) == 3 and all(v is not None for v in goc), goc
    lai = asyncio.run(van_tay_video(
        str(_video(tmp_path / "b.mp4", 1, w=480, h=360, fps=30)), 6
    ))
    assert giong_nhau(goc, lai, LECH), [bin(x ^ y).count("1") for x, y in zip(goc, lai)]


@can_anh
def test_video_khac_khong_khop(tmp_path):
    goc = asyncio.run(van_tay_video(str(_video(tmp_path / "a.mp4", 1)), 6))
    khac = asyncio.run(van_tay_video(str(_video(tmp_path / "b.mp4", 2)), 6))
    assert not giong_nhau(goc, khac, LECH)
    # Chung cảnh mở đầu, phần sau khác hẳn: không phải một video.
    chung_dau = asyncio.run(van_tay_video(str(_video(tmp_path / "c.mp4", 1, doi_tu=1.5)), 6))
    assert goc[0] is not None and giong_nhau([goc[0]], [chung_dau[0]], LECH)
    assert not giong_nhau(goc, chung_dau, LECH)


def test_file_khong_doc_duoc_thi_rong(tmp_path):
    hong = tmp_path / "hong.mp4"
    hong.write_bytes(b"khong phai video")
    assert asyncio.run(van_tay_video(str(hong), 5)) == []
    assert asyncio.run(van_tay_video(str(tmp_path / "khong-co.mp4"), 5)) == []


# --- Bộ nhớ trong database -------------------------------------------------

def _xet(db, uid, *, uid_file="", h="", chat=NHOM, mid=1, loai="photo", d=0, ghi=True):
    vt = giai_ma(h)
    return db._media_trung_hoac_ghi(
        chat, mid, uid, loai, uid_file, h, d, TUAN, B.CHO_SUA_GIAY,
        bo_so(vt, d, LECH), ghi,
    )


def test_cung_file_nguoi_khac_dang_lai():
    db = _db()
    assert _xet(db, 1, uid_file="F1", mid=10) is None
    cu = _xet(db, 2, uid_file="F1", mid=11)
    assert cu is not None and cu[:2] == (10, 1)
    # Bản trùng không được ghi: nó sắp bị xoá.
    assert db._conn.execute("SELECT COUNT(*) FROM media_hashes").fetchone()[0] == 1


def test_van_tay_gan_giong_va_khac_nhom():
    db = _db()
    assert _xet(db, 1, uid_file="F1", h=ma_hoa([0b1010]), mid=10) is None
    assert _xet(db, 2, uid_file="F2", h=ma_hoa([0b1010 ^ 0b11111]), mid=11)[0] == 10
    assert _xet(db, 3, uid_file="F3", h=ma_hoa([0b1010 ^ 0b111111]), mid=12) is None
    assert _xet(db, 4, uid_file="F1", h=ma_hoa([0b1010]), chat=NHOM_KHAC) is None, \
        "nhóm khác không tính"
    # Ảnh không có vân tay (ảnh phẳng) thì chỉ so được file y hệt.
    assert _xet(db, 5, uid_file="F9", h="", mid=13) is None


def test_anh_va_video_khong_lan():
    db = _db()
    _xet(db, 1, uid_file="V1", h=ma_hoa([7, 7, 7]), loai="video", d=10)
    assert _xet(db, 2, uid_file="P1", h=ma_hoa([7]), loai="photo") is None


def test_chinh_nguoi_do_dang_lai_ngay_thi_cho_qua():
    db = _db()
    assert _xet(db, 1, uid_file="F1", mid=10) is None
    assert _xet(db, 1, uid_file="F1", mid=11) is None, "xoá đi đăng lại để sửa chú thích"
    # Quá thời gian cho sửa: đăng lại để đẩy bài.
    db._conn.execute("UPDATE media_hashes SET created_at = created_at - 3600")
    assert _xet(db, 1, uid_file="F1", mid=12)[0] == 10


def test_qua_han_thi_quen_va_bi_don():
    db = _db()
    _xet(db, 1, uid_file="F1", mid=10)
    db._conn.execute("UPDATE media_hashes SET created_at = created_at - ?", (TUAN + 60,))
    assert _xet(db, 2, uid_file="F1", mid=11) is None
    assert db._don_media(7) == 1
    assert db._conn.execute("SELECT COUNT(*) FROM media_hashes").fetchone()[0] == 1


def test_chi_tra_thi_khong_ghi():
    db = _db()
    assert _xet(db, 1, uid_file="F1", ghi=False) is None
    assert db._conn.execute("SELECT COUNT(*) FROM media_hashes").fetchone()[0] == 0


# --- Đầu-cuối qua handler scan ---------------------------------------------

class _Bot:
    def __init__(self, video_tu: dict[str, Path] | None = None):
        self.da_xoa: list[tuple[int, int]] = []
        self.gui: list[tuple[int, str, dict]] = []
        self.video_tu = video_tu or {}
        self.so_lan_tai = 0

    async def delete_message(self, chat_id, message_id, **_):
        self.da_xoa.append((chat_id, message_id))
        return True

    async def send_message(self, chat_id, text, **kw):
        self.gui.append((chat_id, text, kw))
        return SimpleNamespace(message_id=9000 + len(self.gui))

    async def get_file(self, file_id):
        nguon = self.video_tu[file_id]
        bot = self

        async def download_to_drive(dich, **_):
            bot.so_lan_tai += 1
            shutil.copyfile(nguon, dich)

        return SimpleNamespace(download_to_drive=download_to_drive)


class _JobQueue:
    def __init__(self):
        self.hen: list[tuple[float, object]] = []

    def run_once(self, cb, when, data=None, **_):
        self.hen.append((when, data))


_mid = iter(range(100, 10_000))


def _tin(bot, uid, *, chat=NHOM, anh: str = "", video: tuple[str, int] | None = None):
    kw = {}
    if anh:
        kw["photo"] = [PhotoSize(f"id-{anh}", anh, 1280, 960, file_size=90_000)]
    if video:
        uid_file, giay = video
        kw["video"] = Video(f"id-{uid_file}", uid_file, 320, 240, giay, file_size=500_000)
    m = Message(
        next(_mid), datetime.now(timezone.utc), Chat(chat, Chat.SUPERGROUP),
        from_user=User(uid, f"Người {uid}", False), **kw,
    )
    m.set_bot(bot)
    return m


def _moi_truong(monkeypatch, **cfg_kw):
    """Bot giả với mọi thứ ngoài chống trùng được gỡ ra: luật spam, admin,
    quyền bot. vt theo file_unique_id thay cho tải ảnh thật."""
    db = _db()
    # Tắt chống rải: bốn người cùng đăng một ảnh trong các ca dưới đây là chiến
    # dịch ảnh thật, và luật đó sẽ ban trước khi chống trùng kịp xét.
    cfg_kw.setdefault("chong_rai", False)
    cfg = Config(token="x", chong_trung_nhom={NHOM}, **cfg_kw)
    bot, jq = _Bot(), _JobQueue()
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"cfg": cfg, "db": db}),
        bot=bot, job_queue=jq,
    )
    van_tay = {"A": 0b1010, "A-nen-lai": 0b1010 ^ 0b111, "B": 2**50 - 1}
    can: list[bool] = []
    mien: set[int] = set()

    async def scan_image(msg, _ctx, can_van_tay=False):
        can.append(can_van_tay)
        return False, [], "", van_tay.get(msg.photo[-1].file_unique_id) if msg.photo else None

    async def khong(*_a, **_k):
        return None

    async def co(*_a, **_k):
        return True

    async def is_exempt(msg, _ctx):
        return msg.from_user.id in mien

    async def rules(_cid, _ctx):
        return B.ChatRules(cfg, [], set(), set(), set())

    monkeypatch.setattr(B, "_scan_image", scan_image)
    monkeypatch.setattr(B, "_warn_if_crippled", khong)
    monkeypatch.setattr(B, "_admins_known", co)
    monkeypatch.setattr(B, "_is_exempt", is_exempt)
    monkeypatch.setattr(B, "_chat_rules", rules)
    monkeypatch.setattr(B, "_da_bao_trung", {})
    monkeypatch.setattr(B, "_theo_doi", B.raivai.BoTheoDoi())

    def gui(msg, sua=False):
        update = SimpleNamespace(
            effective_message=msg, effective_chat=msg.chat,
            edited_message=msg if sua else None,
        )
        asyncio.run(B.scan(update, context))

    return SimpleNamespace(db=db, bot=bot, jq=jq, gui=gui, can=can, mien=mien,
                           context=context)


def test_dang_lai_bi_xoa_va_bao_roi_tu_xoa(monkeypatch):
    m = _moi_truong(monkeypatch)
    goc = _tin(m.bot, 1, anh="A")
    m.gui(goc)
    assert m.bot.da_xoa == [] and m.can == [True], "bản đầu tiên giữ nguyên"

    lai = _tin(m.bot, 2, anh="A-nen-lai")   # tải lên lại: file khác, vân tay gần
    m.gui(lai)
    assert m.bot.da_xoa == [(NHOM, lai.message_id)]
    (cid, text, kw), = m.bot.gui
    assert cid == NHOM and "Người 2" in text and "bản gốc" in text
    assert f"https://t.me/c/{str(NHOM)[4:]}/{goc.message_id}" in text
    assert kw.get("disable_notification") is True
    assert m.jq.hen == [(B.BAO_TRUNG_SONG, (NHOM, [9001]))], "tin báo phải tự xoá"

    # Đăng lại tiếp trong vòng một phút: vẫn xoá, nhưng không báo thêm lần nữa.
    lai2 = _tin(m.bot, 2, anh="A")
    m.gui(lai2)
    assert (NHOM, lai2.message_id) in m.bot.da_xoa and len(m.bot.gui) == 1

    # Ảnh khác thì không sao.
    m.gui(_tin(m.bot, 3, anh="B"))
    assert len(m.bot.da_xoa) == 2


def test_nhung_ca_khong_duoc_dung_toi(monkeypatch):
    m = _moi_truong(monkeypatch)
    m.mien.add(7)                          # admin / seeding / trusted
    m.gui(_tin(m.bot, 7, anh="A"))
    m.gui(_tin(m.bot, 7, anh="A"))
    assert m.bot.da_xoa == [], "người được miễn đăng lại bao nhiêu cũng được"
    m.gui(_tin(m.bot, 1, anh="A"))
    assert m.bot.da_xoa == [], "ảnh của người được miễn không được ghi nhớ"

    # Nhóm không bật chống trùng.
    m.gui(_tin(m.bot, 2, anh="A", chat=NHOM_KHAC))
    m.gui(_tin(m.bot, 3, anh="A", chat=NHOM_KHAC))
    assert m.bot.da_xoa == []

    # Tin sửa (đổi chú thích) không được coi là trùng với chính nó.
    sua = _tin(m.bot, 4, anh="A")
    m.gui(sua, sua=True)
    assert m.bot.da_xoa == [] and m.can[-1] is False
    assert m.db._conn.execute("SELECT COUNT(*) FROM media_hashes").fetchone()[0] == 1


def test_che_do_report_va_tat_bao(monkeypatch):
    m = _moi_truong(monkeypatch)
    m.gui(_tin(m.bot, 1, anh="A"))
    m.db._set_setting("action", "report")
    m.gui(_tin(m.bot, 2, anh="A"))
    assert m.bot.da_xoa == [] and m.bot.gui == [], "report: chỉ ghi log"

    m.db._set_setting("action", "")
    m.db._set_setting("cfg:chong_trung_bao", "0")
    m.gui(_tin(m.bot, 3, anh="A"))
    assert len(m.bot.da_xoa) == 1 and m.bot.gui == [], "tắt báo: xoá im lặng"

    m.db._set_setting("cfg:chong_trung", "0")
    m.gui(_tin(m.bot, 4, anh="A"))
    assert len(m.bot.da_xoa) == 1, "công tắc chung tắt thì thôi hẳn"


@can_anh
def test_video_dang_lai_bi_xoa(monkeypatch, tmp_path):
    m = _moi_truong(monkeypatch)
    m.bot.video_tu = {
        "id-V1": _video(tmp_path / "goc.mp4", 1),
        "id-V2": _video(tmp_path / "lai.mp4", 1, w=480, h=360, fps=30),
        "id-V3": _video(tmp_path / "khac.mp4", 2),
    }
    m.gui(_tin(m.bot, 1, video=("V1", 6)))
    m.gui(_tin(m.bot, 2, video=("V3", 6)))
    assert m.bot.da_xoa == []
    lai = _tin(m.bot, 3, video=("V2", 6))
    m.gui(lai)
    assert m.bot.da_xoa == [(NHOM, lai.message_id)] and "video này" in m.bot.gui[0][1]

    # Chuyển tiếp đúng file cũ: bắt bằng file_unique_id, không tải lại.
    tai_truoc = m.bot.so_lan_tai
    fwd = _tin(m.bot, 4, video=("V1", 6))
    m.gui(fwd)
    assert (NHOM, fwd.message_id) in m.bot.da_xoa and m.bot.so_lan_tai == tai_truoc


def test_video_qua_20mb_chi_so_file(monkeypatch):
    m = _moi_truong(monkeypatch)
    to = Video("id-X", "X", 1920, 1080, 60, file_size=trunglap.TOI_DA_TAI + 1)
    assert asyncio.run(B._van_tay_video_tin(m.context, to)) == []
    assert m.bot.so_lan_tai == 0


def test_luc_truoc_va_link():
    assert B._luc_truoc(5) == "1 phút trước"
    assert B._luc_truoc(7200) == "2 giờ trước"
    assert B._luc_truoc(3 * 86400 + 5) == "3 ngày trước"
    assert B._link_tin(Chat(-1001234, Chat.SUPERGROUP), 7) == "https://t.me/c/1234/7"
    assert B._link_tin(Chat(-1001234, Chat.SUPERGROUP, username="choxe"), 7) == \
        "https://t.me/choxe/7"
    assert B._link_tin(Chat(-4567, Chat.GROUP), 7) == ""
