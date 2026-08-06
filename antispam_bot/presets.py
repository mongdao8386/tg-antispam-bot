"""Bộ từ cấm dựng sẵn, nạp bằng lệnh /preset.

Lưu ý về cách so khớp: bot so khớp trên chuỗi ĐÃ chuẩn hoá (bỏ dấu, chữ thường,
gộp khoảng trắng - xem normalize.py). Nên chỉ cần viết "lừa đảo" là đã bắt được
"LỪA ĐẢO", "Lua Dao", "lừa   đảo". Không cần liệt kê biến thể dấu.

Cái KHÔNG tự bắt được: nói lái ("đảo lừa"), chèn ký tự lạ giữa chữ, viết tắt.
Những biến thể đó phải liệt kê tay - xem các mục dưới.

Từ trong danh sách này gây BAN NGAY, không cộng điểm. Vì vậy ưu tiên cụm từ
nhiều chữ; từ đơn lẻ quá phổ thông sẽ bắt oan người vô tội.
"""

from __future__ import annotations

# Quảng cáo cờ bạc - kẻ spam chủ động rao, gần như không có ngữ cảnh lành tính.
COBAC = [
    "nhà cái uy tín", "link vào nhà cái", "game bài đổi thưởng",
    "tài xỉu online", "soi cầu miễn phí", "lô đề online",
    "đăng ký nhận 100k", "hoàn trả cao nhất", "chốt kèo",
    "nổ hũ đổi thưởng", "cá cược bóng đá",
]

# Dụ đầu tư / tiền ảo - cam kết lợi nhuận là dấu hiệu gần như chắc chắn.
DAUTU = [
    "cam kết lợi nhuận", "lợi nhuận khủng", "bao lãi", "không lo vốn",
    "x2 tài khoản", "x3 tài khoản", "chốt lãi liên tục",
    "tín hiệu giao dịch vip", "sàn giao dịch uy tín",
    "free airdrop", "claim airdrop", "crypto giveaway",
    "double your money", "guaranteed profit",
]

# Tuyển dụng ma - "việc nhẹ lương cao" là mồi nhử phổ biến nhất.
TUYENDUNG = [
    "việc nhẹ lương cao", "tuyển ctv", "tuyển cộng tác viên",
    "thu nhập không giới hạn", "không cần kinh nghiệm lương",
    "làm việc tại nhà lương", "lương 20 triệu", "lương 30 triệu",
]

# Tín dụng đen.
VAYNO = [
    "vay tiền nhanh", "vay nóng", "giải ngân trong ngày",
    "chỉ cần cmnd", "chỉ cần cccd", "hỗ trợ nợ xấu",
    "vay không thế chấp", "alo là có tiền",
]

# Giấy tờ giả, mua bán dữ liệu, hàng cấm.
HANGCAM = [
    "làm bằng giả", "bằng cấp giả", "làm giấy tờ giả",
    "mua bán cccd", "mua bán data", "hack facebook",
    "mua bán tài khoản ngân hàng", "thuê tài khoản ngân hàng",
    "unlock icloud giá rẻ",
]

# Chiếm đoạt tài khoản - dụ nạn nhân đưa OTP.
CHIEMDOAT = [
    "cung cấp mã otp", "gửi mã otp", "đọc mã otp",
    "tài khoản của bạn bị khoá", "xác minh tài khoản ngay",
    "nhập thông tin thẻ",
]

# Nội dung người lớn - rao bán dịch vụ, không phải nói chuyện thông thường.
NGUOILON = [
    "gái gọi", "phim sex", "clip nóng",
    "sugar baby tuyển", "sugar daddy tuyển", "bán clip nóng",
]


# ---------------------------------------------------------------------------
# CẢNH BÁO - đọc kỹ trước khi nạp bộ này.
#
# Đây là từ NGƯỜI TỐ CÁO dùng, không phải từ kẻ lừa đảo dùng. Kẻ lừa đảo không
# bao giờ tự viết "đây là lừa đảo". Nạp bộ này nghĩa là ban những người đang
# cảnh báo người khác - không phải chặn spam.
#
# Hai hệ quả thực tế:
#   1. Bắt oan rất nhiều. "Tin đó là lừa đảo đấy, đừng chuyển tiền" -> ban.
#      "Phim này nói về trò bịp" -> ban. Người đang giúp nhóm sẽ biến mất.
#   2. Thành viên thật sẽ nhận ra và rời nhóm.
#
# Chỉ nạp nếu bạn hiểu rõ và chấp nhận điều đó.
# ---------------------------------------------------------------------------
TOCAO = [
    "lừa đảo", "lừa tiền", "lừa gạt", "lùa gà", "bịp bợm",
    "ôm tiền bỏ chạy", "quỵt tiền", "chạy làng",
    "scam", "ponzi", "bịp", "lùa đảo", "lùa gà", "lùa tiền", "lùa người", "đào lửa", "scammer"
    # Nói lái - chuẩn hoá không tự bắt được nên phải liệt kê tay.
    # (Các biến thể như "l ừ a đ ả o", "lu@ d@o", "lùađảo" KHÔNG cần liệt kê:
    #  normalize/squeeze đã tự quy về "lừa đảo".)
]


PRESETS: dict[str, tuple[str, list[str]]] = {
    "cobac":      ("Quảng cáo cờ bạc", COBAC),
    "dautu":      ("Dụ đầu tư / tiền ảo", DAUTU),
    "tuyendung":  ("Tuyển dụng ma", TUYENDUNG),
    "vayno":      ("Tín dụng đen", VAYNO),
    "hangcam":    ("Giấy tờ giả / hàng cấm", HANGCAM),
    "chiemdoat":  ("Chiếm đoạt tài khoản (OTP)", CHIEMDOAT),
    "nguoilon":   ("Nội dung người lớn", NGUOILON),
    "tocao":      ("⚠️ Từ tố cáo lừa đảo - ban người cảnh báo", TOCAO),
}

DEFAULT_SET = ("cobac", "dautu", "tuyendung", "vayno", "hangcam", "chiemdoat", "nguoilon", "tocao")

# Bắt lỗi gõ sai ngay lúc nạp module, thay vì âm thầm nạp thiếu một bộ.
_missing = [n for n in DEFAULT_SET if n not in PRESETS]
if _missing:
    raise RuntimeError(f"DEFAULT_SET có tên không tồn tại trong PRESETS: {_missing}")


def all_phrases(names: list[str]) -> list[str]:
    """Gộp các bộ đã chọn, bỏ trùng, giữ thứ tự.

    Tên không tồn tại sẽ báo lỗi thay vì bị bỏ qua - bỏ qua âm thầm từng
    khiến /preset all nạp thiếu cả một bộ mà không ai biết.
    """
    unknown = [n for n in names if n not in PRESETS]
    if unknown:
        raise KeyError(f"Không có bộ: {unknown}")
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        for phrase in PRESETS[name][1]:
            if phrase not in seen:
                seen.add(phrase)
                out.append(phrase)
    return out
