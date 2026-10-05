"""Lệnh /leave: chỉ owner, hỏi lại trước khi rời, và không nhắn gì ra nhóm.

Rời nhóm là việc bot không tự làm ngược lại được (phải có người thêm lại và
cấp quyền admin), nên mấy ca dưới đây chủ yếu canh chuyện rời NHẦM.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram.constants import ChatType
from telegram.error import BadRequest, Forbidden

from antispam_bot import bot as B
from antispam_bot.storage import Storage

OWNER = 1
A, C = -100111, -100222


class _Bot:
    def __init__(self, loi: dict | None = None):
        self.loi = loi or {}
        self.da_roi: list[int] = []
        self.rieng: list[tuple[int, str]] = []

    async def leave_chat(self, chat_id):
        if chat_id in self.loi:
            raise self.loi[chat_id]
        self.da_roi.append(chat_id)

    async def get_chat(self, chat_id):
        return SimpleNamespace(title=f"Nhóm {chat_id}")

    async def send_message(self, chat_id, text, **_):
        self.rieng.append((chat_id, text))


class _Msg:
    def __init__(self, chat_id: int, loai: str):
        self.chat_id = chat_id
        self.message_id = 5
        self.chat = SimpleNamespace(type=loai, title=f"Nhóm {chat_id}")
        self.da_xoa = False
        self.tra_loi: list[str] = []

    async def delete(self):
        self.da_xoa = True

    async def reply_html(self, text, **_):
        self.tra_loi.append(text)
        return SimpleNamespace(message_id=6)


def _chay(args, *, user=OWNER, chat_id=OWNER, loai=ChatType.PRIVATE, loi=None):
    db = Storage(Path(tempfile.mkdtemp()) / "thu.db")
    db._set_setting("home_group", f"{A},{C}")
    bot = _Bot(loi)
    msg = _Msg(chat_id, loai)
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={"cfg": SimpleNamespace(owner_ids={OWNER}), "db": db}
        ),
        bot=bot, args=args, job_queue=None,
    )
    update = SimpleNamespace(effective_message=msg, effective_user=SimpleNamespace(id=user))
    asyncio.run(B.cmd_leave(update, context))
    return bot, msg, db._get_setting("home_group")


def test_chua_ok_thi_chi_hoi_lai():
    bot, msg, nhom = _chay([str(A)])
    assert bot.da_roi == [] and nhom == f"{A},{C}"
    assert f"/leave {A} ok" in msg.tra_loi[0]


def test_ok_thi_roi_va_bo_khoi_danh_sach():
    bot, msg, nhom = _chay([str(A), "ok"])
    assert bot.da_roi == [A]
    assert nhom == str(C), "nhóm còn lại phải giữ nguyên"
    assert "Đã rời" in msg.tra_loi[0] and "Còn lại: <b>1</b>" in msg.tra_loi[0]


def test_khong_co_chat_id_thi_chi_liet_ke():
    bot, msg, nhom = _chay([])
    assert bot.da_roi == [] and nhom == f"{A},{C}"
    assert str(A) in msg.tra_loi[0] and str(C) in msg.tra_loi[0]
    # "ok" trần không được hiểu thành "rời hết".
    bot, _, nhom = _chay(["ok"])
    assert bot.da_roi == [] and nhom == f"{A},{C}"


def test_id_nguoi_dung_hay_chu_bi_tu_choi():
    for sai in ("12345", "abc"):
        bot, msg, nhom = _chay([str(A), sai, "ok"])
        assert bot.da_roi == [] and nhom == f"{A},{C}", sai
        assert "không phải chat_id hợp lệ" in msg.tra_loi[0]


def test_trong_nhom_roi_ngay_va_khong_nhan_gi_ra_nhom():
    bot, msg, nhom = _chay([], chat_id=A, loai=ChatType.SUPERGROUP)
    assert bot.da_roi == [A] and nhom == str(C)
    assert msg.da_xoa and msg.tra_loi == [], "không để lại tin nào trong nhóm"
    assert bot.rieng and bot.rieng[0][0] == OWNER and "Đã rời" in bot.rieng[0][1]


def test_trong_nhom_kem_chat_id_khac_thi_khong_roi():
    bot, msg, nhom = _chay([str(C)], chat_id=A, loai=ChatType.SUPERGROUP)
    assert bot.da_roi == [] and nhom == f"{A},{C}"
    assert msg.tra_loi == [] and "chưa bị rời" in bot.rieng[0][1]


def test_nguoi_khong_phai_owner_khong_duoi_duoc_bot():
    for loai, cid in ((ChatType.SUPERGROUP, A), (ChatType.PRIVATE, 999)):
        bot, msg, nhom = _chay([str(A), "ok"], user=999, chat_id=cid, loai=loai)
        assert bot.da_roi == [] and nhom == f"{A},{C}"
        assert msg.da_xoa and msg.tra_loi == [] and bot.rieng == []


def test_da_bi_kick_san_thi_van_don_danh_sach():
    bot, msg, nhom = _chay([str(A), "ok"], loi={A: Forbidden("bot is not a member")})
    assert nhom == str(C) and "Đã rời" in msg.tra_loi[0]


def test_loi_khac_thi_giu_nhom_va_bao_ro():
    bot, msg, nhom = _chay([str(A), str(C), "ok"], loi={A: BadRequest("Chat not found")})
    assert bot.da_roi == [C] and nhom == str(A)
    assert "Không rời được" in msg.tra_loi[0] and "Chat not found" in msg.tra_loi[0]
