"""Điều khiển bot ngay trên terminal, không cần mở .env hay khởi động lại.

    python -m antispam_bot.cli                 menu tương tác (bấm số để bật/tắt)
    python -m antispam_bot.cli list            trạng thái mọi công tắc
    python -m antispam_bot.cli on captcha      bật một công tắc
    python -m antispam_bot.cli off scan_ocr    tắt một công tắc
    python -m antispam_bot.cli starters        ai đã bấm Start với bot (kèm ID)
    python -m antispam_bot.cli seeding list    acc seeding đang có
    python -m antispam_bot.cli seeding add 123 456 @abc
    python -m antispam_bot.cli seeding del 123
    python -m antispam_bot.cli seeding all     thêm MỌI acc đã bấm Start làm seeding
    python -m antispam_bot.cli pause 30 | resume | action report | action ban

CÁCH HOẠT ĐỘNG
Ghi thẳng vào antispam.db - đúng file bot đang dùng. SQLite ở chế độ WAL nên
bot đang chạy vẫn đọc/ghi song song bình thường. Mỗi lần ghi xong, CLI "đánh
dấu đổi" (control.danh_dau_doi) để bot bỏ cache luật và nạp lại ngay ở tin
nhắn kế tiếp - không phải đợi 60 giây, không phải khởi động lại.

Cùng một mật khẩu với lúc mở bot (START_PASSWORD): ai ngồi được vào terminal
này là chỉnh được cả bot, nên khoá y như nhau.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime

from . import console, control
from .config import Config
from .storage import GLOBAL, Storage

# Mã ANSI cho terminal. Windows 10+ và mọi Linux đều hiểu.
XANH, DO, XAM, DAM, HET = "\033[32m", "\033[31m", "\033[90m", "\033[1m", "\033[0m"


# --------------------------------------------------------------------------
# Phần thuần: dựng văn bản, không đụng database - để kiểm thử được
# --------------------------------------------------------------------------

def bang_cong_tac(co: dict[str, bool], nhan: dict[str, str]) -> str:
    """Bảng đánh số, mỗi dòng một công tắc. Số thứ tự dùng để bấm ở menu."""
    dong = []
    for i, (ten, mo_ta) in enumerate(nhan.items(), start=1):
        dau = f"{XANH}✅ BẬT {HET}" if co.get(ten) else f"{XAM}⬜ tắt {HET}"
        dong.append(f"  {i:2}. {dau}  {mo_ta:<28} {XAM}{ten}{HET}")
    return "\n".join(dong)


def bang_starters(
    starters: list[tuple[int, str, str, int]], da_co: set[int], bo_qua: set[int]
) -> tuple[str, list[int]]:
    """(bảng để in, ID chưa là seeding). Bỏ owner/bot admin - họ đã có quyền."""
    dong, moi = [], []
    for uid, ten, tag, ts in starters:
        if uid in bo_qua:
            continue
        la_seed = uid in da_co
        if not la_seed:
            moi.append(uid)
        dau = f"{XANH}✅{HET}" if la_seed else "▫️"
        khi = datetime.fromtimestamp(ts).strftime("%d/%m") if ts else ""
        dong.append(
            f"  {dau} {DAM}{uid:<12}{HET} {(ten or '')[:24]:<24} "
            f"{('@' + tag) if tag else '':<18} {XAM}{khi}{HET}"
        )
    if not dong:
        return "  (chưa ai bấm Start với bot)", []
    return "\n".join(dong), moi


def doc_ids(tokens: list[str]) -> tuple[list[int], list[str]]:
    """'123, 456 @abc' -> ([123, 456], ['@abc']). @username thì CLI không tra
    được (không có kết nối Telegram) - trả riêng để báo người dùng."""
    ids, hong = [], []
    for t in " ".join(tokens).replace(",", " ").split():
        t = t.strip()
        if t.lstrip("-").isdigit():
            ids.append(int(t))
        elif t:
            hong.append(t)
    return ids, hong


# --------------------------------------------------------------------------
# Lệnh
# --------------------------------------------------------------------------

async def _list(db: Storage, cfg: Config) -> None:
    ngung, con = await control.is_paused(db)
    che_do = await control.effective_action(db, cfg)
    print(f"\n  Chế độ: {DAM}{che_do}{HET}"
          + (f"   {DO}ĐANG NGƯNG{HET} còn {con // 60} phút" if ngung else f"   {XANH}đang chạy{HET}"))
    print()
    print(bang_cong_tac(await control.all_flags(db, cfg), control.CONG_TAC))
    print()


async def _bat_tat(db: Storage, cfg: Config, ten: str, bat: bool) -> int:
    if ten not in control.CONG_TAC:
        from difflib import get_close_matches
        gan = get_close_matches(ten, list(control.CONG_TAC), n=3, cutoff=0.6)
        print(f"  {DO}Không có công tắc '{ten}'.{HET}"
              + (f" Ý bạn là: {', '.join(gan)}?" if gan else "")
              + f"\n  Có: {', '.join(control.CONG_TAC)}")
        return 1
    await control.set_flag(db, ten, bat)
    print(f"  {XANH if bat else XAM}{'BẬT' if bat else 'TẮT'}{HET} {control.CONG_TAC[ten]} ({ten})")
    return 0


async def _starters(db: Storage, cfg: Config) -> list[int]:
    st = await db.get_starters()
    da_co = set(await db.get_fwd_whitelist(GLOBAL))
    bo_qua = set(cfg.owner_ids) | set(await db.get_bot_admins())
    bang, moi = bang_starters(st, da_co, bo_qua)
    print(f"\n  {DAM}Ai đã bấm Start với bot{HET}  ({XANH}✅{HET} = đã là seeding)\n")
    print(bang)
    if moi:
        print(f"\n  ID chưa là seeding ({len(moi)}), copy dòng dưới:")
        print(f"  {DAM}{', '.join(map(str, moi))}{HET}")
        print(f"\n  Thêm tất cả:  {XAM}python -m antispam_bot.cli seeding all{HET}")
    print()
    return moi


async def _seeding(db: Storage, cfg: Config, args: list[str]) -> int:
    viec = (args[0] if args else "list").lower()
    if viec == "list":
        ids = sorted(await db.get_fwd_whitelist(GLOBAL))
        ten = {u: (t or tag) for u, t, tag, _ in await db.get_starters()}
        print(f"\n  {DAM}Acc seeding (mọi nhóm): {len(ids)}{HET}")
        for u in ids:
            print(f"  {u:<12} {ten.get(u, '')}")
        print()
        return 0
    if viec == "all":
        moi = await _starters(db, cfg)
        for u in moi:
            await db.add_fwd_whitelist(GLOBAL, u)
        await control.danh_dau_doi(db)
        print(f"  {XANH}Đã thêm {len(moi)} acc làm seeding.{HET}\n")
        return 0
    ids, hong = doc_ids(args[1:])
    if hong:
        print(f"  {DO}Bỏ qua {', '.join(hong)}: CLI không tra được @username "
              f"(không có kết nối Telegram). Dùng ID số, hoặc bảo acc đó bấm Start "
              f"rồi 'starters'.{HET}")
    if not ids:
        print("  Cần ít nhất một ID. VD: seeding add 123456789")
        return 1
    if viec == "add":
        for u in ids:
            await db.add_fwd_whitelist(GLOBAL, u)
        print(f"  {XANH}Đã thêm {len(ids)} acc seeding.{HET}")
    elif viec in ("del", "delete", "remove"):
        n = 0
        for u in ids:
            n += await db.remove_fwd_whitelist(GLOBAL, u)
        print(f"  Đã bớt {n} acc.")
    else:
        print("  Dùng: seeding list | add ID... | del ID... | all")
        return 1
    await control.danh_dau_doi(db)
    return 0


async def _menu(db: Storage, cfg: Config) -> None:
    """Menu tương tác: bấm số để đảo công tắc, chữ cái cho việc khác."""
    ten_theo_so = list(control.CONG_TAC)
    while True:
        await _list(db, cfg)
        print(f"  {XAM}Bấm SỐ để bật/tắt · p = ngưng 30' · r = bật lại · t = chế độ thử · "
              f"b = bật ban · s = ai đã bấm Start · a = thêm hết làm seeding · q = thoát{HET}")
        try:
            chon = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if chon in ("q", "quit", "exit", ""):
            return
        if chon.isdigit() and 1 <= int(chon) <= len(ten_theo_so):
            ten = ten_theo_so[int(chon) - 1]
            hien = await control.get_flag(db, cfg, ten)
            await control.set_flag(db, ten, not hien)
        elif chon == "p":
            await control.pause(db, 30); print("  Đã ngưng 30 phút.")
        elif chon == "r":
            await control.resume(db); print("  Đã bật lại.")
        elif chon == "t":
            await control.set_action(db, "report"); print("  Chế độ thử: chỉ ghi log, không ban.")
        elif chon == "b":
            await control.set_action(db, "ban"); print("  Đã bật ban lại.")
        elif chon == "s":
            await _starters(db, cfg); input("  Enter để tiếp... ")
        elif chon == "a":
            await _seeding(db, cfg, ["all"]); input("  Enter để tiếp... ")
        else:
            print(f"  {DO}Không hiểu '{chon}'.{HET}")


async def chay(argv: list[str]) -> int:
    cfg = Config.load()
    if not console.hoi_mat_khau(cfg.start_password):
        return 1
    db = Storage(cfg.db_path)
    try:
        lenh = (argv[0] if argv else "").lower()
        rest = argv[1:]
        if not lenh:
            await _menu(db, cfg); return 0
        if lenh == "list":
            await _list(db, cfg); return 0
        if lenh in ("on", "off"):
            if not rest:
                print(f"  Dùng: {lenh} <tên công tắc>. Có: {', '.join(control.CONG_TAC)}")
                return 1
            return await _bat_tat(db, cfg, rest[0].lower(), lenh == "on")
        if lenh == "starters":
            await _starters(db, cfg); return 0
        if lenh == "seeding":
            return await _seeding(db, cfg, rest)
        if lenh == "pause":
            phut = int(rest[0]) if rest and rest[0].isdigit() else 30
            await control.pause(db, phut); print(f"  Đã ngưng {phut} phút."); return 0
        if lenh == "resume":
            await control.resume(db); print("  Đã bật lại."); return 0
        if lenh == "action":
            if not rest or rest[0] not in ("ban", "mute", "delete", "report"):
                print("  Dùng: action ban | mute | delete | report"); return 1
            await control.set_action(db, rest[0]); print(f"  Chế độ: {rest[0]}"); return 0
        print(__doc__.split("CÁCH HOẠT ĐỘNG")[0])
        return 1
    finally:
        db.close()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.platform == "win32":
        import os
        os.system("")  # bật mã màu ANSI trên console Windows
    raise SystemExit(asyncio.run(chay(sys.argv[1:])))


if __name__ == "__main__":
    main()
