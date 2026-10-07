"""Tin trả lời dài hơn giới hạn Telegram phải được cắt, không được rơi mất.

/status với 21 nhóm vượt 4096 ký tự: Telegram trả "Message is too long" và
owner gõ lệnh không nhận được gì (07/10, ba lần trong bảy phút).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot.bot import TIN_TOI_DA, _chia_tin


def test_tin_ngan_giu_nguyen():
    assert _chia_tin("xin chào") == ["xin chào"]
    assert _chia_tin("") == [""]


def test_cat_o_dong_trong_va_khong_mat_chu():
    khoi = ["<b>Nhóm %d</b> (<code>-100%d</code>)\n  ✅ đủ quyền\n  đã xử lý: <b>%d</b>" % (i, i, i)
            for i in range(60)]
    text = "\n\n".join(khoi)
    assert len(text) > TIN_TOI_DA
    phan = _chia_tin(text)
    assert len(phan) > 1
    assert all(len(p) <= TIN_TOI_DA for p in phan)
    # Mỗi khối còn nguyên vẹn trong đúng một phần, không khối nào bị xẻ đôi.
    for k in khoi:
        assert sum(k in p for p in phan) == 1, k
    assert "\n\n".join(phan) == text


def test_the_html_khong_bi_cat_doi():
    dong = ["<code>%08d</code> — <i>tên %d</i>" % (i, i) for i in range(300)]
    for p in _chia_tin("\n".join(dong)):
        assert p.count("<code>") == p.count("</code>")
        assert p.count("<i>") == p.count("</i>")


def test_mot_dong_dai_bat_thuong_van_cat_duoc():
    text = "a" * (TIN_TOI_DA * 2 + 5)
    phan = _chia_tin(text)
    assert all(len(p) <= TIN_TOI_DA for p in phan) and "".join(phan) == text
