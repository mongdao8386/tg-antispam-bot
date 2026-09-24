"""Sửa hậu quả ban oan acc seeding - chạy MỘT LẦN trên VPS sau khi vá mã.

    cd /opt/antispam/app && /opt/antispam/venv/bin/python deploy/sua-hau-qua-seeding.py [ID thêm...]

Làm gì, theo thứ tự:
  1. Thêm các ID truyền vào (nếu có) làm acc seeding cho mọi nhóm.
  2. Tha mọi nội dung mà acc seeding từng đăng khỏi luật chiến dịch.
  3. Gỡ ban acc seeding ở MỌI nhóm đang quản lý (gọi Telegram, có giới hạn tốc độ).
  4. Xoá lịch sử vi phạm của họ - nếu không /purge_all và hốt-cả-ổ sẽ ban lại.
  5. Đánh dấu đổi để bot đang chạy nạp lại danh sách ngay.

Chạy song song với bot đang chạy được: SQLite WAL, và chỉ gọi unban.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Bot
from telegram.error import TelegramError

from antispam_bot import control
from antispam_bot.config import Config
from antispam_bot.storage import GLOBAL, Storage


async def chay(them: list[int]) -> None:
    cfg = Config.load()
    db = Storage(cfg.db_path)
    try:
        for uid in them:
            await db.add_fwd_whitelist(GLOBAL, uid)
        if them:
            print(f"[1] Đã thêm {len(them)} acc seeding: {them}")

        seed = set(await db.get_fwd_whitelist(GLOBAL))
        raw = await db.get_setting("home_group")
        nhom = [int(x) for x in (raw or "").split(",") if x.strip()]
        for gid in nhom:
            seed |= set(await db.get_fwd_whitelist(gid))
        print(f"    {len(seed)} acc seeding, {len(nhom)} nhóm")

        n = await db.tha_noi_dung_cua(seed)
        print(f"[2] Tha {n} nội dung do acc seeding đăng")

        # Cặp (nhóm, acc seeding) từng bị ban -> gỡ.
        cap = [(c, u) for c, u in await db.banned_pairs() if u in seed and c in nhom]
        print(f"[3] Gỡ ban {len(cap)} cặp (nhóm, acc)...", flush=True)
        bot = Bot(cfg.token)
        gioi_han = asyncio.Semaphore(4)
        xong = 0
        loi: list[str] = []

        async def go(c: int, u: int) -> None:
            nonlocal xong
            async with gioi_han:
                try:
                    await bot.unban_chat_member(c, u, only_if_banned=True)
                    xong += 1
                except TelegramError as exc:
                    loi.append(f"{u}@{c}: {exc}")
                await asyncio.sleep(0.25)   # 4 luồng x 0.25s = ~16 lệnh/giây, dưới trần Telegram

        async with bot:
            await asyncio.gather(*(go(c, u) for c, u in cap))
        print(f"    gỡ được {xong}/{len(cap)}" + (f", lỗi {len(loi)} (vd: {loi[0]})" if loi else ""))

        xoa = 0
        for u in seed:
            for c in nhom:
                xoa += await db.clear_offences(c, u)
        print(f"[4] Xoá {xoa} dòng vi phạm của acc seeding")

        await control.danh_dau_doi(db)
        print("[5] Đã đánh dấu đổi - bot nạp lại ngay ở tin kế tiếp.")
    finally:
        db.close()


if __name__ == "__main__":
    ids = [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()]
    asyncio.run(chay(ids))
