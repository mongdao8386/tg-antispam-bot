"""Kiểm thử bộ dò spam - chạy: python -m pytest tests/ hoặc python tests/test_detector.py

Danh sách HAM không phải nghĩ ra cho có: phần lớn là những tin THẬT đã bị bot
ban oan trong quá trình dùng, chép lại nguyên văn. Mỗi mục là một lần bực mình
đã phải đi gỡ ban bằng tay, nên chúng đáng được giữ ở đây để không tái diễn.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot.config import Config
from antispam_bot.detector import MessageFacts, analyse

CFG = Config(
    token="x",
    whitelist_domains={"t.me", "telegram.org", "youtube.com", "github.com", "google.com"},
)


# Đúng cấu hình thực tế đang chạy: chặn số điện thoại đang TẮT.
CFG_TAT_SDT = Config(
    token="x",
    whitelist_domains=CFG.whitelist_domains,
    block_phones=False,
    block_mentions=False,
)


def xet(text: str, **kw):
    return analyse(MessageFacts(text=text, **kw), CFG)


def is_spam(text: str, **kw) -> bool:
    return xet(text, **kw).is_spam


# --- Phải bị chặn ---------------------------------------------------------

SPAM = [
    "Tuyển CTV online làm việc tại nhà, thu nhập 500k/ngày, không cần kinh nghiệm. Inbox zalo 0912345678",
    "🎰🎰 NHÀ CÁI UY TÍN SỐ 1 CHÂU Á 🎰 Đăng ký nhận 100k, hoàn trả cao nhất thị trường, rút tiền 24/7 👉 https://kubet88.xyz",
    "Cơ hội đầu tư sinh lời, cam kết lợi nhuận 30%/tháng, x2 tài khoản sau 1 tuần. Liên hệ ngay https://bit.ly/abc123",
    "VAY TIỀN NHANH chỉ cần CMND, giải ngân trong ngày, hỗ trợ nợ xấu. Alo là có tiền 0987654321",
    "Free airdrop! Claim your crypto giveaway now: send 0.1 ETH to 0x9f8e7d6c5b4a39281706f5e4d3c2b1a098765432 and receive double",
    "Join our VIP signal channel for guaranteed profit https://t.me/+AbCdEfGhIjKlMn",
    "Sàn giao dịch uy tín, chốt lãi liên tục, ib để được tư vấn",
    "k i e m t i e n o n l i n e mỗi ngày 1 triệu, số lượng có hạn",
    "Tài khoản của bạn bị khoá, xác minh tài khoản ngay tại http://tele-verify.top/login",
    "Làm bằng giả uy tín, bảo mật tuyệt đối, giao hàng toàn quốc. Contact: hotline 0333444555",
    # Sáu cụm dưới đây từng KHÔNG BAO GIỜ khớp: normalize() đổi 1->i, 0->o,
    # 3->e trong tin nhắn nhưng danh sách từ khoá thì không, nên hai bên lệch
    # nhau. Giữ lại làm chốt chặn cho lỗi đó.
    "Bỏ túi mỗi ngày 500k, việc nhẹ nhàng ai cũng làm được, add zalo mình nhé",
    "Sàn top 1 châu Á, uy tín số 1, x3 tài khoản trong 1 tuần, đăng ký nhận 100k ngay",
]

# --- Phải được cho qua ----------------------------------------------------

HAM = [
    "Chào cả nhà, mình mới tham gia nhóm 👋",
    "Bạn nào biết cách fix lỗi này không? Mình đọc doc ở https://github.com/python-telegram-bot/python-telegram-bot mà vẫn chưa hiểu",
    "Hôm nay trời đẹp quá, đi cà phê không mọi người?",
    "Video hay lắm nè https://youtube.com/watch?v=dQw4w9WgXcQ",
    "Mình vừa đầu tư một con chuột mới cho cái bàn phím cơ, giá 300k thôi mà xịn phết 😄",
    "Ai rảnh check giúp mình cái PR này với, cảm ơn nhiều!",
    "Nhóm mình có ai ở Hà Nội không nhỉ, tổ chức offline đi",
    "Lừa đảo nhiều quá, mọi người cẩn thận với mấy tin nhắn kiểu đó nhé",
    # --- Những tin THẬT đã bị ban oan, chép nguyên văn ---
    # Cộng dồn điểm: "uy tín" là từ mồi chài (+1) cộng tiền án.
    "Shop này uy tín lắm, mình mua mấy lần rồi",
    # Từng bị bắt vì "hứa hẹn thu nhập bằng con số" + emoji.
    "Lương tháng này được 15 triệu, mừng quá mọi người ơi 🎉🎉🎉🎉🎉🎉",
    # Từng bị bắt vì viết hoa toàn bộ.
    "CHÚC MỪNG SINH NHẬT BẠN NHÉ, CHÚC BẠN LUÔN VUI VẺ VÀ THÀNH CÔNG",
    # Bàn chuyện cờ bạc chứ không quảng cáo - "cá cược" đơn lẻ đã bỏ khỏi danh sách.
    "Trận này mà cá cược thì chắc thua sạch, thôi xem cho vui",
    # "nổ hũ" bỏ dấu thành "no hu", đụng "nó hư".
    "Cái máy giặt nhà mình nó hư rồi, ai biết thợ nào sửa không",
    # "báo lãi" bỏ dấu thành "bao lai", đụng "bao lãi" của quảng cáo.
    "Quý này công ty báo lãi khá tốt, cổ phiếu chắc lên",
    # Người mới vào nhóm hỏi han - trước đây ngưỡng thành viên mới thấp nên dễ dính.
    "Mình mới vào nhóm, cho mình hỏi ở đây có ai làm forex không ạ?",
]


# --- Nội dung giải ra từ mã QR -------------------------------------------
# (không cần OpenCV: ta nạp thẳng payload để kiểm tra phần ra quyết định)

QR_SPAM = [
    # VietQR / EMVCo - QR chuyển khoản ngân hàng
    ("00020101021238570010A00000072701270006970418011234567890123450208QRIBFTTA5303704"
     "5802VN62130809thanh toan6304ABCD", "QR chuyển khoản ngân hàng"),
    ("https://kubet-vip.top/dangky?ref=99", "QR dẫn tới link lạ"),
    ("bitcoin:bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh?amount=0.5", "QR ví crypto"),
    ("ethereum:0x9f8e7d6c5b4a39281706f5e4d3c2b1a098765432", "QR ví crypto"),
    ("https://t.me/+AbCdEfGhIjKlMn", "QR mời vào kênh riêng"),
    ("tg://resolve?domain=scamchannel", "QR mở kênh Telegram"),
    ("Tuyen CTV online thu nhap 500k/ngay, lien he zalo 0912345678", "QR chứa nội dung lừa đảo"),
]

QR_HAM = [
    ("https://github.com/python-telegram-bot/python-telegram-bot", "QR link whitelist"),
    ("https://youtube.com/watch?v=abc", "QR link whitelist"),
    ("WIFI:S:PhongHop;T:WPA;P:matkhau123;;", "QR wifi phòng họp"),
]


# --- Công tắc TẮT thì phải thật sự tắt ---------------------------------
# Lỗi cũ: khi BLOCK_PHONES=false, bot vẫn cộng 2 điểm cho "số điện thoại liên
# hệ". Tắt mà vẫn phạt - và đây là một trong những nguồn ban oan đo được.
# Luật "nhắc tới từ 3 tài khoản trở lên" cũng vậy: tag ba người bạn vào một
# tin là chuyện thường ngày, nhưng vẫn bị cộng 2 điểm.

TAT_CONG_TAC = [
    "Ai cần thì gọi mình nhé 0912345678 🎉🎉🎉🎉🎉🎉🎉🎉 cảm ơn mọi người nhiều 🥰",
    "@nam_nguyen @hoa_tran @minh_le mai họp lúc 9h nhé mọi người",
    "Số mình là 0987654321, cứ alo nhé, hoặc +84912345678 cũng được",
]


# --- Luật dứt khoát: mỗi luật phải TỰ MÌNH đủ, và chỉ mình nó ------------

def _ket_qua_luat() -> list[tuple[str, bool]]:
    # Không QR đọc được thì không có luật QR nào chạy, kể cả với thành viên mới.
    qr_moi = analyse(MessageFacts(has_qr=True, qr_payloads=[], is_new_member=True), CFG)
    qr_sach = analyse(
        MessageFacts(has_qr=True, qr_payloads=["https://github.com/abc"]), CFG
    )
    lich_su = xet("https://github.com/foo/bar rất hay", prior_offences=5, is_new_member=True)
    return [
        ("forward bị chặn", is_spam("chào mọi người", is_forward=True, forward_label="kênh khác")),
        ("forward kèm ảnh sạch được tha", not is_spam("", is_forward=True, has_media=True)),
        ("gửi từ kênh bị chặn", is_spam("hi", from_channel=True)),
        ("link lạ bị chặn", is_spam("xem tại https://random-site.online/promo")),
        ("link whitelist không bị chặn", not is_spam("https://github.com/foo/bar rất hay")),
        ("khung QR không đọc được thì bỏ qua", not qr_moi.is_spam),
        ("QR dẫn tới link whitelist được tha", not qr_sach.is_spam),
        ("tên giả mạo admin bị chặn", is_spam("chào bạn", sender_name="Trợ Lý Nhóm")),
        ("tin kèm nút bấm bị chặn", is_spam("bấm vào đây", has_buttons=True)),
        ("story bị chặn", is_spam("", has_story=True)),
        ("ký tự vô hình bị chặn", is_spam("lu​ừa đ​ảo gì đó")),
        # Cốt lõi của lần đổi này: lý lịch người gửi không còn kết tội được ai.
        ("tiền án + thành viên mới KHÔNG tự kết tội", not lich_su.is_spam),
        # Mỗi lần chặn chỉ nêu đúng lý do đã khớp, không kèm dấu hiệu phụ.
        ("lý do luôn đọc hiểu được", all(
            "(+" not in r for r in xet("Tuyển CTV online, add zalo nhé").reasons
        )),
    ]


def run() -> int:
    loi = 0

    def bang(ten: str, muc, lay, mong_spam: bool) -> None:
        nonlocal loi
        print(f"\n== {ten} ==")
        for phan_tu in muc:
            v, nhan = lay(phan_tu)
            ok = v.is_spam == mong_spam
            loi += not ok
            dau = "OK " if ok else ("MISS" if mong_spam else "BAN OAN")
            print(f"  [{dau}] {nhan[:66]}")
            print(f"         {v.summary()[:100]}")

    bang("Phải chặn", SPAM, lambda t: (xet(t), t), True)
    bang("Phải cho qua", HAM, lambda t: (xet(t), t), False)
    bang("Mã QR: phải chặn", QR_SPAM,
         lambda x: (analyse(MessageFacts(has_qr=True, qr_payloads=[x[0]]), CFG), x[1]), True)
    bang("Mã QR: phải cho qua", QR_HAM,
         lambda x: (analyse(MessageFacts(has_qr=True, qr_payloads=[x[0]]), CFG), x[1]), False)

    print("\n== Công tắc tắt thì phải thật sự tắt ==")
    for text in TAT_CONG_TAC:
        v = analyse(MessageFacts(text=text), CFG_TAT_SDT)
        ok = not v.is_spam
        loi += not ok
        print(f"  [{'OK ' if ok else 'BAN OAN'}] {text[:66]}")
        print(f"         {v.summary()[:100]}")

    print("\n== Luật dứt khoát ==")
    for ten, ok in _ket_qua_luat():
        loi += not ok
        print(f"  [{'OK ' if ok else 'FAIL'}] {ten}")

    print(f"\n{'TẤT CẢ ĐỀU ĐẠT' if loi == 0 else f'{loi} trường hợp SAI'}")
    return loi


# pytest hooks
def test_spam_detected():
    for text in SPAM:
        assert is_spam(text), f"bỏ lọt: {text}"


def test_ham_allowed():
    for text in HAM:
        v = xet(text)
        assert not v.is_spam, f"ban oan: {text}\n  lý do: {v.summary()}"


def test_qr_spam_detected():
    for payload, label in QR_SPAM:
        v = analyse(MessageFacts(has_qr=True, qr_payloads=[payload]), CFG)
        assert v.is_spam, f"bỏ lọt QR: {label}"


def test_qr_ham_allowed():
    for payload, label in QR_HAM:
        v = analyse(MessageFacts(has_qr=True, qr_payloads=[payload]), CFG)
        assert not v.is_spam, f"ban oan QR: {label} ({v.summary()})"


def test_cong_tac_tat_la_that_su_tat():
    for text in TAT_CONG_TAC:
        v = analyse(MessageFacts(text=text), CFG_TAT_SDT)
        assert not v.is_spam, f"tắt công tắc mà vẫn phạt: {text}\n  lý do: {v.summary()}"


def test_luat_dut_khoat():
    for ten, ok in _ket_qua_luat():
        assert ok, ten


def test_ly_lich_khong_ket_toi():
    """Thành viên mới, không username, đã vi phạm 5 lần - tin vẫn sạch thì vẫn sạch."""
    v = xet(
        "mọi người cho mình hỏi cái này với",
        is_new_member=True, has_username=False, prior_offences=5,
    )
    assert not v.is_spam, v.summary()


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
