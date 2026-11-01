"""Chống ảnh/video đăng lại trong cùng một nhóm.

KHÁC LUẬT CHIẾN DỊCH THẾ NÀO
Luật chiến dịch đếm bao nhiêu TÀI KHOẢN khác nhau cùng đăng một thứ, trên MỌI
nhóm, rồi ban. Ở đây đơn giản hơn: trong một nhóm, ảnh/video nào đã có người
đăng trong vài ngày gần đây thì bản đăng lại bị xoá - kể cả chính người cũ đăng
lại để đẩy bài. Không ban ai.

Chỉ chạy ở những nhóm liệt kê trong CHONG_TRUNG_NHOM: nhóm rao vặt, review thì
đăng lại là rác, còn nhóm trò chuyện thì một tấm meme quay lại là chuyện thường.

HAI TẦNG
1. file_unique_id: Telegram giữ nguyên mã này khi cùng một file được chuyển
   tiếp hay gửi lại. Không tải, không tính gì - bắt được kiểu đăng lại phổ biến
   nhất.
2. pHash (anhhash.py): tải lên lại, nén lại, đổi cỡ thì mã trên đổi, nhưng vân
   tay tri giác gần như không. Ảnh: một vân tay. Video: ba vân tay ở 10%, 50%,
   90% thời lượng - không lấy đúng khung đầu/cuối vì video hay mở và đóng bằng
   màn hình đen, mà ảnh phẳng thì không có vân tay.

VIDEO KHÔNG CẦN CÀI FFMPEG
OpenCV cài qua pip đã kèm sẵn bộ giải mã của FFmpeg (avcodec/avformat), nên
cv2.VideoCapture đọc thẳng được mp4 của Telegram - không gói hệ thống, không
tiến trình con. Có trên cả máy Windows lẫn VPS.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .anhhash import AVAILABLE, van_tay_khung
from .qrscan import cv2
from .vantay import lech

log = logging.getLogger("antispam.trung")

# Vị trí cắt khung hình, tính theo phần thời lượng video.
MOC = (0.1, 0.5, 0.9)

# Bot API chỉ cho bot tải file tới 20MB. Video lớn hơn chỉ so được bằng
# file_unique_id.
TOI_DA_TAI = 20_000_000

# Hai video lệch nhau quá chừng này giây thì không thể là một. Telegram làm
# tròn thời lượng về giây, nén lại có thể lệch thêm một khung.
LECH_THOI_LUONG = 1

# Cần ít nhất bấy nhiêu khung so được (cả hai bên đều có vân tay) mới kết luận
# hai video là một. Một khung trùng thì chưa nói lên gì: nhiều video mở đầu
# bằng cùng một logo kênh.
KHUNG_TOI_THIEU = 2

# Giải mã video nặng hơn ảnh nhiều mà VPS dùng chung với website, nên mỗi lúc
# chỉ làm một video. Video hiếm hơn ảnh nhiều nên hàng chờ không dài.
_sem: asyncio.Semaphore | None = None


def _limiter() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(1)
    return _sem


def ma_hoa(cac_vt: list[int | None]) -> str:
    """Vân tay -> chuỗi lưu database. Ảnh: 16 ký tự hex. Video: ba cụm cách nhau
    dấu phẩy, khung phẳng để trống. Không có khung nào dùng được thì chuỗi rỗng."""
    if all(v is None for v in cac_vt):
        return ""
    return ",".join("" if v is None else f"{v:016x}" for v in cac_vt)


def giai_ma(chuoi: str) -> list[int | None]:
    out: list[int | None] = []
    for phan in (chuoi or "").split(","):
        try:
            out.append(int(phan, 16) if phan else None)
        except ValueError:
            out.append(None)
    return out


def giong_nhau(a: list[int | None], b: list[int | None], lech_toi_da: int) -> bool:
    """Hai bộ vân tay có phải cùng một ảnh/video không.

    Mọi khung so được đều phải gần nhau, không phải chỉ đa số: hai video khác
    nhau mà chung cảnh mở đầu vẫn lệch hẳn ở khung giữa.
    """
    cap = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not cap or (len(a) > 1 and len(cap) < KHUNG_TOI_THIEU):
        return False
    return all(lech(x, y) <= lech_toi_da for x, y in cap)


def bo_so(
    cac_vt: list[int | None], thoi_luong: int, lech_toi_da: int
) -> Callable[[str, int], bool]:
    """Hàm so một dòng đã lưu (file_hash, duration) với bản đang xét."""
    def so(file_hash: str, duration: int) -> bool:
        if thoi_luong and duration and abs(thoi_luong - duration) > LECH_THOI_LUONG:
            return False
        return giong_nhau(cac_vt, giai_ma(file_hash), lech_toi_da)
    return so


def _cat_khung(duong_dan: str, thoi_luong: float) -> list[int | None]:
    cap = cv2.VideoCapture(duong_dan)
    try:
        if not cap.isOpened():
            return []
        if thoi_luong <= 0:
            # Telegram ghi 0 giây cho video quá ngắn: tự đếm từ file.
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            thoi_luong = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps if fps > 0 else 0
        out: list[int | None] = []
        for moc in MOC:
            cap.set(cv2.CAP_PROP_POS_MSEC, moc * thoi_luong * 1000)
            ok, khung = cap.read()
            out.append(van_tay_khung(khung) if ok else None)
        return out
    finally:
        cap.release()


async def van_tay_video(duong_dan: str, thoi_luong: float) -> list[int | None]:
    """Vân tay ba khung hình của một file video. Rỗng nếu không đọc được."""
    if not AVAILABLE:
        return []
    async with _limiter():
        try:
            # OpenCV thả GIL khi giải mã nên chạy ở thread không chặn bot.
            return await asyncio.to_thread(_cat_khung, duong_dan, thoi_luong)
        except Exception as exc:  # file hỏng, codec lạ - không đáng làm sập bot
            log.debug("Không cắt được khung video %s: %s", duong_dan, exc)
            return []
