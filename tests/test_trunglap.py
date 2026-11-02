"""Chống ảnh/video đăng lại: vân tay, bộ nhớ trong database, xoá / reply.

Hai mức: TRÙNG (cùng file, hoặc vân tay lệch <= CHONG_TRUNG_LECH_XOA) thì xoá
với MỌI người kể cả admin, admin ẩn danh, seeding; chỉ GIỐNG thì giữ lại và
reply vào tin đó cho chủ bot xem tay. Ca quan trọng: tin chỉ giống KHÔNG bị
xoá, tin spam không lọt vào bộ nhớ, nhóm không bật thì không đụng tới.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Chat, Message, PhotoSize, Update, User, Video
from telegram.ext import ApplicationHandlerStop

from antispam_bot import bot as B
from antispam_bot import trunglap
from antispam_bot.anhhash import AVAILABLE, van_tay_anh
from antispam_bot.config import Config
from antispam_bot.storage import Storage
from antispam_bot.trunglap import bo_so, do_lech, giai_ma, giong_nhau, ma_hoa, van_tay_video

cv2 = pytest.importorskip("cv2") if AVAILABLE else None
np = pytest.importorskip("numpy") if AVAILABLE else None
can_anh = pytest.mark.skipif(not AVAILABLE, reason="cần OpenCV")

NHOM, NHOM_KHAC = -1001234567890, -1009999999999
LECH = 5
TUAN = 7 * 86400
AN_DANH = 1087968824   # GroupAnonymousBot của Telegram


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


def test_do_lech_lay_khung_lech_nhat():
    a = [0, 0b111, 0]
    assert do_lech(a, [0, 0b111, 0b11]) == 2
    assert do_lech(a, [0, 0b111, 2**40 - 1]) == 40, "một khung lệch hẳn là video khác"
    # Chỉ một khung so được: chưa nói lên gì (cùng logo mở đầu).
    assert do_lech([0, None, None], [0, 5, 7]) is None
    assert do_lech([0, None, 3], [1, 9, 3]) == 1
    # Ảnh chỉ có một vân tay.
    assert do_lech([0], [0b11111]) == 5 and do_lech([None], [None]) is None
    assert giong_nhau([0], [0b11111], LECH) and not giong_nhau([0], [0b111111], LECH)


def test_lech_thoi_luong_thi_khong_phai_mot():
    so = bo_so([0, 0, 0], 30)
    h = ma_hoa([0, 0, 0])
    assert so(h, 30) == 0 and so(h, 31) == 0 and so(h, 0) == 0
    assert so(h, 32) is None


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

def _xet(db, uid, *, uid_file="", h="", chat=NHOM, mid=1, loai="photo", d=0, ghi=True,
         lech_xoa=0):
    return db._media_trung_hoac_ghi(
        chat, mid, uid, loai, uid_file, h, d, TUAN, bo_so(giai_ma(h), d), LECH, lech_xoa, ghi,
    )


def _so_dong(db) -> int:
    return db._conn.execute("SELECT COUNT(*) FROM media_hashes").fetchone()[0]


def test_cung_file_la_trung_ke_ca_chinh_nguoi_do_dang_lai_ngay():
    db = _db()
    assert _xet(db, 1, uid_file="F1", mid=10) is None
    assert _xet(db, 1, uid_file="F1", mid=11)[::3] == (10, 0), "đăng lại ngay vẫn là trùng"
    cu = _xet(db, 2, uid_file="F1", mid=12)
    assert cu[0] == 10 and cu[1] == 1 and cu[3] == 0
    assert _so_dong(db) == 1, "bản trùng sắp bị xoá, không được ghi"


def test_hai_muc_trung_va_giong():
    db = _db()
    assert _xet(db, 1, uid_file="F1", h=ma_hoa([0b1010]), mid=10) is None
    # Tải lên lại: file mới nhưng vân tay y hệt -> trùng, không ghi.
    assert _xet(db, 2, uid_file="F2", h=ma_hoa([0b1010]), mid=11)[::3] == (10, 0)
    assert _so_dong(db) == 1
    # Lệch 3 bit -> chỉ giống: báo độ lệch, VẪN ghi vì tin còn ở lại nhóm.
    assert _xet(db, 3, uid_file="F3", h=ma_hoa([0b1010 ^ 0b111]), mid=12)[::3] == (10, 3)
    assert _so_dong(db) == 2
    # Ai đăng lại đúng file vừa "giống" đó thì là trùng với chính nó.
    assert _xet(db, 4, uid_file="F3", mid=13)[::3] == (12, 0)
    # Khác hẳn cả hai bản đã lưu.
    assert _xet(db, 5, uid_file="F5", h=ma_hoa([0b1010 ^ (2**40 - 1)]), mid=14) is None
    # Nâng ngưỡng xoá lên 3 thì lệch 3 cũng xoá.
    assert _xet(db, 6, uid_file="F6", h=ma_hoa([0b1010 ^ 0b111]), mid=15, lech_xoa=3)[3] == 0
    assert _so_dong(db) == 3


def test_chon_ban_giong_nhat():
    db = _db()
    _xet(db, 1, uid_file="F1", h=ma_hoa([0b1111]), mid=10)        # lệch 4 với 0
    _xet(db, 2, uid_file="F2", h=ma_hoa([0b1]), mid=11)           # lệch 1 với 0
    assert _xet(db, 3, uid_file="F3", h=ma_hoa([0]), mid=12)[::3] == (11, 1)


def test_khac_nhom_khac_loai_va_anh_phang():
    db = _db()
    _xet(db, 1, uid_file="F1", h=ma_hoa([7]))
    assert _xet(db, 2, uid_file="F1", h=ma_hoa([7]), chat=NHOM_KHAC) is None, "nhóm khác không tính"
    assert _xet(db, 3, uid_file="V1", h=ma_hoa([7, 7, 7]), loai="video", d=10) is None
    # Ảnh không có vân tay (ảnh phẳng) thì chỉ so được file y hệt.
    assert _xet(db, 4, uid_file="F9", h="") is None


def test_qua_han_thi_quen_va_bi_don():
    db = _db()
    _xet(db, 1, uid_file="F1", mid=10)
    db._conn.execute("UPDATE media_hashes SET created_at = created_at - ?", (TUAN + 60,))
    assert _xet(db, 2, uid_file="F1", mid=11) is None
    assert db._don_media(7) == 1
    assert _so_dong(db) == 1


def test_chi_tra_thi_khong_ghi():
    db = _db()
    assert _xet(db, 1, uid_file="F1", ghi=False) is None
    assert _so_dong(db) == 0


# --- Đầu-cuối qua scan() rồi on_media_trung() ------------------------------

class _Bot:
    def __init__(self):
        self.da_xoa: list[tuple[int, int]] = []
        self.da_ban: list[tuple[int, int]] = []
        self.gui: list[tuple[int, str, dict]] = []
        self.video_tu: dict[str, Path] = {}
        self.so_lan_tai = 0

    async def delete_message(self, chat_id, message_id, **_):
        self.da_xoa.append((chat_id, message_id))
        return True

    async def ban_chat_member(self, chat_id, user_id, **_):
        self.da_ban.append((chat_id, user_id))
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


def _tin(bot, uid, *, chat=NHOM, anh: str = "", video: tuple[str, int] | None = None,
         an_danh=False):
    kw = {}
    if anh:
        kw["photo"] = [PhotoSize(f"id-{anh}", anh, 1280, 960, file_size=90_000)]
    if video:
        uid_file, giay = video
        kw["video"] = Video(f"id-{uid_file}", uid_file, 320, 240, giay, file_size=500_000)
    if an_danh:
        kw["sender_chat"] = Chat(chat, Chat.SUPERGROUP)
        uid = AN_DANH
    m = Message(
        next(_mid), datetime.now(timezone.utc), Chat(chat, Chat.SUPERGROUP),
        from_user=User(uid, f"Người {uid}", an_danh), **kw,
    )
    m.set_bot(bot)
    return m


def _moi_truong(monkeypatch, **cfg_kw):
    """Gỡ hết những gì ngoài chống trùng: quyền bot, danh sách admin, tải ảnh.
    Vân tay ảnh lấy theo file_unique_id thay cho tải ảnh thật."""
    db = _db()
    # Tắt chống rải: nhiều người cùng đăng một ảnh trong các ca dưới đây là
    # chiến dịch ảnh thật, và luật đó sẽ ban trước khi chống trùng kịp xét.
    cfg_kw.setdefault("chong_rai", False)
    cfg = Config(token="x", chong_trung_nhom={NHOM}, **cfg_kw)
    bot, jq = _Bot(), _JobQueue()
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"cfg": cfg, "db": db}),
        bot=bot, job_queue=jq,
    )
    van_tay = {"A": 0b1010, "A-chup-lai": 0b1010 ^ 0b111, "A-tai-lai": 0b1010, "B": 2**50 - 1}
    goi: list[dict] = []
    mien: set[int] = set()
    chan: set[int] = set()

    async def scan_image(msg, _ctx, can_van_tay=False, chi_van_tay=False):
        goi.append({"can": can_van_tay, "chi": chi_van_tay})
        return False, [], "", van_tay.get(msg.photo[-1].file_unique_id) if msg.photo else None

    async def khong(*_a, **_k):
        return None

    async def co(*_a, **_k):
        return True

    async def is_exempt(msg, _ctx):
        return msg.sender_chat is not None or msg.from_user.id in mien

    async def rules(_cid, _ctx):
        return B.ChatRules(cfg, [], set(), chan, set())

    monkeypatch.setattr(B, "_scan_image", scan_image)
    monkeypatch.setattr(B, "_warn_if_crippled", khong)
    monkeypatch.setattr(B, "_admins_known", co)
    monkeypatch.setattr(B, "_is_exempt", is_exempt)
    monkeypatch.setattr(B, "_chat_rules", rules)
    monkeypatch.setattr(B, "_da_bao_trung", {})
    monkeypatch.setattr(B, "_vua_ban", {})
    monkeypatch.setattr(B, "_theo_doi", B.raivai.BoTheoDoi())

    def gui(msg, sua=False):
        """Như Application.process_update: nhóm 1 (scan) rồi nhóm 2, trừ khi
        nhóm 1 dừng chuỗi. Bộ lọc của nhóm 2 thử riêng ở test_dang_ky_handler."""
        update = SimpleNamespace(
            effective_message=msg, effective_chat=msg.chat,
            edited_message=msg if sua else None,
        )

        async def chay():
            try:
                await B.scan(update, context)
            except ApplicationHandlerStop:
                return
            if not sua and (msg.photo or msg.video):
                await B.on_media_trung(update, context)

        asyncio.run(chay())

    return SimpleNamespace(db=db, bot=bot, jq=jq, gui=gui, goi=goi, mien=mien, chan=chan,
                           context=context)


def _reply(kw) -> int | None:
    rp = kw.get("reply_parameters")
    return rp.message_id if rp else None


def test_trung_y_het_bi_xoa_ke_ca_chinh_nguoi_do(monkeypatch):
    """Đúng ca chủ bot thử: một acc đăng cùng một ảnh nhiều lần liền."""
    m = _moi_truong(monkeypatch)
    goc = _tin(m.bot, 1, anh="A")
    m.gui(goc)
    assert m.bot.da_xoa == [] and m.goi[0]["can"] is True, "bản đầu giữ nguyên"
    lai = [_tin(m.bot, 1, anh="A") for _ in range(3)]
    for t in lai:
        m.gui(t)
    assert m.bot.da_xoa == [(NHOM, t.message_id) for t in lai]

    # Báo một lần (tự xoá sau 10 giây), không báo lại trong vòng một phút.
    (cid, text, kw), = m.bot.gui
    assert cid == NHOM and "Người 1" in text and "bản gốc" in text and _reply(kw) is None
    assert f"https://t.me/c/{str(NHOM)[4:]}/{goc.message_id}" in text
    assert m.jq.hen == [(B.BAO_TRUNG_SONG, (NHOM, [9001]))]

    # Người khác tải lên lại (file khác, vân tay y hệt) cũng là trùng.
    tai_lai = _tin(m.bot, 2, anh="A-tai-lai")
    m.gui(tai_lai)
    assert m.bot.da_xoa[-1] == (NHOM, tai_lai.message_id) and len(m.bot.gui) == 2


def test_chi_giong_thi_reply_khong_xoa(monkeypatch):
    m = _moi_truong(monkeypatch)
    goc = _tin(m.bot, 1, anh="A")
    m.gui(goc)
    giong = _tin(m.bot, 2, anh="A-chup-lai")        # lệch 3 bit
    m.gui(giong)
    assert m.bot.da_xoa == [], "chỉ giống thì KHÔNG được xoá"
    (cid, text, kw), = m.bot.gui
    assert _reply(kw) == giong.message_id, "phải reply đúng vào tấm ảnh đó"
    assert "giống ~95%" in text and "không xoá" in text
    assert f"/{goc.message_id}" in text
    assert m.jq.hen == [], "reply để admin tìm lại, không tự xoá"

    # Ai đăng lại đúng tấm vừa bị nghi đó thì xoá.
    lai = _tin(m.bot, 3, anh="A-chup-lai")
    m.gui(lai)
    assert m.bot.da_xoa == [(NHOM, lai.message_id)]
    m.gui(_tin(m.bot, 4, anh="B"))
    assert len(m.bot.da_xoa) == 1 and len(m.bot.gui) == 2


def test_admin_seeding_an_danh_cung_bi_xoa(monkeypatch):
    m = _moi_truong(monkeypatch)
    m.mien.add(7)                          # admin / seeding / trusted / owner
    m.gui(_tin(m.bot, 7, anh="A"))
    lai = _tin(m.bot, 7, anh="A")
    m.gui(lai)
    assert m.bot.da_xoa == [(NHOM, lai.message_id)]
    assert m.goi[-1]["chi"] is True, "người được miễn: scan bỏ qua, chống trùng tự lấy vân tay"

    m.gui(_tin(m.bot, 0, anh="B", an_danh=True))
    an = _tin(m.bot, 0, anh="B", an_danh=True)
    m.gui(an)
    assert m.bot.da_xoa[-1] == (NHOM, an.message_id)
    assert "Admin ẩn danh" in m.bot.gui[-1][1]


def test_tin_spam_bi_ban_va_khong_vao_bo_nho(monkeypatch):
    m = _moi_truong(monkeypatch)
    m.chan.add(66)                         # chặn cứng
    rac = _tin(m.bot, 66, anh="A")
    m.gui(rac)
    assert m.bot.da_ban == [(NHOM, 66)] and m.bot.da_xoa == [(NHOM, rac.message_id)]
    assert _so_dong(m.db) == 0, "tin rác đã xoá thì không được ghi nhớ"
    m.gui(_tin(m.bot, 1, anh="A"))
    assert len(m.bot.da_xoa) == 1, "người sau đăng tấm đó không bị coi là trùng với tin rác"


def test_nhom_khac_va_tin_sua(monkeypatch):
    m = _moi_truong(monkeypatch)
    m.gui(_tin(m.bot, 2, anh="A", chat=NHOM_KHAC))
    m.gui(_tin(m.bot, 3, anh="A", chat=NHOM_KHAC))
    assert m.bot.da_xoa == [] and _so_dong(m.db) == 0
    assert m.goi[-1]["can"] is False, "nhóm không bật thì khỏi tính vân tay"

    sua = _tin(m.bot, 4, anh="A")
    m.gui(sua, sua=True)
    assert m.bot.da_xoa == [] and _so_dong(m.db) == 0


def test_che_do_report_va_cong_tac(monkeypatch):
    m = _moi_truong(monkeypatch)
    m.gui(_tin(m.bot, 1, anh="A"))
    m.db._set_setting("action", "report")
    m.gui(_tin(m.bot, 2, anh="A"))
    m.gui(_tin(m.bot, 2, anh="A-chup-lai"))
    assert m.bot.da_xoa == [] and m.bot.gui == [], "report: chỉ ghi log"

    m.db._set_setting("action", "")
    m.db._set_setting("cfg:chong_trung_bao", "0")
    m.gui(_tin(m.bot, 3, anh="A"))
    assert len(m.bot.da_xoa) == 1 and m.bot.gui == [], "tắt báo: xoá im lặng"

    m.db._set_setting("cfg:chong_trung", "0")
    m.gui(_tin(m.bot, 4, anh="A"))
    assert len(m.bot.da_xoa) == 1, "công tắc chung tắt thì thôi hẳn"


@can_anh
def test_video_trung_xoa_giong_reply(monkeypatch, tmp_path):
    m = _moi_truong(monkeypatch)
    m.bot.video_tu = {
        "id-V1": _video(tmp_path / "goc.mp4", 1),
        "id-V2": _video(tmp_path / "lai.mp4", 1, w=480, h=360, fps=30),
        "id-V3": _video(tmp_path / "khac.mp4", 2),
    }
    m.gui(_tin(m.bot, 1, video=("V1", 6)))
    m.gui(_tin(m.bot, 2, video=("V3", 6)))
    lai = _tin(m.bot, 3, video=("V2", 6))     # quay lại ở cỡ/fps khác
    m.gui(lai)
    assert m.bot.da_xoa == [], "nén lại lệch vài bit: chỉ giống, không xoá"
    (_cid, text, kw), = m.bot.gui
    assert _reply(kw) == lai.message_id and "Video này giống" in text

    # Chuyển tiếp đúng file cũ: trùng, bắt bằng file_unique_id, không tải lại.
    tai_truoc = m.bot.so_lan_tai
    fwd = _tin(m.bot, 4, video=("V1", 6))
    m.gui(fwd)
    assert m.bot.da_xoa == [(NHOM, fwd.message_id)] and m.bot.so_lan_tai == tai_truoc


def test_video_qua_20mb_chi_so_file(monkeypatch):
    m = _moi_truong(monkeypatch)
    to = Video("id-X", "X", 1920, 1080, 60, file_size=trunglap.TOI_DA_TAI + 1)
    assert asyncio.run(B._van_tay_video_tin(m.context, to)) == []
    assert m.bot.so_lan_tai == 0


def test_van_tay_anh_lay_lai_tu_bo_nho(monkeypatch):
    """scan() đã tải ảnh rồi thì chống trùng không tải lần hai."""
    monkeypatch.setattr(B, "_vt_anh_nho", OrderedDict({"A": 0b1010}))

    class _KhongTai:
        async def get_file(self, *_a, **_k):
            raise AssertionError("không được tải lại ảnh")

    cfg = Config(token="x")
    ctx = SimpleNamespace(
        application=SimpleNamespace(bot_data={"cfg": cfg, "db": _db()}), bot=_KhongTai(),
    )
    assert asyncio.run(B._scan_image(_tin(None, 1, anh="A"), ctx, chi_van_tay=True))[3] == 0b1010


def test_dang_ky_handler():
    """Chống trùng nằm ở nhóm SAU scan(), chỉ nhận ảnh/video MỚI trong nhóm."""
    app = B.build_application(Config(token="123:abc", db_path=Path(tempfile.mkdtemp()) / "a.db"))
    assert max(app.handlers) == 2
    (h,) = app.handlers[2]
    assert h.callback is B.on_media_trung
    assert any(x.callback is B.scan for x in app.handlers[1])

    def u(sua=False, **kw):
        m = _tin(None, 1, **kw)
        return Update(1, edited_message=m) if sua else Update(1, message=m)

    assert h.check_update(u(anh="A")) and h.check_update(u(video=("V", 3)))
    assert not h.check_update(u(anh="A", sua=True)), "tin sửa không xét"
    chu = Update(1, message=Message(1, datetime.now(timezone.utc), Chat(NHOM, Chat.SUPERGROUP),
                                    text="chào"))
    rieng = Update(1, message=Message(1, datetime.now(timezone.utc), Chat(5, Chat.PRIVATE),
                                      photo=[PhotoSize("i", "u", 9, 9)]))
    assert not h.check_update(chu) and not h.check_update(rieng)
    app.bot_data["db"].close()


def test_luc_truoc_va_link():
    assert B._luc_truoc(5) == "1 phút trước"
    assert B._luc_truoc(7200) == "2 giờ trước"
    assert B._luc_truoc(3 * 86400 + 5) == "3 ngày trước"
    assert B._link_tin(Chat(-1001234, Chat.SUPERGROUP), 7) == "https://t.me/c/1234/7"
    assert B._link_tin(Chat(-1001234, Chat.SUPERGROUP, username="choxe"), 7) == \
        "https://t.me/choxe/7"
    assert B._link_tin(Chat(-4567, Chat.GROUP), 7) == ""
