"""Lưu trữ SQLite: theo dõi thành viên mới, lịch sử vi phạm, whitelist theo nhóm."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    first_seen  INTEGER NOT NULL,
    msg_count   INTEGER NOT NULL DEFAULT 0,
    trusted     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS offences (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id   INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    ts        INTEGER NOT NULL,
    score     INTEGER NOT NULL,
    action    TEXT    NOT NULL,
    reasons   TEXT    NOT NULL,
    excerpt   TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_offences_user ON offences (chat_id, user_id);

CREATE TABLE IF NOT EXISTS chat_whitelist (
    chat_id INTEGER NOT NULL,
    domain  TEXT    NOT NULL,
    PRIMARY KEY (chat_id, domain)
);

-- Người dùng được phép chuyển tiếp tin (ngoại lệ của BLOCK_FORWARDS)
CREATE TABLE IF NOT EXISTS forward_whitelist (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);

-- Người/kênh bị chặn cứng bất kể điểm số
CREATE TABLE IF NOT EXISTS blacklist (
    chat_id   INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    PRIMARY KEY (chat_id, entity_id)
);

-- @username được phép nhắc tới (lưu chữ thường, không có dấu @)
CREATE TABLE IF NOT EXISTS username_whitelist (
    chat_id  INTEGER NOT NULL,
    username TEXT    NOT NULL,
    PRIMARY KEY (chat_id, username)
);

-- Số điện thoại được phép xuất hiện
CREATE TABLE IF NOT EXISTS phone_whitelist (
    chat_id INTEGER NOT NULL,
    phone   TEXT    NOT NULL,
    PRIMARY KEY (chat_id, phone)
);

-- Cài đặt chung của bot (key-value)
CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Bot admin toàn cục (không phụ thuộc nhóm, được thêm bởi owner)
CREATE TABLE IF NOT EXISTS bot_admins (
    user_id INTEGER PRIMARY KEY
);

-- Từ/cụm từ cấm per-group: nhắn là bị ban ngay
CREATE TABLE IF NOT EXISTS keyword_blacklist (
    chat_id INTEGER NOT NULL,
    phrase  TEXT    NOT NULL,
    PRIMARY KEY (chat_id, phrase)
);
"""


# chat_id = 0 nghĩa là "áp dụng cho mọi nhóm" (cài từ chat riêng với bot).
GLOBAL = 0


class Storage:
    def __init__(self, path: Path):
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        # Với WAL, NORMAL vẫn an toàn trước khi ứng dụng sập (chỉ mất giao dịch
        # cuối nếu MẤT ĐIỆN đột ngột) nhưng bỏ được fsync mỗi lần commit.
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Thêm cột mới vào bảng đã tồn tại từ bản cũ.

        CREATE TABLE IF NOT EXISTS không đụng tới bảng đã có, nên cột thêm sau
        phải tự vá ở đây - nếu không, database cũ sẽ thiếu cột và sập.
        """
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(offences)")}
        if "name" not in cols:
            # Lưu tên người bị xử lý để /lastbans đọc được, khỏi phải gọi API.
            self._conn.execute(
                "ALTER TABLE offences ADD COLUMN name TEXT NOT NULL DEFAULT ''"
            )

    def close(self) -> None:
        self._conn.close()

    # -- helpers ----------------------------------------------------------

    async def _run(self, fn, *args):
        """Chạy thẳng trên event loop, KHÔNG đẩy sang thread.

        Các truy vấn ở đây đều là tra cứu theo khoá chính trên bảng nhỏ, mất
        khoảng 6µs. Đẩy qua asyncio.to_thread tốn thêm ~200µs điều phối - tức
        là chậm hơn 30 lần so với việc chỉ chặn event loop đúng 6µs đó.
        Vì mọi thứ chạy trên một luồng nên cũng không cần khoá.
        """
        return fn(*args)

    # -- members ----------------------------------------------------------

    def _touch_member(self, chat_id: int, user_id: int) -> tuple[int, int, bool]:
        now = int(time.time())
        cur = self._conn.execute(
            "SELECT first_seen, msg_count, trusted FROM members WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        row = cur.fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO members (chat_id, user_id, first_seen, msg_count) VALUES (?,?,?,1)",
                (chat_id, user_id, now),
            )
            self._conn.commit()
            return now, 1, False
        first_seen, msg_count, trusted = row
        self._conn.execute(
            "UPDATE members SET msg_count = msg_count + 1 WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        self._conn.commit()
        return first_seen, msg_count + 1, bool(trusted)

    async def touch_member(self, chat_id: int, user_id: int) -> tuple[int, int, bool]:
        """Ghi nhận một tin nhắn. Trả về (first_seen, msg_count, trusted)."""
        return await self._run(self._touch_member, chat_id, user_id)

    def _mark_joined(self, chat_id: int, user_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO members (chat_id, user_id, first_seen) VALUES (?,?,?)",
            (chat_id, user_id, int(time.time())),
        )
        self._conn.commit()

    async def mark_joined(self, chat_id: int, user_id: int) -> None:
        await self._run(self._mark_joined, chat_id, user_id)

    def _set_trusted(self, chat_id: int, user_id: int, trusted: bool) -> None:
        self._conn.execute(
            "INSERT INTO members (chat_id, user_id, first_seen, trusted) VALUES (?,?,?,?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET trusted=excluded.trusted",
            (chat_id, user_id, int(time.time()), int(trusted)),
        )
        self._conn.commit()

    async def set_trusted(self, chat_id: int, user_id: int, trusted: bool = True) -> None:
        await self._run(self._set_trusted, chat_id, user_id, trusted)

    # -- offences ---------------------------------------------------------

    def _count_offences(self, chat_id: int, user_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM offences WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        return int(cur.fetchone()[0])

    async def count_offences(self, chat_id: int, user_id: int) -> int:
        return await self._run(self._count_offences, chat_id, user_id)

    def _log_offence(
        self, chat_id: int, user_id: int, score: int, action: str,
        reasons: str, excerpt: str, name: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO offences (chat_id, user_id, ts, score, action, reasons, excerpt, name) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (chat_id, user_id, int(time.time()), score, action, reasons, excerpt[:400], name[:80]),
        )
        self._conn.commit()

    async def log_offence(
        self, chat_id: int, user_id: int, score: int, action: str,
        reasons: str, excerpt: str = "", name: str = "",
    ) -> None:
        await self._run(
            self._log_offence, chat_id, user_id, score, action, reasons, excerpt, name
        )

    def _recent_bans(self, limit: int) -> list[tuple]:
        cur = self._conn.execute(
            "SELECT id, chat_id, user_id, ts, score, reasons, excerpt, name "
            "FROM offences WHERE action IN ('ban','mute') ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    async def recent_bans(self, limit: int = 10) -> list[tuple]:
        """Các lượt ban/mute gần nhất trên MỌI nhóm, mới nhất trước."""
        return await self._run(self._recent_bans, limit)

    def _count_recent_bans(self, seconds: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM offences WHERE action IN ('ban','mute') AND ts >= ?",
            (int(time.time()) - seconds,),
        )
        return int(cur.fetchone()[0])

    async def count_recent_bans(self, seconds: int = 60) -> int:
        return await self._run(self._count_recent_bans, seconds)

    def _clear_offences(self, chat_id: int, user_id: int) -> int:
        cur = self._conn.execute(
            "DELETE FROM offences WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount

    async def clear_offences(self, chat_id: int, user_id: int) -> int:
        return await self._run(self._clear_offences, chat_id, user_id)

    def _stats(self, chat_id: int) -> tuple[int, int, int]:
        cur = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(action='ban'), 0), "
            "COALESCE(SUM(ts > ?), 0) FROM offences WHERE chat_id=?",
            (int(time.time()) - 86400, chat_id),
        )
        total, bans, last_day = cur.fetchone()
        return int(total), int(bans), int(last_day)

    async def stats(self, chat_id: int) -> tuple[int, int, int]:
        """(tổng vi phạm, số lần ban, số vi phạm 24h qua)."""
        return await self._run(self._stats, chat_id)

    # -- whitelist theo nhóm ----------------------------------------------

    def _get_whitelist(self, chat_id: int) -> set[str]:
        """Domain của nhóm + domain chung (chat_id=0)."""
        cur = self._conn.execute(
            "SELECT domain FROM chat_whitelist WHERE chat_id IN (?, ?)", (chat_id, GLOBAL)
        )
        return {r[0] for r in cur.fetchall()}

    async def get_whitelist(self, chat_id: int) -> set[str]:
        return await self._run(self._get_whitelist, chat_id)

    def _get_whitelist_own(self, chat_id: int) -> set[str]:
        """Chỉ domain đăng ký riêng cho chat_id này (dùng để hiển thị)."""
        cur = self._conn.execute("SELECT domain FROM chat_whitelist WHERE chat_id=?", (chat_id,))
        return {r[0] for r in cur.fetchall()}

    async def get_whitelist_own(self, chat_id: int) -> set[str]:
        return await self._run(self._get_whitelist_own, chat_id)

    def _add_whitelist(self, chat_id: int, domain: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO chat_whitelist (chat_id, domain) VALUES (?,?)",
            (chat_id, domain),
        )
        self._conn.commit()

    async def add_whitelist(self, chat_id: int, domain: str) -> None:
        await self._run(self._add_whitelist, chat_id, domain)

    def _remove_whitelist(self, chat_id: int, domain: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM chat_whitelist WHERE chat_id=? AND domain=?", (chat_id, domain)
        )
        self._conn.commit()
        return cur.rowcount

    async def remove_whitelist(self, chat_id: int, domain: str) -> int:
        return await self._run(self._remove_whitelist, chat_id, domain)

    # -- forward whitelist ------------------------------------------------

    def _in_fwd_whitelist(self, chat_id: int, user_id: int) -> bool:
        """Có trong danh sách của nhóm này, hoặc danh sách chung."""
        cur = self._conn.execute(
            "SELECT 1 FROM forward_whitelist WHERE chat_id IN (?, ?) AND user_id=?",
            (chat_id, GLOBAL, user_id),
        )
        return cur.fetchone() is not None

    async def in_fwd_whitelist(self, chat_id: int, user_id: int) -> bool:
        return await self._run(self._in_fwd_whitelist, chat_id, user_id)

    def _get_fwd_whitelist(self, chat_id: int) -> list[int]:
        cur = self._conn.execute(
            "SELECT user_id FROM forward_whitelist WHERE chat_id=?", (chat_id,)
        )
        return [r[0] for r in cur.fetchall()]

    async def get_fwd_whitelist(self, chat_id: int) -> list[int]:
        return await self._run(self._get_fwd_whitelist, chat_id)

    def _add_fwd_whitelist(self, chat_id: int, user_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO forward_whitelist (chat_id, user_id) VALUES (?,?)",
            (chat_id, user_id),
        )
        self._conn.commit()

    async def add_fwd_whitelist(self, chat_id: int, user_id: int) -> None:
        await self._run(self._add_fwd_whitelist, chat_id, user_id)

    def _remove_fwd_whitelist(self, chat_id: int, user_id: int) -> int:
        cur = self._conn.execute(
            "DELETE FROM forward_whitelist WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount

    async def remove_fwd_whitelist(self, chat_id: int, user_id: int) -> int:
        return await self._run(self._remove_fwd_whitelist, chat_id, user_id)

    def _count_fwd_whitelist(self, chat_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM forward_whitelist WHERE chat_id=?", (chat_id,)
        )
        return int(cur.fetchone()[0])

    async def count_fwd_whitelist(self, chat_id: int) -> int:
        return await self._run(self._count_fwd_whitelist, chat_id)

    # -- blacklist (chặn cứng user/kênh) ---------------------------------

    def _in_blacklist(self, chat_id: int, entity_id: int) -> bool:
        """Bị chặn ở nhóm này, hoặc bị chặn chung ở mọi nhóm."""
        cur = self._conn.execute(
            "SELECT 1 FROM blacklist WHERE chat_id IN (?, ?) AND entity_id=?",
            (chat_id, GLOBAL, entity_id),
        )
        return cur.fetchone() is not None

    async def in_blacklist(self, chat_id: int, entity_id: int) -> bool:
        return await self._run(self._in_blacklist, chat_id, entity_id)

    def _get_blacklist(self, chat_id: int) -> list[int]:
        cur = self._conn.execute(
            "SELECT entity_id FROM blacklist WHERE chat_id=?", (chat_id,)
        )
        return [r[0] for r in cur.fetchall()]

    async def get_blacklist(self, chat_id: int) -> list[int]:
        return await self._run(self._get_blacklist, chat_id)

    def _add_blacklist(self, chat_id: int, entity_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO blacklist (chat_id, entity_id) VALUES (?,?)",
            (chat_id, entity_id),
        )
        self._conn.commit()

    async def add_blacklist(self, chat_id: int, entity_id: int) -> None:
        await self._run(self._add_blacklist, chat_id, entity_id)

    def _remove_blacklist(self, chat_id: int, entity_id: int) -> int:
        cur = self._conn.execute(
            "DELETE FROM blacklist WHERE chat_id=? AND entity_id=?", (chat_id, entity_id)
        )
        self._conn.commit()
        return cur.rowcount

    async def remove_blacklist(self, chat_id: int, entity_id: int) -> int:
        return await self._run(self._remove_blacklist, chat_id, entity_id)

    def _count_blacklist(self, chat_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM blacklist WHERE chat_id=?", (chat_id,)
        )
        return int(cur.fetchone()[0])

    async def count_blacklist(self, chat_id: int) -> int:
        return await self._run(self._count_blacklist, chat_id)

    # -- @username được phép ----------------------------------------------

    def _get_usernames(self, chat_id: int) -> set[str]:
        """Của nhóm + dùng chung (chat_id=0)."""
        cur = self._conn.execute(
            "SELECT username FROM username_whitelist WHERE chat_id IN (?, ?)", (chat_id, GLOBAL)
        )
        return {r[0] for r in cur.fetchall()}

    async def get_usernames(self, chat_id: int) -> set[str]:
        return await self._run(self._get_usernames, chat_id)

    def _get_usernames_own(self, chat_id: int) -> set[str]:
        cur = self._conn.execute(
            "SELECT username FROM username_whitelist WHERE chat_id=?", (chat_id,)
        )
        return {r[0] for r in cur.fetchall()}

    async def get_usernames_own(self, chat_id: int) -> set[str]:
        return await self._run(self._get_usernames_own, chat_id)

    def _add_username(self, chat_id: int, username: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO username_whitelist (chat_id, username) VALUES (?,?)",
            (chat_id, username),
        )
        self._conn.commit()

    async def add_username(self, chat_id: int, username: str) -> None:
        await self._run(self._add_username, chat_id, username)

    def _remove_username(self, chat_id: int, username: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM username_whitelist WHERE chat_id=? AND username=?", (chat_id, username)
        )
        self._conn.commit()
        return cur.rowcount

    async def remove_username(self, chat_id: int, username: str) -> int:
        return await self._run(self._remove_username, chat_id, username)

    def _count_usernames(self, chat_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM username_whitelist WHERE chat_id=?", (chat_id,)
        )
        return int(cur.fetchone()[0])

    async def count_usernames(self, chat_id: int) -> int:
        return await self._run(self._count_usernames, chat_id)

    # -- số điện thoại được phép ------------------------------------------

    def _get_phones(self, chat_id: int) -> set[str]:
        cur = self._conn.execute(
            "SELECT phone FROM phone_whitelist WHERE chat_id IN (?, ?)", (chat_id, GLOBAL)
        )
        return {r[0] for r in cur.fetchall()}

    async def get_phones(self, chat_id: int) -> set[str]:
        return await self._run(self._get_phones, chat_id)

    def _get_phones_own(self, chat_id: int) -> set[str]:
        cur = self._conn.execute(
            "SELECT phone FROM phone_whitelist WHERE chat_id=?", (chat_id,)
        )
        return {r[0] for r in cur.fetchall()}

    async def get_phones_own(self, chat_id: int) -> set[str]:
        return await self._run(self._get_phones_own, chat_id)

    def _add_phone(self, chat_id: int, phone: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO phone_whitelist (chat_id, phone) VALUES (?,?)",
            (chat_id, phone),
        )
        self._conn.commit()

    async def add_phone(self, chat_id: int, phone: str) -> None:
        await self._run(self._add_phone, chat_id, phone)

    def _remove_phone(self, chat_id: int, phone: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM phone_whitelist WHERE chat_id=? AND phone=?", (chat_id, phone)
        )
        self._conn.commit()
        return cur.rowcount

    async def remove_phone(self, chat_id: int, phone: str) -> int:
        return await self._run(self._remove_phone, chat_id, phone)

    def _count_phones(self, chat_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM phone_whitelist WHERE chat_id=?", (chat_id,)
        )
        return int(cur.fetchone()[0])

    async def count_phones(self, chat_id: int) -> int:
        return await self._run(self._count_phones, chat_id)

    # -- cài đặt bot (key-value) ------------------------------------------

    def _get_setting(self, key: str) -> str | None:
        cur = self._conn.execute("SELECT value FROM bot_settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    async def get_setting(self, key: str) -> str | None:
        return await self._run(self._get_setting, key)

    def _set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    async def set_setting(self, key: str, value: str) -> None:
        await self._run(self._set_setting, key, value)

    # -- bot admins (toàn cục) --------------------------------------------

    def _is_bot_admin(self, user_id: int) -> bool:
        cur = self._conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return cur.fetchone() is not None

    async def is_bot_admin(self, user_id: int) -> bool:
        return await self._run(self._is_bot_admin, user_id)

    def _get_bot_admins(self) -> list[int]:
        cur = self._conn.execute("SELECT user_id FROM bot_admins ORDER BY user_id")
        return [r[0] for r in cur.fetchall()]

    async def get_bot_admins(self) -> list[int]:
        return await self._run(self._get_bot_admins)

    def _add_bot_admin(self, user_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,)
        )
        self._conn.commit()

    async def add_bot_admin(self, user_id: int) -> None:
        await self._run(self._add_bot_admin, user_id)

    def _remove_bot_admin(self, user_id: int) -> int:
        cur = self._conn.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
        self._conn.commit()
        return cur.rowcount

    async def remove_bot_admin(self, user_id: int) -> int:
        return await self._run(self._remove_bot_admin, user_id)

    # -- keyword blacklist (per-group) ------------------------------------

    def _get_keywords(self, chat_id: int) -> list[str]:
        """Chỉ từ cấm đăng ký riêng cho chat_id này (dùng để hiển thị)."""
        cur = self._conn.execute(
            "SELECT phrase FROM keyword_blacklist WHERE chat_id=? ORDER BY phrase", (chat_id,)
        )
        return [r[0] for r in cur.fetchall()]

    async def get_keywords(self, chat_id: int) -> list[str]:
        return await self._run(self._get_keywords, chat_id)

    def _get_keywords_effective(self, chat_id: int) -> list[str]:
        """Từ cấm của nhóm + từ cấm chung (chat_id=0) — dùng khi quét tin nhắn."""
        cur = self._conn.execute(
            "SELECT DISTINCT phrase FROM keyword_blacklist WHERE chat_id IN (?, ?)",
            (chat_id, GLOBAL),
        )
        return [r[0] for r in cur.fetchall()]

    async def get_keywords_effective(self, chat_id: int) -> list[str]:
        return await self._run(self._get_keywords_effective, chat_id)

    def _add_keyword(self, chat_id: int, phrase: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO keyword_blacklist (chat_id, phrase) VALUES (?,?)",
            (chat_id, phrase),
        )
        self._conn.commit()

    async def add_keyword(self, chat_id: int, phrase: str) -> None:
        await self._run(self._add_keyword, chat_id, phrase)

    def _remove_keyword(self, chat_id: int, phrase: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM keyword_blacklist WHERE chat_id=? AND phrase=?", (chat_id, phrase)
        )
        self._conn.commit()
        return cur.rowcount

    async def remove_keyword(self, chat_id: int, phrase: str) -> int:
        return await self._run(self._remove_keyword, chat_id, phrase)

    def _count_keywords(self, chat_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM keyword_blacklist WHERE chat_id=?", (chat_id,)
        )
        return int(cur.fetchone()[0])

    async def count_keywords(self, chat_id: int) -> int:
        return await self._run(self._count_keywords, chat_id)
