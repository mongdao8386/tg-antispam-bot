"""Kiểm thử phần dựng menu (thuần, không cần Telegram chạy)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from antispam_bot import menu
from antispam_bot.control import CONG_TAC
from antispam_bot.presets import PRESETS


def _ma(kb) -> list[str]:
    return [b.callback_data for hang in kb.inline_keyboard for b in hang]


def _tt(**k) -> menu.TomTat:
    goc = dict(so_nhom=20, che_do="ban", dang_ngung=False, ban_24h=668,
               so_tu_cam=120, so_seeding=14, so_chien_dich=3, captcha=False)
    goc.update(k)
    return menu.TomTat(**goc)


def test_man_chinh_moi_nut_deu_co_tien_to_m():
    chu, kb = menu.man_chinh(_tt(), la_owner=True)
    ma = _ma(kb)
    assert ma and all(m.startswith("m:") for m in ma), ma
    assert "20" in chu and "668" in chu


def test_man_chinh_doi_nut_theo_trang_thai():
    _, kb_chay = menu.man_chinh(_tt(), True)
    _, kb_ngung = menu.man_chinh(_tt(dang_ngung=True), True)
    _, kb_thu = menu.man_chinh(_tt(che_do="report"), True)
    assert "m:pause:30" in _ma(kb_chay) and "m:resume" not in _ma(kb_chay)
    assert "m:resume" in _ma(kb_ngung) and "m:pause:30" not in _ma(kb_ngung)
    assert "m:act:ban" in _ma(kb_thu) and "m:act:report" in _ma(kb_chay)


def test_moi_man_hinh_phu_deu_ve_duoc_menu():
    cac = [
        menu.man_seeding([1, 2], {1: "A"}),
        menu.man_tu_cam(5, {k: (v[0], False, len(v[1])) for k, v in PRESETS.items()}),
        menu.man_link(["a.com"], ["abc"], ["0912"]),
        menu.man_cong_tac({t: True for t in CONG_TAC}, CONG_TAC),
        menu.man_van_ban("x"),
    ]
    for chu, kb in cac:
        assert "m:main" in _ma(kb), chu[:30]


def test_danh_sach_dai_bi_cat():
    ids = list(range(1, 50))
    chu, _ = menu.man_seeding(ids, {})
    assert f"và {49 - menu.TOI_DA_DONG} mục nữa" in chu
    assert "<code>49</code>" not in chu


def test_ten_nguoi_dung_duoc_thoat_html():
    chu, _ = menu.man_seeding([7], {7: "<b>x</b>"})
    assert "&lt;b&gt;" in chu and "<b>x</b>" not in chu


def test_preset_hien_dung_trang_thai():
    bo = {"cobac": ("Cờ bạc", True, 30), "dautu": ("Đầu tư", False, 20)}
    _, kb = menu.man_tu_cam(50, bo)
    nhan = [b.text for hang in kb.inline_keyboard for b in hang]
    assert any(n.startswith("✅ Cờ bạc") for n in nhan)
    assert any(n.startswith("⬜ Đầu tư") for n in nhan)


def test_cong_tac_moi_nut_mot_cong_tac():
    co = {t: (i % 2 == 0) for i, t in enumerate(CONG_TAC)}
    _, kb = menu.man_cong_tac(co, CONG_TAC)
    ma = [m for m in _ma(kb) if m.startswith("m:cong:")]
    assert sorted(m[7:] for m in ma) == sorted(CONG_TAC)


def test_moi_cach_nhap_deu_co_lenh_tuong_duong():
    for loai, c in menu.NHAP.items():
        assert c.lenh.startswith("/"), loai
        assert c.lenh in menu.cau_hoi_nhap(loai)
        assert "huy" in menu.cau_hoi_nhap(loai)
