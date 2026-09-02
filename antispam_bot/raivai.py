"""Chống rải hàng loạt: dồn tin, lặp nội dung, và nhiều acc phối hợp.

Bot chấm từng tin riêng lẻ thì không bao giờ thấy được ba kiểu tấn công này:

  1. DỒN TIN    - một người bắn 15 tin trong 8 giây
  2. LẶP LẠI    - cùng một nội dung gửi đi gửi lại, mỗi lần đổi vài chữ
  3. PHỐI HỢP   - 5 tài khoản khác nhau cùng đăng một nội dung y hệt

Kiểu 3 là nguy hiểm nhất và cũng là thứ bot thường bỏ lọt hoàn toàn: từng tin
một nhìn hoàn toàn vô hại, chỉ khi đặt cạnh nhau mới lộ ra là chiến dịch.

Toàn bộ chạy trong bộ nhớ, không đụng database - mỗi lần kiểm tra dưới 0,01 ms.
Bộ nhớ có trần cứng nên nhóm đông cỡ nào cũng không phình.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from .normalize import squeeze_keep_accents

# Nội dung ngắn hơn mức này thì bỏ qua khi so trùng lặp: "ok", "vâng", "=))"
# lặp lại là chuyện bình thường, không phải rải quảng cáo.
TOI_THIEU_KY_TU = 12

# Trần bộ nhớ, tính theo số nhóm và số người trong mỗi nhóm được theo dõi.
TRAN_NGUOI_MOI_NHOM = 2000
TRAN_VAN_TAY_MOI_NHOM = 500


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
        chien_dich[chat][vt]  - nội dung này do bao nhiêu người khác nhau gửi?
    """

    def __init__(self) -> None:
        self._nhip: dict[int, dict[int, deque[float]]] = defaultdict(dict)
        self._lap: dict[int, dict[tuple[int, str], deque[float]]] = defaultdict(dict)
        self._chien_dich: dict[int, dict[str, dict[int, float]]] = defaultdict(dict)

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
        cd = self._chien_dich[chat_id]
        if len(cd) > TRAN_VAN_TAY_MOI_NHOM:
            for vt in sorted(cd, key=lambda v: max(cd[v].values(), default=0))[:len(cd) // 4]:
                cd.pop(vt, None)

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

        # --- 3. Phối hợp: nhiều acc khác nhau, cùng nội dung ---
        # Chỉ xét chữ. Ba người cùng đăng lại một tấm meme trong 5 phút là
        # chuyện thường ở nhóm đông; ba người cùng gõ y hệt một đoạn chữ dài
        # thì gần như chắc chắn là chiến dịch.
        if vt.startswith("a:"):
            self._gioi_han(chat_id)
            return None
        nguoi_gui = self._chien_dich[chat_id].setdefault(vt, {})
        nguoi_gui[user_id] = bay_gio
        han = bay_gio - cfg.raid_window
        for uid in [u for u, t in nguoi_gui.items() if t < han]:
            nguoi_gui.pop(uid, None)
        if len(nguoi_gui) >= cfg.raid_users:
            return (
                f"{len(nguoi_gui)} tài khoản cùng đăng một nội dung "
                f"trong {cfg.raid_window // 60:.0f} phút"
            )

        self._gioi_han(chat_id)
        return None

    def dong_pham(self, chat_id: int, chu: str, anh_id: str) -> list[int]:
        """Những ai khác cũng vừa đăng đúng nội dung này (để xử lý cả ổ)."""
        vt = van_tay(chu, anh_id)
        if not vt:
            return []
        return list(self._chien_dich.get(chat_id, {}).get(vt, {}))

    def quen(self, chat_id: int, user_id: int) -> None:
        """Xoá dấu vết của một người - gọi sau khi đã xử lý xong."""
        self._nhip.get(chat_id, {}).pop(user_id, None)
        for khoa in [k for k in self._lap.get(chat_id, {}) if k[0] == user_id]:
            self._lap[chat_id].pop(khoa, None)
