"""Tự học từ những lần admin gỡ ban.

Ý TƯỞNG
Mỗi lần bạn gõ /undo là bạn đang nói "luật này bắt sai". Đó là dữ liệu quý
nhất mà bot có - đúng người, đúng nhóm, đúng kiểu tin nhắn của bạn, không phải
suy đoán của người viết bot. Trước đây thông tin đó bị vứt đi.

Nay bot đếm: luật nào bị gỡ bao nhiêu lần. Rồi làm hai việc.

1. THA NGAY CÁI ĐÃ BẮT SAI
   Gỡ một lượt ban vì "chiến dịch rải" thì bot tha luôn nội dung đó - lần sau
   ai đăng lại cũng không bị nữa. Đây là hành động hẹp, chỉ đụng đúng nội dung
   bạn vừa tha, nên gần như không thể sai.

2. TỰ TẮT LUẬT BẮT SAI QUÁ NHIỀU
   Một luật bị gỡ tới NGUONG lần là nó không hợp với nhóm của bạn. Bot tự tắt
   công tắc tương ứng và báo rõ. Ranh giới cố ý hẹp: chỉ tắt được những công
   tắc mà chính bạn cũng tắt được bằng tay trong /panel - bot không tự nghĩ ra
   luật mới, không tự nới lỏng thứ gì nằm ngoài tầm tay bạn.

VÌ SAO KHÔNG DÙNG TRỌNG SỐ HỌC MÁY
Đã bỏ hệ thống điểm số vì nó không giải thích được. Học ra một mớ trọng số
cũng y hệt vậy, chỉ khác là còn khó đoán hơn. Đếm và tắt thì đọc log là hiểu
ngay chuyện gì đã xảy ra.
"""

from __future__ import annotations

import re

# Cắt phần chi tiết sau dấu hai chấm: "link lạ: abc.com" -> "link lạ".
# Giữ tên luật thôi thì mới cộng dồn được các lần gỡ về cùng một mối.
_CHI_TIET_RE = re.compile(r"\s*[:(].*$")

# Luật có con số thay đổi mỗi lần, phải quy về một tên chung.
_QUY_VE = (
    (re.compile(r"^\d+ tài khoản khác nhau cùng đăng"), "chiến dịch rải"),
    (re.compile(r"^rải \d+ tin trong"), "dồn tin"),
    (re.compile(r"^gửi lại cùng một nội dung"), "lặp nội dung"),
    (re.compile(r"^đồng phạm trong chiến dịch"), "chiến dịch rải"),
    # "tin nhắn chuyển tiếp từ kênh ABC" - tên nguồn không nằm sau dấu hai
    # chấm nên _CHI_TIET_RE không cắt được, phải quy về tay.
    (re.compile(r"^tin nhắn chuyển tiếp"), "tin nhắn chuyển tiếp"),
    (re.compile(r"^số điện thoại lạ"), "số điện thoại lạ"),
    (re.compile(r"^link lạ"), "link lạ"),
)

# Tên luật -> công tắc tắt được. Luật nào không có ở đây thì bot chỉ đếm và
# báo, không tự đụng vào: từ khoá tự đặt phải do bạn tự bỏ, còn "ví crypto"
# hay "QR chuyển khoản" thì không có lý do gì để tắt.
CONG_TAC_CUA_LUAT = {
    "tin nhắn chuyển tiếp": "block_forwards",
    "link lạ": "block_links",
    "nhắc @ không được phép": "block_mentions",
    "số điện thoại lạ": "block_phones",
    "tên giả mạo ban quản trị": "block_fake_admin",
    "chiến dịch rải": "chong_rai",
    "dồn tin": "chong_rai",
    "lặp nội dung": "chong_rai",
}


def ten_luat(ly_do: str) -> list[str]:
    """Rút tên các luật từ chuỗi lý do đã ghi trong database.

    "link lạ: abc.com; nhắc @ không được phép: @x"  ->  ["link lạ", "nhắc @..."]
    """
    ra: list[str] = []
    for phan in ly_do.split(";"):
        ten = _CHI_TIET_RE.sub("", phan.strip()).strip()
        if not ten:
            continue
        for mau, chung in _QUY_VE:
            if mau.match(ten):
                ten = chung
                break
        if ten not in ra:
            ra.append(ten)
    return ra
