"""Xét ngữ cảnh quanh từ cấm trước khi kết luận.

Đây là chỗ con bot này khác các bot chống spam thông thường. Bot phổ thông chỉ
so chuỗi: thấy "lừa đảo" là ban. Kết quả là ban oan người kể chuyện phim, người
đặt câu hỏi, người trích lại tin tức - và bỏ lọt kẻ viết né dấu.

Module này trả lời câu hỏi khác: người viết ĐANG NHẮM VÀO AI?

    "nhóm này lừa đảo đấy"          -> nhắm vào nhóm      -> xử lý
    "bộ phim nói về một vụ lừa đảo" -> đang kể chuyện     -> bỏ qua
    "nhóm này có lừa đảo không?"    -> đang hỏi           -> bỏ qua
    "công an vừa bắt nhóm lừa đảo"  -> trích tin tức      -> bỏ qua

Cách làm: quét cửa sổ chữ quanh vị trí từ cấm, tìm dấu hiệu chỉ hướng. Không
dùng mô hình ngôn ngữ nào - chỉ luật, nên vẫn nhanh (dưới 0,1 ms mỗi tin) và
kết quả luôn giải thích được, không phải hộp đen.
"""

from __future__ import annotations

import re

from .normalize import normalize

# Cửa sổ chữ xét quanh từ cấm. Câu tiếng Việt thường ngắn nên 60 ký tự mỗi bên
# là đủ ôm trọn mệnh đề chứa nó.
CUA_SO = 60

# --------------------------------------------------------------------------
# Dấu hiệu người viết NHẮM VÀO nhóm/admin ở đây -> đúng là tố cáo
# --------------------------------------------------------------------------
NHAM_VAO_DAY = re.compile(
    r"\b(?:"
    r"nhom nay|group nay|kenh nay|san nay|app nay|web nay|trang nay|shop nay"
    r"|o day|trong day|ben nay|cho nay|bon nay|tui nay|thang nay|con nay"
    r"|ad|admin|adm|qtv|chu nhom|chu kenh|chu san|thang chu|con chu"
    r"|may|m[aà]y|bon may|chung may|tui may"
    r")\b"
)

# --------------------------------------------------------------------------
# Dấu hiệu đang KỂ CHUYỆN / trích dẫn -> không nhắm vào ai ở đây
# --------------------------------------------------------------------------
KE_CHUYEN = re.compile(
    r"\b(?:"
    # phim ảnh, sách truyện
    r"phim|bo phim|tap phim|truyen|tieu thuyet|tap \d+|chuong \d+|nhan vat"
    r"|xem phim|doc truyen|cot truyen|kich ban|dien vien"
    # tin tức, pháp luật
    r"|cong an|canh sat|toa an|khoi to|bi bat|da bat|triet pha|dieu tra"
    r"|bao chi|bao dua|tin tuc|thoi su|vtv|vnexpress|dan tri|tuoi tre"
    r"|vu an|duong day|bang o|nhom toi pham"
    # kể lại chuyện đã nghe
    r"|nghe noi|nghe ke|doc duoc|thay bao|hom qua co|hom truoc|ngay xua"
    r"|hoi do|luc truoc|tung bi|da tung|co lan|nguoi ta bao|nguoi ta noi"
    # cảnh báo chung chung, không chỉ đích danh
    r"|canh giac|de phong|coi chung|luu y moi nguoi|tranh xa nhung"
    r")\b"
)

# --------------------------------------------------------------------------
# Dấu hiệu đang HỎI -> không phải khẳng định
# --------------------------------------------------------------------------
DANG_HOI = re.compile(
    # "có ... không" với 1-5 chữ ở giữa: "có lừa đảo không", "có uy tín không",
    # "có phải lừa đảo không". Chỉ cho một chữ là hụt phần lớn câu hỏi thật.
    r"\b(?:co(?:\s+\w+){1,5}\s+khong|co phai|phai khong|dung khong|that khong"
    r"|the nao|nhu nao|sao vay|tai sao|vi sao|co nen|nen khong"
    r"|cho hoi|cho minh hoi|xin hoi|ai biet|co ai biet|thuc hu|hay khong)\b"
)

# --------------------------------------------------------------------------
# Dấu hiệu đây là QUẢNG CÁO chứ không phải bình luận -> luôn xử lý
# Kẻ spam dùng chính từ "lừa đảo"/"uy tín" làm mồi: "sàn X lừa đảo, qua Y uy tín"
# --------------------------------------------------------------------------
DANG_QUANG_CAO = re.compile(
    r"\b(?:"
    r"inbox|ib\b|lien he|lh\b|zalo|telegram|call|goi ngay|dang ky|dk ngay"
    r"|truy cap|click|bam vao|link|http|www|com|net|vn\b"
    r"|uy tin|cam ket|dam bao|hoan tien|rut tien|nap tien|khuyen mai"
    r"|mien phi|tang ngay|nhan ngay|so 1|top 1|hang dau"
    r")\b"
)


class KetQua:
    """Kết luận cho một lần khớp từ cấm."""

    __slots__ = ("xu_ly", "ly_do")

    def __init__(self, xu_ly: bool, ly_do: str):
        self.xu_ly = xu_ly      # True = đúng là vi phạm, cứ xử lý
        self.ly_do = ly_do      # giải thích ngắn, để ghi log và /check

    def __bool__(self) -> bool:
        return self.xu_ly


def xet(chu: str, tu_cam: str) -> KetQua:
    """Từ cấm này xuất hiện trong ngữ cảnh nào?

    Thứ tự xét quan trọng - cái chắc chắn nhất đi trước:
      1. Có dấu hiệu quảng cáo  -> xử lý ngay, kể cả đang hỏi hay kể chuyện.
         Kẻ spam hay nguỵ trang bằng câu hỏi: "sàn kia lừa đảo hả? qua đây đi".
      2. Đang hỏi                -> bỏ qua
      3. Đang kể chuyện/trích tin -> bỏ qua
      4. Nhắm thẳng vào nhóm      -> xử lý
      5. Không rõ                 -> xử lý (thà chặt còn hơn lọt, theo ý chủ bot)
    """
    n_chu = normalize(chu)
    n_tu = normalize(tu_cam)

    vi_tri = n_chu.find(n_tu)
    if vi_tri < 0:
        # Từ cấm khớp qua dạng dồn chữ, không định vị được -> xét cả câu.
        vung = n_chu
    else:
        dau = max(0, vi_tri - CUA_SO)
        cuoi = min(len(n_chu), vi_tri + len(n_tu) + CUA_SO)
        vung = n_chu[dau:cuoi]

    if DANG_QUANG_CAO.search(vung):
        return KetQua(True, "kèm dấu hiệu quảng cáo")
    if DANG_HOI.search(vung):
        return KetQua(False, "đang hỏi, không phải khẳng định")
    if KE_CHUYEN.search(vung):
        return KetQua(False, "đang kể chuyện/trích tin, không nhắm vào nhóm")
    if NHAM_VAO_DAY.search(vung):
        return KetQua(True, "nhắm thẳng vào nhóm/admin")
    return KetQua(True, "không có ngữ cảnh làm nhẹ")


def loc(chu: str, cac_tu: list[str]) -> tuple[list[str], list[str]]:
    """Lọc danh sách từ cấm đã khớp qua bộ xét ngữ cảnh.

    Trả về (những từ thật sự vi phạm, giải thích cho những từ được bỏ qua).
    """
    vi_pham: list[str] = []
    bo_qua: list[str] = []
    for tu in cac_tu:
        kq = xet(chu, tu)
        if kq.xu_ly:
            vi_pham.append(tu)
        else:
            bo_qua.append(f"{tu} ({kq.ly_do})")
    return vi_pham, bo_qua
