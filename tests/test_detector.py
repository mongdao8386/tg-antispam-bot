"""Kiểm thử bộ dò spam - chạy: python -m pytest tests/ hoặc python tests/test_detector.py"""

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


def score(text: str, **kw) -> int:
    return analyse(MessageFacts(text=text, **kw), CFG).score


def is_spam(text: str, **kw) -> bool:
    return analyse(MessageFacts(text=text, **kw), CFG).is_spam


# --- Phải bị chặn ---------------------------------------------------------

SPAM = [
    "Tuyển CTV online làm việc tại nhà, thu nhập 500k/ngày, không cần kinh nghiệm. Inbox zalo 0912345678",
    "🎰🎰 NHÀ CÁI UY TÍN SỐ 1 CHÂU Á 🎰 Đăng ký nhận 100k, hoàn trả cao nhất thị trường, rút tiền 24/7 👉 https://kubet88.xyz",
    "Cơ hội đầu tư sinh lời, cam kết lợi nhuận 30%/tháng, x2 tài khoản sau 1 tuần. Liên hệ ngay https://bit.ly/abc123",
    "VAY TIỀN NHANH chỉ cần CMND, giải ngân trong ngày, hỗ trợ nợ xấu. Alo là có tiền 0987654321",
    "Free airdrop! Claim your crypto giveaway now: send 0.1 ETH to 0x9f8e7d6c5b4a39281706f5e4d3c2b1a098765432 and receive double",
    "Join our VIP signal channel for guaranteed profit https://t.me/+AbCdEfGhIjKlMn",
    "l.ừ.a đ.ả.o? Không nhé! Sàn giao dịch uy tín, bao lãi, chốt lãi liên tục, ib để được tư vấn",
    "k i e m t i e n o n l i n e mỗi ngày 1 triệu, nhanh tay số lượng có hạn",
    "Tài khoản của bạn bị khoá, xác minh tài khoản ngay tại http://tele-verify.top/login",
    "Làm bằng giả uy tín, bảo mật tuyệt đối, giao hàng toàn quốc. Contact: hotline 0333444555",
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
]


# --- Nội dung giải ra từ mã QR -------------------------------------------
# (không cần OpenCV: ta nạp thẳng payload để kiểm tra phần chấm điểm)

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


def run() -> int:
    failures = 0

    print("== Phải chặn ==")
    for text in SPAM:
        v = analyse(MessageFacts(text=text), CFG)
        ok = v.is_spam
        failures += not ok
        print(f"  [{'OK ' if ok else 'MISS'}] {v.score}/{v.threshold}  {text[:60]}...")
        if not ok:
            print(f"         lý do: {v.reasons}")

    print("\n== Phải cho qua ==")
    for text in HAM:
        v = analyse(MessageFacts(text=text), CFG)
        ok = not v.is_spam
        failures += not ok
        print(f"  [{'OK ' if ok else 'FALSE POSITIVE'}] {v.score}/{v.threshold}  {text[:60]}...")
        if not ok:
            print(f"         lý do: {v.reasons}")

    print("\n== Mã QR: phải chặn ==")
    for payload, label in QR_SPAM:
        v = analyse(MessageFacts(has_qr=True, qr_payloads=[payload]), CFG)
        ok = v.is_spam
        failures += not ok
        print(f"  [{'OK ' if ok else 'MISS'}] {v.score}/{v.threshold}  {label}")
        if not ok:
            print(f"         lý do: {v.reasons}")

    print("\n== Mã QR: phải cho qua (thành viên cũ) ==")
    for payload, label in QR_HAM:
        v = analyse(MessageFacts(has_qr=True, qr_payloads=[payload]), CFG)
        ok = not v.is_spam
        failures += not ok
        print(f"  [{'OK ' if ok else 'FALSE POSITIVE'}] {v.score}/{v.threshold}  {label}")
        if not ok:
            print(f"         lý do: {v.reasons}")

    print("\n== Luật cứng ==")
    qr_new = analyse(MessageFacts(has_qr=True, qr_payloads=[], is_new_member=True), CFG)
    qr_old = analyse(MessageFacts(has_qr=True, qr_payloads=[], is_new_member=False), CFG)
    checks = [
        ("forward bị chặn", is_spam("chào mọi người", is_forward=True, forward_label="kênh khác")),
        ("gửi từ kênh bị chặn", is_spam("hi", from_channel=True)),
        ("link lạ bị chặn", is_spam("xem tại https://random-site.online/promo")),
        ("link whitelist không bị chặn", not is_spam("https://github.com/foo/bar rất hay")),
        ("thành viên mới ngưỡng thấp hơn", score("nhanh tay đăng ký ngay", is_new_member=True) > 0),
        ("thành viên mới gửi QR bị chặn", qr_new.is_spam),
        ("thành viên cũ gửi QR vô hại không bị chặn", not qr_old.is_spam),
    ]
    for name, ok in checks:
        failures += not ok
        print(f"  [{'OK ' if ok else 'FAIL'}] {name}")

    print(f"\n{'TẤT CẢ ĐỀU ĐẠT' if failures == 0 else f'{failures} trường hợp SAI'}")
    return failures


# pytest hooks
def test_spam_detected():
    for text in SPAM:
        assert is_spam(text), f"bỏ lọt: {text}"


def test_ham_allowed():
    for text in HAM:
        assert not is_spam(text), f"chặn oan: {text}"


def test_qr_spam_detected():
    for payload, label in QR_SPAM:
        v = analyse(MessageFacts(has_qr=True, qr_payloads=[payload]), CFG)
        assert v.is_spam, f"bỏ lọt QR: {label} ({v.score}/{v.threshold})"


def test_qr_ham_allowed():
    for payload, label in QR_HAM:
        v = analyse(MessageFacts(has_qr=True, qr_payloads=[payload]), CFG)
        assert not v.is_spam, f"chặn oan QR: {label} ({v.reasons})"


def test_hard_rules():
    assert is_spam("chào mọi người", is_forward=True)
    assert is_spam("hi", from_channel=True)
    assert is_spam("xem tại https://random-site.online/promo")
    assert not is_spam("https://github.com/foo/bar rất hay")


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
