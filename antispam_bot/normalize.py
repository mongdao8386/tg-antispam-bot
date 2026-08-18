"""Chuẩn hoá văn bản để chống né bộ lọc.

Spammer hay chèn ký tự vô hình, dùng chữ Cyrillic/Hy Lạp trông giống Latin,
viết leetspeak (`k1em t1en`), hoặc chèn dấu câu giữa các chữ (`l.ừ.a đ.ả.o`).
Module này đưa mọi biến thể đó về một dạng chuẩn duy nhất trước khi dò từ khoá.
"""

from __future__ import annotations

import re
import unicodedata

# Ký tự vô hình / định dạng thường dùng để cắt vụn từ khoá.
INVISIBLE_RE = re.compile(
    "["
    "­"          # soft hyphen
    "͏"          # combining grapheme joiner
    "؜"          # arabic letter mark
    "᠎"          # mongolian vowel separator
    "​-‏"   # zero-width space/joiner + LTR/RTL marks
    "‪-‮"   # bidi overrides
    "⁠-⁤"   # word joiner, invisible operators
    "⁦-⁯"   # bidi isolates, deprecated format chars
    "︀-️"   # variation selectors
    "﻿"          # BOM / zero-width no-break space
    "]"
)

# Chữ cái ngoài bảng Latin nhưng trông giống hệt chữ Latin.
HOMOGLYPHS = str.maketrans(
    {
        # Cyrillic
        "а": "a", "в": "b", "с": "c", "е": "e", "ѕ": "s", "һ": "h", "і": "i",
        "ј": "j", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "т": "t",
        "у": "y", "х": "x", "ԁ": "d", "ɡ": "g", "ν": "v",
        # Hy Lạp
        "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ο": "o", "ρ": "p",
        "τ": "t", "υ": "u", "χ": "x", "ϲ": "c",
        # Fullwidth
        "０": "0", "１": "1", "２": "2", "３": "3", "４": "4", "５": "5",
        "６": "6", "７": "7", "８": "8", "９": "9",
    }
)

LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

# Mọi thứ không phải chữ/số đều thành khoảng trắng ở bước cuối.
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
REPEAT_RE = re.compile(r"(.)\1{2,}")


def strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt: 'lừa đảo' -> 'lua dao'."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize(text: str) -> str:
    """Dạng chuẩn dùng để so khớp từ khoá (giữ khoảng trắng giữa các từ)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_RE.sub("", text)
    text = text.lower().translate(HOMOGLYPHS)
    text = strip_diacritics(text)
    text = text.translate(LEET)
    text = NON_ALNUM_RE.sub(" ", text)
    text = REPEAT_RE.sub(r"\1\1", text)  # 'kiiiiem' -> 'kiiem'
    return text.strip()


def squeeze(text: str) -> str:
    """Dạng chuẩn đã bỏ hết khoảng trắng, bắt được 'k i e m t i e n'."""
    return normalize(text).replace(" ", "")


def obfuscation_score(text: str) -> int:
    """Điểm cho dấu hiệu cố tình né bộ lọc."""
    if not text:
        return 0
    score = 0
    if INVISIBLE_RE.search(text):
        score += 3
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    fake_latin = sum(1 for ch in text.lower() if ord(ch) in HOMOGLYPHS)
    if fake_latin and fake_latin >= max(2, latin // 10):
        score += 3
    # Chèn dấu câu giữa từng chữ cái: "l.ừ.a đ.ả.o"
    if re.search(r"(?:\w[.\-_*|]){4,}\w", text):
        score += 2
    return score


# Dấu hiệu người dùng đang HỎI chứ không khẳng định. Người vào nhóm hỏi
# "nhóm này có uy tín không?" là người cẩn thận, không phải kẻ phá hoại -
# ban họ là mất người dùng thật.
_QUESTION_PATTERNS = (
    # "có ... không / ko / k / hông / hem"
    r"\bco\b.{0,40}\b(khong|ko|k|hong|hem)\b",
    # đuôi nghi vấn phổ biến
    r"\b(phai khong|dung khong|that khong|co that|thuc hu|hay khong)\b",
    # mở đầu bằng lời hỏi
    r"\b(cho hoi|cho minh hoi|cho em hoi|xin hoi|hoi chut|ai biet|"
    r"co ai biet|ai tung|ad oi|admin oi|anh chi oi|moi nguoi oi)\b",
    # từ để hỏi
    r"\b(the nao|nhu nao|nhu the nao|sao vay|tai sao|vi sao|co nen|nen khong)\b",
    # tiểu từ nghi vấn cuối câu
    r"\b(vay a|vay ta|ha ban|nhi|the a|a\?)\s*$",
)
_QUESTION_RE = re.compile("|".join(_QUESTION_PATTERNS))


def looks_like_question(text: str) -> bool:
    """Câu này là đang hỏi hay đang khẳng định?

    Dùng để KHÔNG ban người hỏi "nhóm này có lừa đảo không?". Chỉ nên tin kết
    quả này khi tin nhắn không kèm link/ảnh/@ - xem cách dùng trong bot.py,
    nếu không kẻ spam chỉ cần chấm thêm dấu ? là thoát.
    """
    if not text:
        return False
    if "?" in text:
        return True
    return bool(_QUESTION_RE.search(normalize(text)))


# Như NON_ALNUM_RE nhưng giữ lại chữ có dấu tiếng Việt.
NON_ALNUM_VN_RE = re.compile(r"[^0-9a-zà-ỹ]+")


def normalize_keep_accents(text: str) -> str:
    """Chuẩn hoá NHƯNG GIỮ DẤU tiếng Việt.

    Vẫn chống được ký tự vô hình, chữ giả Latin (Cyrillic/Hy Lạp) và leetspeak
    - chỉ khác normalize() ở chỗ không bỏ dấu.

    Cần vì bỏ dấu gây đụng độ chết người: "lựa đào" và "lừa đảo" đều thành
    "lua dao", nên câu nói chuyện bình thường bị coi là tố cáo lừa đảo.
    """
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_RE.sub("", text)
    text = text.lower()
    text = text.translate(HOMOGLYPHS).translate(LEET)
    text = NON_ALNUM_VN_RE.sub(" ", text)
    return REPEAT_RE.sub(r"\1\1", text).strip()


def squeeze_keep_accents(text: str) -> str:
    """Như normalize_keep_accents() nhưng bỏ luôn khoảng trắng.

    Bắt kiểu chèn khoảng trắng để né lọc: "l ừ a  đ ả o" -> "lừađảo".
    """
    return normalize_keep_accents(text).replace(" ", "")
