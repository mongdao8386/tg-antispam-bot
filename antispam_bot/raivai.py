"""Chống rải: một NGƯỜI đăng quá nhanh hoặc đăng lặp lại.

  1. DỒN TIN  - một người bắn 15 tin trong 8 giây
  2. LẶP LẠI  - một người gửi đi gửi lại cùng một nội dung

Cả hai đều nói về MỘT tài khoản trong MỘT nhóm, trong vài giây tới vài phút.
Loại đó hợp với bộ nhớ tạm: nhanh, không đụng database, khởi động lại thì
quên - không ai bị phạt vì chuyện hôm qua.

Kiểu thứ ba, NHIỀU TÀI KHOẢN cùng đăng một bài, đã chuyển sang bộ nhớ lưu
trong database (xem storage.ghi_noi_dung và vantay.py). Lý do: đo trên dữ
liệu thật, chiến dịch lớn nhất dùng 334 tài khoản trên 16 nhóm nhưng kéo dài
27 NGÀY, chỗ dày nhất chỉ 14 tin mỗi 5 phút. Một cửa sổ 5 phút trong bộ nhớ
tạm, lại đếm riêng từng nhóm, gần như mù trước kiểu rải chậm đó.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from .normalize import squeeze_keep_accents

# Nội dung ngắn hơn mức này thì bỏ qua khi so trùng lặp: "ok", "vâng", "=))"
# lặp lại là chuyện bình thường, không phải rải quảng cáo.
TOI_THIEU_KY_TU = 12

# Trần bộ nhớ, tính theo số người trong mỗi nhóm được theo dõi.
TRAN_NGUOI_MOI_NHOM = 2000


def van_tay(chu: str, anh_id: str = "") -> str:
    """Dấu nhận dạng nội dung, bỏ qua khác biệt vụn vặt.

    Dùng bản dồn chữ giữ dấu nên "MUA NGAY!!!" và "mua ngay" ra cùng một dấu,
    còn "lựa đào" và "lừa đảo" vẫn khác nhau. Ảnh thì lấy thẳng file_unique_id
    của Telegram - cùng một tấm ảnh gửi lại luôn cho cùng mã.
    """
    if anh_id:
        return f"a:{anh_id}"
    goc = squeeze_keep_accents(chu or "")
    return f"t:{goc}" if len(goc) >= TOI_THIEU_KY_TU else ""


class BoTheoDoi:
    """Theo dõi nhịp gửi tin của từng nhóm.

    Ba sổ ghi, mỗi sổ trả lời một câu hỏi:
        nhip[chat][user]      - người này gửi bao nhiêu tin gần đây?
        lap[chat][user][vt]   - người này gửi nội dung này mấy lần?
    """

    def __init__(self) -> None:
        self._nhip: dict[int, dict[int, deque[float]]] = defaultdict(dict)
        self._lap: dict[int, dict[tuple[int, str], deque[float]]] = defaultdict(dict)

    # -- dọn dẹp ---------------------------------------------------------

    @staticmethod
    def _cat_cu(hang: deque[float], han: float) -> None:
        while hang and hang[0] < han:
            hang.popleft()

    def _gioi_han(self, chat_id: int) -> None:
        """Giữ bộ nhớ trong trần, bỏ những mục lâu nhất không đụng tới."""
        nhip = self._nhip[chat_id]
        if len(nhip) > TRAN_NGUOI_MOI_NHOM:
            for uid in sorted(nhip, key=lambda u: nhip[u][-1] if nhip[u] else 0)[:len(nhip) // 4]:
                nhip.pop(uid, None)

    # -- ghi nhận và kết luận --------------------------------------------

    def ghi(
        self,
        chat_id: int,
        user_id: int,
        chu: str,
        anh_id: str,
        cfg,
    ) -> str | None:
        """Ghi nhận một tin. Trả về lý do vi phạm, hoặc None nếu bình thường."""
        if cfg.flood_msgs <= 0:
            return None
        bay_gio = time.monotonic()
        vt = van_tay(chu, anh_id)

        # --- 1. Dồn tin: nhiều tin trong thời gian ngắn ---
        hang = self._nhip[chat_id].setdefault(user_id, deque(maxlen=64))
        hang.append(bay_gio)
        self._cat_cu(hang, bay_gio - cfg.flood_window)
        if len(hang) >= cfg.flood_msgs:
            return f"rải {len(hang)} tin trong {cfg.flood_window:.0f} giây"

        if not vt:
            self._gioi_han(chat_id)
            return None

        # --- 2. Lặp lại: cùng người, cùng nội dung ---
        khoa = (user_id, vt)
        lap = self._lap[chat_id].setdefault(khoa, deque(maxlen=32))
        lap.append(bay_gio)
        self._cat_cu(lap, bay_gio - cfg.repeat_window)
        if len(lap) >= cfg.repeat_limit:
            return f"gửi lại cùng một nội dung {len(lap)} lần"

        self._gioi_han(chat_id)
        return None

    def quen(self, chat_id: int, user_id: int) -> None:
        """Xoá dấu vết của một người - gọi sau khi đã xử lý xong."""
        self._nhip.get(chat_id, {}).pop(user_id, None)
        for khoa in [k for k in self._lap.get(chat_id, {}) if k[0] == user_id]:
            self._lap[chat_id].pop(khoa, None)
