"""Kiểm thử CLI: phần dựng văn bản, đọc ID, và ghi database có đánh dấu đổi."""

from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot import cli, control
from antispam_bot.config import Config
from antispam_bot.control import CONG_TAC
from antispam_bot.storage import GLOBAL, Storage

_MAU = re.compile(r"\x1b\[[0-9;]*m")


def _tho(s: str) -> str:
    """Bỏ mã màu để so chuỗi."""
    return _MAU.sub("", s)


def _db() -> Storage:
    return Storage(Path(tempfile.mkdtemp()) / "thu.db")


def test_bang_cong_tac_danh_so_dung_thu_tu():
    co = {t: (i % 2 == 0) for i, t in enumerate(CONG_TAC)}
    bang = _tho(cli.bang_cong_tac(co, CONG_TAC))
    dong = bang.split("\n")
    assert len(dong) == len(CONG_TAC)
    for i, (ten, nhan) in enumerate(CONG_TAC.items(), start=1):
        assert dong[i - 1].strip().startswith(f"{i}."), dong[i - 1]
        assert ten in dong[i - 1] and nhan in dong[i - 1]
        assert ("BẬT" in dong[i - 1]) == co[ten]


def test_bang_starters_bo_owner_va_tach_id_moi():
    st = [(1, "Owner", "own", 1000), (2, "A", "a_user", 1000), (3, "B", "", 0), (4, "C", "c", 1000)]
    bang, moi = cli.bang_starters(st, da_co={2}, bo_qua={1})
    tho = _tho(bang)
    assert "Owner" not in tho, "owner phải bị bỏ khỏi danh sách"
    assert moi == [3, 4], moi
    assert "@a_user" in tho and "✅" in tho


def test_bang_starters_trong():
    bang, moi = cli.bang_starters([], set(), set())
    assert moi == [] and "chưa ai" in bang


def test_doc_ids():
    ids, hong = cli.doc_ids(["123,", "456", "@abc", "-100777"])
    assert ids == [123, 456, -100777] and hong == ["@abc"]
    assert cli.doc_ids([]) == ([], [])


def test_set_flag_danh_dau_doi():
    """Bật/tắt qua control phải đổi phiên bản để bot bỏ cache luật."""
    db = _db()

    async def chay():
        truoc = await db.get_setting("cfg:version")
        await control.set_flag(db, "captcha", True)
        sau = await db.get_setting("cfg:version")
        assert sau and sau != truoc
        assert await control.get_flag(db, Config(token="x"), "captcha") is True
        await asyncio.sleep(0.002)
        await control.danh_dau_doi(db)
        assert await db.get_setting("cfg:version") != sau

    asyncio.run(chay())


def test_seeding_add_del_qua_cli():
    db = _db()
    cfg = Config(token="x")

    async def chay():
        assert await cli._seeding(db, cfg, ["add", "11,", "22", "@x"]) == 0
        assert sorted(await db.get_fwd_whitelist(GLOBAL)) == [11, 22]
        assert await cli._seeding(db, cfg, ["del", "11"]) == 0
        assert await db.get_fwd_whitelist(GLOBAL) == [22]
        assert await cli._seeding(db, cfg, ["add"]) == 1, "không có ID thì phải báo lỗi"

    asyncio.run(chay())


def test_seeding_all_them_moi_starter_tru_owner():
    db = _db()
    cfg = Config(token="x", owner_ids={1})

    async def chay():
        for uid, ten in ((1, "own"), (5, "A"), (6, "B")):
            await db.add_starter(uid, ten, "")
        await db.add_bot_admin(6)
        assert await cli._seeding(db, cfg, ["all"]) == 0
        assert await db.get_fwd_whitelist(GLOBAL) == [5], "chỉ acc thường mới thành seeding"

    asyncio.run(chay())


def test_bat_tat_ten_sai_goi_y():
    db = _db()
    cfg = Config(token="x")

    async def chay():
        assert await cli._bat_tat(db, cfg, "khong_co", True) == 1
        assert await cli._bat_tat(db, cfg, "scan_ocr", False) == 0
        assert await control.get_flag(db, cfg, "scan_ocr") is False

    asyncio.run(chay())
