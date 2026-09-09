"""Menu nút bấm - toàn bộ thao tác quản trị trong vài lần chạm.

TRIẾT LÝ
Rose, Combot, Shieldy đều đi theo lối "gõ lệnh, đọc hướng dẫn". Với 45 lệnh
thì người dùng phải nhớ tên, nhớ cú pháp, nhớ lệnh nào đi với lệnh nào. Bot này
đảo lại: MỌI thứ đều đến được từ /start bằng nút, lệnh gõ chỉ là đường tắt cho
người đã quen.

Mỗi màn hình trả lời đúng ba câu: đang có gì, làm được gì tiếp, quay lại đâu.

Module này chỉ DỰNG văn bản và bàn phím từ dữ liệu đã có sẵn - không gọi
Telegram, không đụng database - nên kiểm thử được mà không cần bot chạy.
Phần xử lý nút nằm ở bot.py (on_menu_button).

Mã callback: "m:<màn hình>[:<tham số>]". Tiền tố "m:" để không đụng "p:"
(bảng cũ) và "cap:" (captcha).
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Mỗi màn hình hiển thị tối đa bấy nhiêu dòng danh sách. Quá thì ghi "...và N
# mục nữa" và chỉ sang lệnh /list_* để xem hết.
TOI_DA_DONG = 15


def _nut(nhan: str, ma: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(nhan, callback_data=f"m:{ma}")


def _ve_menu() -> list[InlineKeyboardButton]:
    return [_nut("◀️ Menu", "main")]


def _cat(ds: list[str]) -> str:
    """Rút gọn danh sách dài cho vừa một màn hình điện thoại."""
    if not ds:
        return "  <i>(trống)</i>"
    ra = "\n".join(f"• {d}" for d in ds[:TOI_DA_DONG])
    if len(ds) > TOI_DA_DONG:
        ra += f"\n  <i>...và {len(ds) - TOI_DA_DONG} mục nữa</i>"
    return ra


# --------------------------------------------------------------------------
# Màn hình chính
# --------------------------------------------------------------------------

@dataclass
class TomTat:
    """Số liệu để vẽ màn hình chính."""
    so_nhom: int
    che_do: str            # ban / mute / delete / report
    dang_ngung: bool
    ban_24h: int
    so_tu_cam: int
    so_seeding: int
    so_chien_dich: int
    captcha: bool = False


def man_chinh(tt: TomTat, la_owner: bool) -> tuple[str, InlineKeyboardMarkup]:
    trang_thai = "⏸ <b>ĐANG NGƯNG</b>" if tt.dang_ngung else (
        "🧪 chế độ thử (chỉ ghi log)" if tt.che_do == "report" else f"🟢 đang chạy · {tt.che_do}"
    )
    chu = (
        "🛡 <b>Bot chống spam</b>\n"
        f"{trang_thai}\n"
        f"Nhóm: <b>{tt.so_nhom}</b> · Ban 24h: <b>{tt.ban_24h}</b>"
        f" · Từ cấm: <b>{tt.so_tu_cam}</b> · Seeding: <b>{tt.so_seeding}</b>\n"
        + (f"📡 Đang theo dõi <b>{tt.so_chien_dich}</b> chiến dịch rải\n" if tt.so_chien_dich else "")
        + ("🔐 Captcha đang bật\n" if tt.captcha else "")
        + "\n<i>Nhắn ở đây = áp dụng cho mọi nhóm. Muốn riêng một nhóm thì gõ lệnh trong nhóm đó.</i>"
    )
    hang_nhanh = (
        [_nut("▶️ Bật lại", "resume")] if tt.dang_ngung
        else [_nut("⏸ Ngưng 30'", "pause:30"), _nut("⏸ Ngưng 2h", "pause:120")]
    )
    hang_che_do = (
        [_nut("🔨 Bật ban lại", "act:ban")] if tt.che_do == "report"
        else [_nut("🧪 Chế độ thử (không ban)", "act:report")]
    )
    ban_phim = [
        [_nut("👥 Acc seeding", "seed"), _nut("🚫 Từ cấm", "tucam")],
        [_nut("🔗 Link & @", "link"), _nut("⚙️ Công tắc", "ct")],
        [_nut("📡 Chiến dịch", "cd"), _nut("🧠 Đã học", "hoc")],
        [_nut("📋 Ban gần đây", "ban"), _nut("↩️ Gỡ ban vừa rồi", "undo")],
        hang_nhanh,
        hang_che_do,
        [_nut("📊 Trạng thái chi tiết", "tt"), _nut("📖 Hướng dẫn", "hd")],
    ]
    return chu, InlineKeyboardMarkup(ban_phim)


# --------------------------------------------------------------------------
# Acc seeding
# --------------------------------------------------------------------------

def man_seeding(ids: list[int], ten: dict[int, str]) -> tuple[str, InlineKeyboardMarkup]:
    dong = [f"{html.escape(ten[u])} (<code>{u}</code>)" if ten.get(u) else f"<code>{u}</code>"
            for u in ids]
    chu = (
        "👥 <b>Acc seeding</b> — được phép forward, nhắc @, đăng trùng nhau\n"
        f"Áp dụng mọi nhóm ({len(ids)}):\n{_cat(dong)}\n\n"
        "<i>Cách nhanh nhất: bảo từng acc bấm Start với bot, rồi bấm 🔍 Quét.</i>"
    )
    return chu, InlineKeyboardMarkup([
        [_nut("➕ Thêm ID / @username", "nhap:user"), _nut("🔍 Quét tự động", "scan")],
        [_nut("➖ Bớt", "nhap:deluser"), *_ve_menu()],
    ])


# --------------------------------------------------------------------------
# Từ cấm
# --------------------------------------------------------------------------

def man_tu_cam(so_tu: int, bo_da_nap: dict[str, tuple[str, bool, int]]) -> tuple[str, InlineKeyboardMarkup]:
    """bo_da_nap: khoá -> (nhãn, đã nạp?, số cụm)."""
    chu = (
        "🚫 <b>Từ cấm</b> — ai gửi là ban ngay (có xét ngữ cảnh)\n"
        f"Đang có <b>{so_tu}</b> cụm áp dụng mọi nhóm.\n\n"
        "Bấm một bộ dựng sẵn để nạp / gỡ:"
    )
    hang = [
        [_nut(f"{'✅' if nap else '⬜'} {nhan} ({n})", f"preset:{khoa}")]
        for khoa, (nhan, nap, n) in bo_da_nap.items()
    ]
    hang.append([_nut("➕ Thêm cụm từ", "nhap:word"), _nut("➖ Bớt", "nhap:delword")])
    hang.append([_nut("📋 Xem hết", "ds:word"), *_ve_menu()])
    return chu, InlineKeyboardMarkup(hang)


# --------------------------------------------------------------------------
# Link & @
# --------------------------------------------------------------------------

def man_link(domains: list[str], usernames: list[str], phones: list[str]) -> tuple[str, InlineKeyboardMarkup]:
    chu = (
        "🔗 <b>Được phép xuất hiện</b> (mọi nhóm)\n\n"
        f"<b>Link</b> ({len(domains)}):\n{_cat([html.escape(d) for d in sorted(domains)])}\n\n"
        f"<b>@username</b> ({len(usernames)}):\n{_cat(['@' + html.escape(u) for u in sorted(usernames)])}\n\n"
        f"<b>Số điện thoại</b> ({len(phones)}):\n{_cat([html.escape(p) for p in sorted(phones)])}\n\n"
        "<i>Link/@/số ngoài danh sách này bị chặn (nếu công tắc tương ứng đang bật). "
        "Admin nhóm tự động được phép nhắc @.</i>"
    )
    return chu, InlineKeyboardMarkup([
        [_nut("➕ Link", "nhap:link"), _nut("➕ @username", "nhap:at"), _nut("➕ Số ĐT", "nhap:phone")],
        [_nut("➖ Bớt link", "nhap:dellink"), _nut("➖ Bớt @", "nhap:delat")],
        _ve_menu(),
    ])


# --------------------------------------------------------------------------
# Các màn hình chỉ-đọc: bọc văn bản có sẵn bằng nút quay lại
# --------------------------------------------------------------------------

def man_van_ban(chu: str, them: list[list[InlineKeyboardButton]] | None = None) -> tuple[str, InlineKeyboardMarkup]:
    return chu, InlineKeyboardMarkup([*(them or []), _ve_menu()])


def man_cong_tac(co: dict[str, bool], nhan: dict[str, str]) -> tuple[str, InlineKeyboardMarkup]:
    chu = (
        "⚙️ <b>Công tắc</b>\n\n"
        "Bấm để đảo trạng thái. Có hiệu lực ngay, không cần khởi động lại.\n"
        "<i>Bot tự tắt được vài công tắc ở đây khi bạn gỡ ban một luật quá nhiều lần — xem 🧠 Đã học.</i>"
    )
    hang = [[_nut(f"{'✅' if co[t] else '⬜'}  {nhan[t]}", f"cong:{t}")] for t in nhan]
    hang.append(_ve_menu())
    return chu, InlineKeyboardMarkup(hang)


# --------------------------------------------------------------------------
# Nhập liệu: mỗi loại một câu hỏi, trả lời xong là xong
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CachNhap:
    hoi: str                     # câu hỏi hiện cho người dùng
    lenh: str                    # lệnh gõ tương đương (để nhắc)
    ve: str = "main"             # màn hình quay về sau khi xong


NHAP: dict[str, CachNhap] = {
    "user":    CachNhap("Gửi <b>ID hoặc @username</b> của acc seeding.\nNhiều acc: cách nhau bằng dấu phẩy.", "/add_user", "seed"),
    "deluser": CachNhap("Gửi <b>ID hoặc @username</b> cần bớt khỏi danh sách seeding.", "/delete_user", "seed"),
    "word":    CachNhap("Gửi <b>cụm từ</b> cần cấm.\nNhiều cụm: cách nhau bằng dấu phẩy. VD: <code>lừa đảo, scam</code>", "/add_word", "tucam"),
    "delword": CachNhap("Gửi <b>cụm từ</b> cần bỏ cấm.", "/delete_word", "tucam"),
    "link":    CachNhap("Gửi <b>domain</b> được phép. VD: <code>shopee.vn</code> hoặc <code>t.me/kenhcuaban</code>", "/add_link", "link"),
    "dellink": CachNhap("Gửi <b>domain</b> cần bỏ khỏi danh sách cho phép.", "/delete_link", "link"),
    "at":      CachNhap("Gửi <b>@username</b> được phép nhắc tới.", "/add_username", "link"),
    "delat":   CachNhap("Gửi <b>@username</b> cần bỏ khỏi danh sách cho phép.", "/delete_username", "link"),
    "phone":   CachNhap("Gửi <b>số điện thoại</b> được phép xuất hiện.", "/add_phone", "link"),
    "block":   CachNhap("Gửi <b>ID hoặc @username</b> cần chặn cứng ở mọi nhóm.", "/block_user", "main"),
}


def cau_hoi_nhap(loai: str) -> str:
    c = NHAP[loai]
    return (
        f"✏️ {c.hoi}\n\n"
        f"<i>Trả lời tin này. Hoặc gõ thẳng: <code>{c.lenh} ...</code>. "
        f"Gõ <code>huy</code> để bỏ.</i>"
    )
