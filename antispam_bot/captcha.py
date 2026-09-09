"""Captcha khi vào nhóm: chặn đội quân tài khoản ảo TRƯỚC khi chúng kịp đăng gì.

VÌ SAO
Mọi luật khác của bot đều xử lý SAU khi tin nhắn đã hiện ra. Chiến dịch 334 tài
khoản đo được là 334 lần một tin rác lọt vào nhóm rồi mới bị xoá. Captcha chặn
ở cửa: vào nhóm là bị khoá mõm, bấm đúng nút mới được nói. Tài khoản ảo điều
khiển bằng script hầu như không bấm - đây là lý do Shieldy/Rose đều làm vậy và
là thứ hiệu quả nhất chống bot army.

KHÁC GÌ BOT KHÁC
- Người thật qua captcha ở MỘT nhóm thì mọi nhóm khác không hỏi lại. Chủ bot
  có 20 nhóm; bắt một người bấm 20 lần là tự đuổi khách.
- Trượt captcha thì chỉ bị đá (ban rồi gỡ ngay) để còn vào lại thử tiếp.
  Trượt tới lần thứ ba mới là ban thật - lúc đó không còn là người vô ý nữa.
- Acc seeding, admin, người đã được tin cậy: không bao giờ bị hỏi.

VÌ SAO MẶC ĐỊNH TẮT
Bot này chạy im lặng; captcha bắt buộc phải hiện MỘT tin trong nhóm (tự xoá
ngay khi xong). Chủ bot tự quyết có đánh đổi không - bật trong menu công tắc.
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup

# Trượt liên tiếp bấy nhiêu lần thì ban thật thay vì đá.
TRUOT_TOI_DA = 3

# Người đã qua captcha được nhớ bấy lâu, tính bằng ngày. Sau đó vào nhóm mới
# thì hỏi lại - đủ dài để không phiền, đủ ngắn để tài khoản bị hack lâu ngày
# không hưởng mãi.
NHO_NGAY = 90

# Cửa sổ đếm "đợt vào dồn dập", tính bằng giây. Đo trên 30 ngày dữ liệu thật:
# đợt dày nhất là 26 người trong 2 phút - nhóm bình thường không bao giờ như thế.
CUA_SO_DOT_VAO = 120


def ghi_luot_vao(hang, luc: float, cua_so: float) -> int:
    """Ghi một lượt vào nhóm, trả về số lượt trong cửa sổ vừa rồi."""
    hang.append(luc)
    while hang and hang[0] < luc - cua_so:
        hang.popleft()
    return len(hang)


# Quyền lúc bị khoá: không gửi được gì cả.
KHOA = ChatPermissions(can_send_messages=False)


@dataclass
class DangCho:
    """Một người đang chờ bấm captcha."""
    chat_id: int
    user_id: int
    message_id: int
    het_han: float
    ten: str = ""


@dataclass
class SoCaptcha:
    """Sổ theo dõi trong bộ nhớ. Mất khi khởi động lại - người đang chờ lúc đó
    vẫn bị khoá, admin gỡ tay bằng /unban hoặc họ rời rồi vào lại."""
    dang_cho: dict[tuple[int, int], DangCho] = field(default_factory=dict)
    truot: dict[int, int] = field(default_factory=dict)  # user_id -> số lần trượt

    def them(self, cho: DangCho) -> None:
        self.dang_cho[(cho.chat_id, cho.user_id)] = cho

    def lay(self, chat_id: int, user_id: int) -> DangCho | None:
        return self.dang_cho.get((chat_id, user_id))

    def xoa(self, chat_id: int, user_id: int) -> DangCho | None:
        return self.dang_cho.pop((chat_id, user_id), None)

    def ghi_truot(self, user_id: int) -> int:
        self.truot[user_id] = self.truot.get(user_id, 0) + 1
        return self.truot[user_id]

    def quen_truot(self, user_id: int) -> None:
        self.truot.pop(user_id, None)

    def don(self) -> list[DangCho]:
        """Trả về và bỏ những mục đã quá hạn từ lâu mà job không dọn được."""
        bay_gio = time.time()
        cu = [c for c in self.dang_cho.values() if bay_gio - c.het_han > 600]
        for c in cu:
            self.dang_cho.pop((c.chat_id, c.user_id), None)
        return cu


def noi_dung(ten: str, giay: int) -> str:
    ten = html.escape(ten or "bạn")
    phut = max(1, giay // 60)
    return (
        f"👋 <b>{ten}</b>, bấm nút bên dưới để xác nhận bạn là người thật.\n"
        f"<i>Có {phut} phút. Không bấm sẽ bị mời ra, vào lại được ngay.</i>"
    )


def ban_phim(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tôi là người thật", callback_data=f"cap:{user_id}")
    ]])
