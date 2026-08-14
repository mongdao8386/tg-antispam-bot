"""Bảng điều khiển web (CMS) chạy chung tiến trình với bot.

Vì sao có nó dù đã có nút bấm trong Telegram: sửa hàng loạt. Dán 50 từ cấm
một lúc, xem cạnh nhau nhiều danh sách, gỡ nhiều người liên tiếp - những việc
này trên khung chat rất cực.

BẢO MẬT - đọc kỹ:
  * Mặc định chỉ nghe ở 127.0.0.1, tức là KHÔNG ai từ Internet vào được.
    Muốn mở cho điện thoại thì đọc phần hướng dẫn ở README (Cloudflare Tunnel).
  * Vào bằng liên kết dùng một lần do bot cấp qua lệnh /web. Không có mật khẩu
    để lộ, không có form đăng nhập để dò.
  * Phiên đăng nhập hết hạn sau WEB_SESSION_HOURS giờ.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from typing import Any

log = logging.getLogger("antispam.web")

AVAILABLE = False
UNAVAILABLE_REASON = ""

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    UNAVAILABLE_REASON = str(exc).strip().splitlines()[-1] if str(exc) else type(exc).__name__

# Vé vào cửa dùng một lần: mã -> hết hạn lúc nào
_tickets: dict[str, float] = {}
# Phiên đã đăng nhập: mã -> hết hạn lúc nào
_sessions: dict[str, float] = {}

TICKET_TTL = 300  # giây - vé chỉ sống 5 phút


def new_ticket() -> str:
    """Cấp một vé vào cửa dùng một lần (bot gọi khi có lệnh /web)."""
    _dọn()
    ma = secrets.token_urlsafe(24)
    _tickets[ma] = time.time() + TICKET_TTL
    return ma


def _dọn() -> None:
    now = time.time()
    for kho in (_tickets, _sessions):
        for k in [k for k, het in kho.items() if het < now]:
            kho.pop(k, None)


def _phien_hop_le(request: "Request") -> bool:
    ma = request.cookies.get("sid")
    if not ma:
        return False
    het = _sessions.get(ma)
    return bool(het and het > time.time())


def _sdt(raw: str) -> str:
    return re.sub(r"[\s.\-()]", "", raw.strip())


def build_app(bot_app: Any, session_hours: int = 12) -> "FastAPI":
    """Dựng ứng dụng web. bot_app là Application của python-telegram-bot."""
    from . import control
    from .storage import GLOBAL

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def db():
        return bot_app.bot_data["db"]

    def cfg():
        return bot_app.bot_data["cfg"]

    def _lam_moi_cache() -> None:
        bot_app.bot_data.get("rules_cache", {}).clear()
        bot_app.bot_data.pop("bot_admin_cache", None)

    @api.middleware("http")
    async def chan_cua(request: Request, call_next):
        duong_dan = request.url.path
        if duong_dan.startswith("/vao/") or duong_dan == "/health":
            return await call_next(request)
        if not _phien_hop_le(request):
            if duong_dan.startswith("/api/"):
                return JSONResponse({"loi": "chưa đăng nhập"}, status_code=401)
            return HTMLResponse(TRANG_CHUA_DANG_NHAP, status_code=401)
        return await call_next(request)

    @api.get("/health")
    async def health():
        return {"ok": True}

    @api.get("/vao/{ma}")
    async def vao(ma: str):
        """Đổi vé dùng một lần lấy phiên đăng nhập."""
        _dọn()
        het = _tickets.pop(ma, None)   # pop: vé dùng xong là huỷ
        if not het or het < time.time():
            return HTMLResponse(TRANG_VE_HET_HAN, status_code=403)
        sid = secrets.token_urlsafe(32)
        _sessions[sid] = time.time() + session_hours * 3600
        r = RedirectResponse("/", status_code=302)
        r.set_cookie("sid", sid, httponly=True, samesite="lax",
                     max_age=session_hours * 3600)
        return r

    @api.get("/", response_class=HTMLResponse)
    async def trang_chu():
        return TRANG_CHINH

    # ---------------- API ----------------

    @api.get("/api/trangthai")
    async def trang_thai():
        d, c = db(), cfg()
        dang_ngung, con_lai = await control.is_paused(d)
        nhom = []
        raw = await d.get_setting("home_group") or ""
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            gid = int(part)
            try:
                chat = await bot_app.bot.get_chat(gid)
                ten = chat.title or str(gid)
            except Exception:  # noqa: BLE001
                ten = f"(không truy cập được) {gid}"
            tong, ban, ngay = await d.stats(gid)
            nhom.append({"id": gid, "ten": ten, "tong": tong, "ban": ban, "ngay": ngay})
        return {
            "dang_ngung": dang_ngung,
            "con_lai_phut": con_lai // 60,
            "che_do": await control.effective_action(d, c),
            "che_do_env": c.action,
            "ban_1h": await d.count_recent_bans(3600),
            "phanh_luc": await control.brake_info(d),
            "nhom": nhom,
            "qr": c.scan_qr,
            "ocr": c.scan_ocr,
        }

    @api.post("/api/dieukhien")
    async def dieu_khien(payload: dict):
        d, c = db(), cfg()
        viec = payload.get("viec")
        if viec == "ngung":
            await control.pause(d, int(payload.get("phut", 30)))
        elif viec == "batlai":
            await control.resume(d)
        elif viec == "chedo":
            che_do = payload.get("gia_tri", "")
            if che_do == "macdinh":
                await control.clear_action(d)
            else:
                from .config import VALID_ACTIONS
                if che_do not in VALID_ACTIONS:
                    return JSONResponse({"loi": "chế độ không hợp lệ"}, status_code=400)
                await control.set_action(d, che_do)
        else:
            return JSONResponse({"loi": "việc không hợp lệ"}, status_code=400)
        return {"ok": True}

    # Mỗi danh sách khai báo một lần, khỏi viết 5 bộ endpoint giống nhau.
    DANH_SACH = {
        "tucam":   ("get_keywords",      "add_keyword",      "remove_keyword",      str),
        "seeding": ("get_fwd_whitelist", "add_fwd_whitelist", "remove_fwd_whitelist", int),
        "chancung": ("get_blacklist",    "add_blacklist",    "remove_blacklist",    int),
        "domain":  ("get_whitelist_own", "add_whitelist",    "remove_whitelist",    str),
        "at":      ("get_usernames_own", "add_username",     "remove_username",     str),
        "sdt":     ("get_phones_own",    "add_phone",        "remove_phone",        str),
    }

    @api.get("/api/danhsach/{ten}")
    async def doc_danh_sach(ten: str):
        if ten not in DANH_SACH:
            return JSONResponse({"loi": "không có danh sách này"}, status_code=404)
        doc, _, _, _ = DANH_SACH[ten]
        muc = await getattr(db(), doc)(GLOBAL)
        return {"muc": sorted(str(m) for m in muc)}

    @api.post("/api/danhsach/{ten}")
    async def sua_danh_sach(ten: str, payload: dict):
        if ten not in DANH_SACH:
            return JSONResponse({"loi": "không có danh sách này"}, status_code=404)
        _, them, xoa, kieu = DANH_SACH[ten]
        d = db()

        def chuan(v: str):
            v = v.strip()
            if ten == "at":
                return v.lstrip("@").lower()
            if ten == "sdt":
                return _sdt(v)
            if ten == "domain":
                v = v.lower().removeprefix("https://").removeprefix("http://")
                return v.removeprefix("www.").rstrip("/")
            return v

        so = 0
        for raw in payload.get("muc", []):
            giatri = chuan(str(raw))
            if not giatri:
                continue
            try:
                giatri = kieu(giatri)
            except ValueError:
                continue
            if payload.get("xoa"):
                so += await getattr(d, xoa)(GLOBAL, giatri) or 0
            else:
                await getattr(d, them)(GLOBAL, giatri)
                so += 1
        _lam_moi_cache()
        return {"ok": True, "so": so}

    @api.get("/api/banganday")
    async def ban_gan_day(limit: int = 25):
        rows = await db().recent_bans(min(limit, 100))
        return {"muc": [
            {"id": r[0], "nhom": r[1], "uid": r[2], "luc": r[3],
             "diem": r[4], "ly_do": r[5], "trich": r[6], "ten": r[7]}
            for r in rows
        ]}

    @api.post("/api/goban")
    async def go_ban(payload: dict):
        try:
            uid = int(payload["uid"])
            gid = int(payload["nhom"])
        except (KeyError, ValueError, TypeError):
            return JSONResponse({"loi": "thiếu uid hoặc nhóm"}, status_code=400)
        try:
            await bot_app.bot.unban_chat_member(gid, uid, only_if_banned=True)
            await db().clear_offences(gid, uid)
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"loi": str(exc)}, status_code=400)

    @api.get("/api/preset")
    async def doc_preset():
        from . import presets
        return {"bo": [
            {"ma": k, "ten": v[0], "so": len(v[1])} for k, v in presets.PRESETS.items()
        ]}

    @api.post("/api/preset")
    async def nap_preset(payload: dict):
        from . import presets
        ten = payload.get("ma")
        if ten not in presets.PRESETS:
            return JSONResponse({"loi": "không có bộ này"}, status_code=404)
        d = db()
        cum = presets.PRESETS[ten][1]
        so = 0
        for p in cum:
            if payload.get("xoa"):
                so += await d.remove_keyword(GLOBAL, p) or 0
            else:
                await d.add_keyword(GLOBAL, p)
                so += 1
        _lam_moi_cache()
        return {"ok": True, "so": so}

    return api


from .web_ui import TRANG_CHINH, TRANG_CHUA_DANG_NHAP, TRANG_VE_HET_HAN  # noqa: E402
