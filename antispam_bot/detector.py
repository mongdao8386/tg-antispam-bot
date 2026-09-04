"""Bộ dò spam theo luật dứt khoát.

Mỗi luật ở đây tự chịu trách nhiệm: khớp là xử lý, không khớp thì thôi. Không
cộng dồn, không ngưỡng, không "gần đủ điểm".

VÌ SAO BỎ CHẤM ĐIỂM
Đo trên 1.761 lượt ban thật của chính bot này:

    1.508 lượt (99,4%)  có sẵn MỘT luật đủ mạnh, cộng dồn không thay đổi gì
       10 lượt ( 0,6%)  thật sự do cộng dồn quyết định

Mười lượt đó gần như đều là ban oan: "số điện thoại + nhiều emoji", "uy tín +
đã vi phạm 1 lần trước đó". Lớp điểm số không cứu được ca nào mà chỉ thêm oan
sai, nên bỏ hẳn.

CÁI GIÁ PHẢI TRẢ
Mỗi luật giờ phải tự đứng vững một mình. Luật nào không đủ chắc để một mình
kết tội thì không có lý do tồn tại - đã xoá hết ở lần này: lạm dụng emoji,
viết hoa toàn bộ, nhắc con số tiền, "có vẻ như là mã QR", thành viên mới,
không có username, đã vi phạm trước đó. Chúng chỉ từng có ý nghĩa khi được
cộng vào một tổng, mà cái tổng đó vừa chứng minh là vô dụng.

Đổi lại, mỗi lần ban giờ chỉ ra được đúng MỘT lý do đọc hiểu ngay, thay vì
một danh sách bốn dấu hiệu mơ hồ cộng lại thành 5/5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ngucanh
from .config import Config
from .normalize import INVISIBLE_RE, collapse_repeats, normalize, squeeze

# --------------------------------------------------------------------------
# Từ khoá (viết ở dạng đã bỏ dấu, chữ thường - xem normalize.py)
#
# Chỉ còn MỘT danh sách. Trước đây có ba mức mạnh/vừa/yếu, nhưng hai mức dưới
# chỉ tồn tại để cộng điểm - mà cộng điểm thì đã bỏ. Luật ở đây là: cụm nào
# đủ chắc để một mình kết tội thì giữ, không thì xoá.
#
# Đã xoá vì quá chung, người bình thường vẫn nói: "làm giàu", "cơ hội đầu tư",
# "forex", "tăng ngay", "nhận ngay", "trúng thưởng", "mã khuyến mãi", "ib
# riêng", "nhắn tin riêng", "uy tín", "cam kết", "nhanh tay", "liên hệ ngay",
# "lãi suất 0" và toàn bộ nhóm "mồi chài" cũ.
#
# Lưu ý về dấu: chuỗi so khớp đã bỏ dấu nên "nổ hũ" và "nó hư" ra cùng một
# dạng. Những cụm ngắn dễ đụng như vậy đều đã được viết dài ra cho an toàn.
# --------------------------------------------------------------------------
_CHAN_GOC = {
    # Việc nhẹ lương cao / tuyển CTV
    "viec nhe luong cao", "tuyen ctv", "tuyen cong tac vien", "ctv online",
    "lam viec tai nha luong", "khong can kinh nghiem luong", "thu nhap khong gioi han",
    "kiem tien online", "kiem tien tai nha", "thu nhap thu dong",
    "work from home earn", "make money fast", "passive income", "financial freedom",
    # Cờ bạc  ("nổ hũ", "cá cược" viết dài ra vì bỏ dấu là đụng chữ thường)
    "nha cai uy tin", "tai xiu", "soi cau", "lo de", "keo thom", "chot keo",
    "game no hu", "no hu doi thuong", "link no hu",
    "ca cuoc bong da", "trang ca cuoc", "nha cai ca cuoc", "web ca cuoc",
    "dang ky nhan 100k", "hoan tra cao nhat", "game bai doi thuong",
    "link vao nha cai", "code tan thu", "nap rut",
    # Đầu tư / crypto lừa đảo
    "cam ket loi nhuan", "loi nhuan khung", "sieu loi nhuan", "cam ket bao lai",
    "x2 tai khoan", "x3 tai khoan", "san giao dich uy tin", "tin hieu giao dich",
    "chot lai lien tuc", "khong lo von", "dau tu sinh loi", "von it loi nhieu",
    "binary option", "san quoc te", "uy tin so 1", "top 1 chau a",
    "guaranteed profit", "guaranteed returns", "double your money",
    "free airdrop", "claim airdrop", "elon musk giveaway", "crypto giveaway",
    "pump signal", "insider signal", "vip signal", "trading bot profit",
    "investment opportunity", "join our vip", "join my channel",
    "recover your funds", "recovery expert", "hack recovery",
    # Hứa hẹn thu nhập bằng con số cụ thể
    "bo tui moi ngay", "moi ngay 500k", "moi ngay 1 trieu", "300k ngay", "500k ngay",
    "hoa hong cao", "rut tien nhanh", "qua tang khung",
    # Vay nặng lãi / tín dụng đen
    "vay tien nhanh", "vay nong", "giai ngan trong ngay", "chi can cmnd",
    "chi can cccd", "ho tro no xau", "vay khong the chap", "alo la co tien",
    # Giấy tờ giả / hàng cấm
    "lam bang gia", "bang cap gia", "lam giay to gia", "mua ban cccd",
    "mua ban data", "hack facebook", "hack tai khoan", "unlock icloud gia re",
    "sim rac gia re", "mua ban tai khoan ngan hang", "thue tai khoan ngan hang",
    # Người lớn
    "gai goi", "check hang gai", "phim sex", "clip nong", "sugar baby tuyen",
    # Chiếm đoạt tài khoản
    "cung cap ma otp", "gui ma otp", "doc ma otp", "tai khoan cua ban bi khoa",
    "xac minh tai khoan ngay", "nhap thong tin the",
    # Kéo sang kênh riêng để lừa
    "inbox de biet them", "ib de duoc tu van", "lien he zalo",
    "add zalo", "ket ban zalo", "dm me for", "text me on whatsapp",
}

# Chuẩn hoá chính danh sách bằng đúng hàm dùng cho tin nhắn.
#
# Bắt buộc, không phải cho đẹp: normalize() đổi leetspeak "1"->"i", "0"->"o",
# "3"->"e" trong tin nhắn. Danh sách viết tay thì không qua bước đó, nên
# "500k ngay" trong tin đã thành "sook ngay" mà từ khoá vẫn là "500k ngay" -
# sáu cụm có chữ số ("500k ngay", "dang ky nhan 100k", "x3 tai khoan",
# "top 1 chau a", "moi ngay 1 trieu", "uy tin so 1") chưa từng khớp được lần
# nào. Cho cả hai bên đi qua cùng một hàm là hết lệch.
CHAN = {normalize(k) for k in _CHAN_GOC}

# Dạng dồn hết khoảng trắng, để bắt kiểu "k i e m t i e n o n l i n e".
# Tính sẵn một lần lúc nạp module: nhánh này chạy cho MỌI tin sạch, mà
# squeeze() gọi normalize() bên trong - tính lại 111 lần mỗi tin thì riêng nó
# đã ngốn hơn 1 ms. Chỉ giữ cụm đủ dài để không khớp nhầm khi nối chữ giữa
# các từ bình thường.
SQUEEZED = {squeeze(k): k for k in CHAN if len(squeeze(k)) >= 12}

# Dạng đã gộp mọi chữ lặp, để bắt kiểu "nhàa cáii uy tínn", "gaii gooi".
# Chỉ giữ cụm còn đủ dài sau khi gộp - cụm quá ngắn dễ khớp nhầm. Sáu ký tự
# là đủ an toàn vì vế kia so theo RANH GIỚI TỪ, không phải chuỗi con.
GOP_LAP = {
    nen: k for k in CHAN
    if len(nen := collapse_repeats(k)) >= 6
}

# --------------------------------------------------------------------------
# Regex
# --------------------------------------------------------------------------

URL_RE = re.compile(
    r"""(?xi)
    \b
    (?:https?://|www\.)?
    (?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+
    (?:com|net|org|io|co|xyz|top|icu|click|link|work|buzz|cfd|rest|monster|
       shop|site|online|live|vip|win|bet|casino|app|dev|me|tv|info|biz|ru|cn|
       vn|us|uk|asia|pro|store|fun|life|world|space|website|host|art|club)
    \b (?:/[^\s]*)?
    """
)

# Dạng né bộ lọc: "abc (dot) com", "abc [.] com", "abc . com"
OBFUSCATED_URL_RE = re.compile(
    r"(?i)\b[a-z0-9][a-z0-9-]{1,61}\s*(?:\(|\[|\{)?\s*(?:dot|\.|,)\s*(?:\)|\]|\})?\s*"
    r"(?:com|net|org|io|xyz|top|vip|win|club|shop|live|me)\b"
)

INVITE_RE = re.compile(r"(?i)(?:t\.me/\+|t\.me/joinchat/|telegram\.me/\+|telegram\.dog/)")

# @username Telegram: 5-32 ký tự, chữ/số/gạch dưới. Bắt cả khi Telegram không
# tạo entity (ví dụ @ nằm trong caption ảnh hoặc dính dấu câu).
# (?<![\w@/]) tránh khớp phần sau của email hay t.me/@abc.
MENTION_RE = re.compile(r"(?<![\w@/])@([A-Za-z][A-Za-z0-9_]{4,31})\b")

SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "goo.gl", "ow.ly", "rb.gy",
    "shorturl.at", "rebrand.ly", "t.co", "shorte.st", "adf.ly", "bl.ink",
    "s.id", "linktr.ee", "urlz.fr", "v.gd", "tiny.cc", "1link.vn", "vn.link",
}

SUSPICIOUS_TLDS = {
    "xyz", "top", "icu", "click", "link", "work", "buzz", "cfd", "rest",
    "monster", "win", "bet", "casino", "loan", "gq", "tk", "ml", "cf", "ga",
    "fun", "space", "host", "surf", "quest", "sbs", "autos", "bond",
}

CRYPTO_RE = re.compile(
    r"(?:\b(?:bc1|[13])[a-hj-np-z0-9]{25,62}\b)"      # BTC
    r"|(?:\b0x[a-fA-F0-9]{40}\b)"                      # ETH/BSC
    r"|(?:\bT[1-9A-HJ-NP-Za-km-z]{33}\b)"              # TRON
)

# Số điện thoại: bắt cả số trong nước lẫn số quốc tế (+84, +1, +44, +86...).
# Kẻ spam đổi sang ghi +84 hoặc số nước ngoài để né luật chỉ bắt số bắt đầu
# bằng 0. Hai nhánh:
#   1. Số VN viết kiểu nội địa: 0 + đầu số di động + 8 chữ số
#   2. Bất kỳ số nào có dấu + đứng đầu: mã quốc gia 1-3 số rồi 6-13 chữ số
PHONE_RE = re.compile(
    r"(?<![\d+])(?:0(?:3|5|7|8|9)\d(?:[\s.\-]?\d){7})(?!\d)"
    r"|\+\d{1,3}[\s.\-]?\d(?:[\s.\-]?\d){5,13}(?!\d)"
)

# Tên tự xưng chức vụ. Người thật hiếm khi đặt tên là "Trợ lý" hay "QTV";
# đây là chiêu giả mạo ban quản trị để lừa thành viên nhắn riêng.
# So khớp trên chuỗi ĐÃ normalize (bỏ dấu, chữ thường) nên viết ở dạng không
# dấu - cùng quy ước với bộ từ khoá phía trên. Nhờ vậy bắt được cả "Trợ Lý",
# "TRO LY", "trợ lý" mà không phải liệt kê từng biến thể.
FAKE_ADMIN_RE = re.compile(
    r"(?:^|\s)(?:"
    r"tro ly|quan ly|quan tri|admin|adm|qtv|ql|tl|hr|ho tro|support|cskh"
    r"|cham soc khach|ke toan|thu ngan|nhan vien|nv|bot|manager|staff"
    r"|team support|cong tac vien|ctv|mod|moderator|ban quan tri"
    r")(?:\s|$)"
)

# Chèn dấu câu giữa từng chữ cái để cắt vụn từ khoá: "l.ừ.a đ.ả.o"
CAT_VUN_RE = re.compile(r"(?:\w[.\-_*|]){4,}\w")

# QR thanh toán chuẩn EMVCo (VietQR, VNPay, MoMo...): chuỗi bắt đầu bằng
# "000201", có mã tiền tệ (5303) và/hoặc mã quốc gia (5802VN).
EMV_QR_RE = re.compile(r"^000201.*(?:5303\d{3}|58\d{2}[A-Z]{2})", re.DOTALL)

# Ví crypto / ứng dụng ví đặt trong QR.
WALLET_URI_RE = re.compile(
    r"(?i)^(?:bitcoin|ethereum|tron|litecoin|ton|solana|monero|bnb|metamask|trust|wc):"
)

# QR chứa lệnh mở app/kênh Telegram.
TG_URI_RE = re.compile(r"(?i)^(?:tg://|telegram://)")


# --------------------------------------------------------------------------


@dataclass
class MessageFacts:
    """Thông tin rút ra từ một tin nhắn Telegram, tách khỏi thư viện telegram."""

    text: str = ""
    entity_urls: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    is_forward: bool = False
    forward_label: str | None = None
    via_bot: bool = False
    from_channel: bool = False
    has_buttons: bool = False
    has_media: bool = False
    is_new_member: bool = False
    has_username: bool = True
    prior_offences: int = 0
    has_qr: bool = False
    qr_payloads: list[str] = field(default_factory=list)
    # Chữ OCR đọc được trong ảnh. CỐ Ý tách khỏi `text`: chỉ dùng để soi từ khoá,
    # không dùng để rút link/@ vì OCR đọc sai một ký tự là ra domain ma.
    ocr_text: str = ""
    # Tin thuần chữ và đang hỏi ("nhóm này có lừa đảo không?"). bot.py chỉ bật
    # cờ này khi không kèm link/ảnh/@, nên không lách được bằng dấu ?.
    is_question: bool = False
    # Tên hiển thị của người gửi, để bắt kiểu giả mạo "Trợ lý", "QTV"...
    sender_name: str = ""
    # Người này có đúng là admin thật của nhóm không (đã xác minh qua API).
    is_real_admin: bool = False
    # Tin chia sẻ story (kể cả story đã hết hạn). Không có nội dung để soi,
    # chỉ dùng để kéo người xem sang tài khoản khác.
    has_story: bool = False


@dataclass
class Verdict:
    """Kết luận cho một tin nhắn: danh sách lý do bị chặn.

    Rỗng nghĩa là sạch. Không rỗng nghĩa là bị xử lý - không có mức lưng chừng.
    """

    reasons: list[str] = field(default_factory=list)

    def chan(self, ly_do: str) -> None:
        """Ghi nhận một luật đã khớp. Mỗi luật ở đây tự nó đủ để kết tội."""
        self.reasons.append(ly_do)

    @property
    def is_spam(self) -> bool:
        return bool(self.reasons)

    def summary(self) -> str:
        return "; ".join(self.reasons) or "sạch"


def _hostname(url: str) -> str:
    url = url.strip().rstrip(".,;:!?)»\"'")
    url = re.sub(r"(?i)^[a-z][a-z0-9+.\-]*://", "", url)
    host = url.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _split_url(url: str) -> tuple[str, str]:
    """Tách URL thành (host, path). Path đã bỏ dấu / đầu-cuối, viết thường."""
    url = url.strip().rstrip(".,;:!?)»\"'")
    url = re.sub(r"(?i)^[a-z][a-z0-9+.\-]*://", "", url)
    head, _, tail = url.partition("/")
    host = head.split("?", 1)[0].split("#", 1)[0].split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    path = tail.split("?", 1)[0].split("#", 1)[0].strip("/").lower()
    return host, path


def _host_matches(host: str, pattern: str) -> bool:
    return host == pattern or host.endswith("." + pattern)


def _url_allowed(url: str, whitelist: set[str]) -> bool:
    """URL có được phép không, xét cả đường dẫn.

    Mục whitelist dạng "t.me"                -> cho phép mọi link t.me/*
    Mục whitelist dạng "t.me/abc"            -> CHỈ cho phép đúng link đó
    Nhờ vậy admin mở một kênh cụ thể mà không mở toàn bộ tên miền.
    """
    host, path = _split_url(url)
    if not host or "." not in host:
        return True  # không phải link thật
    for entry in whitelist:
        e_host, _, e_path = entry.partition("/")
        e_host = e_host.lower()
        e_path = e_path.strip("/").lower()
        if not _host_matches(host, e_host):
            continue
        if not e_path:
            return True  # whitelist cả tên miền
        if path == e_path or path.startswith(e_path + "/"):
            return True
    return False


def _khop_tu_khoa(haystack: str, squeezed: str) -> list[str]:
    """Những cụm trong CHAN xuất hiện trong tin nhắn.

    So khớp theo RANH GIỚI TỪ chứ không phải chuỗi con: đệm khoảng trắng hai
    đầu rồi tìm " cum tu ". normalize() đã biến mọi dấu câu thành khoảng trắng
    nên cách này bắt được cả "…nạp rút!" lẫn "(nạp rút)", mà không khớp nhầm
    vào giữa một từ dài hơn.
    """
    dem = f" {haystack} "
    hits = [k for k in CHAN if f" {k} " in dem]
    if hits:
        return hits
    # Không thấy dạng thường thì thử dạng dồn chữ: "k i e m t i e n o n l i n e".
    hits = [goc for nen, goc in SQUEEZED.items() if nen in squeezed]
    if hits:
        return hits
    # Cuối cùng: dạng đã gộp chữ lặp, bắt kiểu "nhàa cáii uy tínn".
    # Nhân đôi một chữ cái là chiêu né rẻ tiền nhất mà lại hiệu quả nhất -
    # REPEAT_RE trong normalize() chỉ gộp khi lặp từ 3 lần, nên gõ hai lần là
    # lọt sạch. Áp cùng phép gộp cho cả danh sách nên hai vế không lệch nhau.
    gop = f" {collapse_repeats(haystack)} "
    return [goc for nen, goc in GOP_LAP.items() if f" {nen} " in gop]


def analyse(facts: MessageFacts, cfg: Config) -> Verdict:
    v = Verdict()

    text = facts.text or ""
    # Nội dung QR và chữ OCR trong ảnh cũng được soi từ khoá như chữ tin nhắn.
    # Riêng `text` (dùng cho luật link/@) thì giữ nguyên bản gốc.
    scannable = " ".join([text, *facts.qr_payloads, facts.ocr_text]).strip()
    haystack = normalize(scannable)
    squeezed = squeeze(scannable)

    # --- Từ khoá ---
    # Câu hỏi thuần chữ thì bỏ qua hẳn phần từ khoá: hỏi "có nhà cái uy tín
    # không?" không phải là quảng cáo nhà cái. Các luật khác vẫn chạy.
    if haystack and not facts.is_question:
        khop = _khop_tu_khoa(haystack, squeezed)
        if khop:
            # Khớp chuỗi thôi chưa đủ - xét xem người viết đang nhắm vào ai:
            # quảng cáo, hay chỉ kể chuyện / trích tin / đặt câu hỏi. Dùng
            # chung bộ xét ngữ cảnh với danh sách từ cấm tự đặt.
            that_su, _ = ngucanh.loc(scannable, khop)
            if that_su:
                v.chan(f"từ khoá lừa đảo: {', '.join(sorted(that_su)[:3])}")

    # --- Chuyển tiếp ---
    # Chỉ chặn khi công tắc đang bật. Forward kèm ảnh thì tha: ảnh đã được soi
    # QR và đọc chữ ở trên, có gì xấu thì luật khác đã bắt rồi - chia sẻ ảnh là
    # chuyện bình thường, không đáng ban.
    if facts.is_forward and cfg.block_forwards:
        if not cfg.block_forwards_new_only or facts.is_new_member:
            if not (facts.has_media and not facts.has_qr):
                nhan = f" từ {facts.forward_label}" if facts.forward_label else ""
                v.chan(f"tin nhắn chuyển tiếp{nhan}")

    # --- Gửi dưới danh nghĩa kênh ---
    if facts.from_channel and cfg.block_channel_senders:
        v.chan("gửi dưới danh nghĩa kênh/nhóm khác")

    # --- Link ---
    urls = {u for u in (URL_RE.findall(text) + facts.entity_urls) if u}
    hosts = {h for h in (_hostname(u) for u in urls) if h and "." in h}
    # Xét cả đường dẫn: whitelist "t.me/kenh-a" không mở luôn "t.me/kenh-b".
    unknown_urls = {u for u in urls if not _url_allowed(u, cfg.whitelist_domains)}

    if unknown_urls and cfg.block_links and (
        not cfg.block_links_new_only or facts.is_new_member
    ):
        def _short(u: str) -> str:
            host, path = _split_url(u)
            return f"{host}/{path}" if path else host

        preview = ", ".join(sorted({_short(u) for u in unknown_urls})[:3])
        v.chan(f"link lạ: {preview}")

    # Ba luật dưới đây chạy kể cả khi đã tắt chặn link: chúng không nói "có
    # link" mà nói "link này cố tình giấu đích đến".
    if any(h in SHORTENERS for h in hosts):
        v.chan("link rút gọn (giấu đích đến)")
    elif any(h.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS for h in hosts):
        v.chan("tên miền thuộc nhóm rủi ro cao")
    if INVITE_RE.search(text):
        v.chan("link mời vào nhóm/kênh riêng")
    if OBFUSCATED_URL_RE.search(text) and not hosts:
        v.chan("link viết né bộ lọc (dạng 'abc (dot) com')")

    # --- Mã QR trong ảnh ---
    # CỐ Ý không có luật "ảnh này có mã QR". Đã thử và bỏ: bộ dò nhận nhầm hoa
    # văn ảnh đời thường (đĩa cơm, vân vải) rất nhiều, mà một mã QR đọc được
    # dẫn tới trang lành thì chẳng có gì sai. Chỉ chặn theo NỘI DUNG mã.
    for payload in facts.qr_payloads:
        p = payload.strip()
        if EMV_QR_RE.match(p):
            v.chan("QR chuyển khoản / thanh toán ngân hàng")
            continue
        if WALLET_URI_RE.match(p) or CRYPTO_RE.search(p):
            v.chan("QR chứa địa chỉ ví crypto")
            continue
        if INVITE_RE.search(p) or TG_URI_RE.match(p):
            v.chan("QR dẫn tới nhóm/kênh Telegram")
            continue

        qr_urls = {u for u in URL_RE.findall(p) if _hostname(u) and "." in _hostname(u)}
        if not qr_urls and "://" in p and "." in _hostname(p):
            qr_urls = {p}
        unknown_qr = {u for u in qr_urls if not _url_allowed(u, cfg.whitelist_domains)}
        if unknown_qr:
            names = sorted({_hostname(u) for u in unknown_qr})[:2]
            v.chan(f"QR dẫn tới link lạ: {', '.join(names)}")

    # --- Nhắc @username ---
    # Gom cả entity do Telegram nhận diện lẫn @ viết thẳng trong chữ.
    # CỐ Ý không còn luật "nhắc tới từ 3 tài khoản trở lên": tag ba người bạn
    # vào một tin là chuyện thường ngày.
    if cfg.block_mentions:
        handles = {m.strip().lstrip("@").lower() for m in facts.mentions}
        handles |= {m.lower() for m in MENTION_RE.findall(text)}
        la = {h for h in handles if h and h not in cfg.allowed_usernames}
        if la:
            preview = ", ".join("@" + h for h in sorted(la)[:3])
            v.chan(f"nhắc @ không được phép: {preview}")

    # --- Ví crypto ---
    # Quét trên `scannable` (gồm cả chữ đọc từ ảnh và nội dung QR), không chỉ
    # chữ tin nhắn: kẻ spam đã chuyển sang gửi ẢNH CẮT chỉ còn địa chỉ ví.
    if CRYPTO_RE.search(scannable):
        v.chan("địa chỉ ví crypto")

    # CỐ Ý KHÔNG có luật nào bắt số tài khoản / tên ngân hàng / ảnh biên lai.
    #
    # Đã thử và bỏ: mọi cách nhận diện đều bắt oan hàng loạt, vì thành viên
    # trong nhóm đăng ảnh chuyển khoản là chuyện bình thường, mà ảnh đó luôn
    # có đủ tên ngân hàng, số tài khoản và số tiền - không khác gì ảnh spam.
    # Mỗi lần vá cho một mẫu ảnh thì hôm sau lại lọt mẫu khác (biến động số
    # dư, "chuyển tiền thành công", app khác câu chữ khác...).
    #
    # QR mới là thứ đáng chặn: mã VietQR/EMV chuyển thẳng tiền đi được, và
    # người dùng thường không đăng QR thanh toán của mình trong nhóm chat.

    # --- Số điện thoại ---
    # Quét cả chữ trong ảnh, vì tờ rơi quảng cáo luôn in số liên hệ lên ảnh
    # chứ không gõ vào tin nhắn. Chỉ chạy khi công tắc bật - trước đây còn một
    # nhánh "số điện thoại liên hệ" cộng 2 điểm khi công tắc TẮT, tức là tắt
    # mà vẫn phạt. Đó là một trong những nguồn ban oan, đã xoá.
    if cfg.block_phones:
        phones = {re.sub(r"[\s.\-]", "", p) for p in PHONE_RE.findall(scannable)}
        phones -= cfg.allowed_phones
        if phones:
            v.chan(f"số điện thoại lạ: {', '.join(sorted(phones)[:2])}")

    # --- Giả mạo ban quản trị ---
    # Đặt tên "Trợ lý", "QTV", "Admin" mà không phải admin thật là chiêu dụ
    # thành viên nhắn riêng rồi lừa. Admin thật đã được miễn trừ từ trước nên
    # không bao giờ tới được đây.
    if cfg.block_fake_admin and not facts.is_real_admin and facts.sender_name:
        # normalize() bỏ dấu và gộp ký tự lạ về khoảng trắng, nên bắt được cả
        # "Trợ Lý", "TRO LY", và cả tên trang trí kiểu 𝓣𝓻𝓸̛̣ 𝓛𝔂́.
        khop = FAKE_ADMIN_RE.search(f" {normalize(facts.sender_name)} ")
        if khop:
            v.chan(f"tên giả mạo ban quản trị: {khop.group(0).strip()!r}")

    # --- Cố tình né bộ lọc ---
    # Chỉ giữ hai dấu hiệu KHÔNG THỂ vô tình: ký tự vô hình chèn giữa chữ, và
    # dấu câu cắt vụn từng chữ cái ("l.ừ.a đ.ả.o"). Người viết bình thường
    # không bao giờ làm hai việc này.
    #
    # Đã bỏ luật "chữ giả Latin": nó bắt cả tin nhắn tiếng Nga hay tên trang
    # trí, mà normalize() vốn đã quy homoglyph về chữ Latin rồi - từ khoá viết
    # bằng chữ Cyrillic vẫn bị các luật trên bắt bình thường.
    if INVISIBLE_RE.search(text):
        v.chan("chèn ký tự vô hình để né bộ lọc")
    elif CAT_VUN_RE.search(text):
        v.chan("cắt vụn chữ bằng dấu câu để né bộ lọc")

    # --- Hình thức ---
    # CỐ Ý không còn luật "viết hoa toàn bộ" và "lạm dụng emoji". Cả hai chưa
    # bao giờ tự kết tội được ai, chỉ góp điểm - và chúng có mặt trong hầu hết
    # những lần ban oan đo được.
    if facts.has_story:
        # Story không để lại nội dung nào soi được (nhất là khi đã hết hạn),
        # nên chỉ có tác dụng kéo người sang tài khoản khác.
        v.chan("tin chia sẻ story")
    if facts.has_buttons:
        v.chan("tin nhắn kèm nút bấm (dấu hiệu bot spam)")

    # CỐ Ý không còn luật nào về BỐI CẢNH NGƯỜI GỬI - thành viên mới, không có
    # username, đã từng vi phạm. Chúng không nói gì về tin nhắn này, chỉ nói về
    # người gửi; dùng chúng để kết tội nghĩa là phạt người vì lý lịch. Khi còn
    # chấm điểm, tổ hợp hay gặp nhất là "link lạ + thành viên mới gửi link +
    # không username gửi link" - nhìn tưởng ba bằng chứng, thực ra là một sự
    # việc đếm ba lần. Đó là tự tin giả, và là nguồn ban oan lớn nhất.

    return v
