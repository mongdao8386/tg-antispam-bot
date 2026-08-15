"""Khoá bằng mật khẩu và phím tắt điều khiển khi chạy trên máy cá nhân.

Hai việc:
  * Hỏi mật khẩu trước khi bot chạy (chỉ khi có bàn phím thật).
  * Bắt phím tắt để tắt bot, thay cho Ctrl+C vốn dễ nhầm với lệnh copy.

Lưu ý về mức bảo mật: mật khẩu này chỉ ngăn người ngồi cùng máy bấm nhầm hoặc
tò mò mở bot. Nó KHÔNG bảo vệ được BOT_TOKEN - token nằm trong .env dạng chữ
thường, ai đọc được file đó thì đã có toàn quyền với bot rồi. Muốn kín thật
thì phải khoá quyền truy cập file hoặc mã hoá ổ đĩa.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import os
import secrets
import sys
import threading

VONG_LAP = 200_000  # số vòng PBKDF2, đủ chậm để dò mật khẩu không bõ công


def bam(mat_khau: str, muoi: str) -> str:
    """Băm mật khẩu bằng PBKDF2. Không lưu mật khẩu gốc ở bất kỳ đâu."""
    return hashlib.pbkdf2_hmac(
        "sha256", mat_khau.encode(), bytes.fromhex(muoi), VONG_LAP
    ).hex()


def tao_chuoi_luu(mat_khau: str) -> str:
    """Chuỗi để ghi vào .env, dạng: pbkdf2$<muối>$<băm>"""
    muoi = secrets.token_bytes(16).hex()
    return f"pbkdf2${muoi}${bam(mat_khau, muoi)}"


def la_chuoi_bam(chuoi_luu: str) -> bool:
    return chuoi_luu.startswith("pbkdf2$") and chuoi_luu.count("$") == 2


def kiem_tra(mat_khau: str, chuoi_luu: str) -> bool:
    """So mật khẩu với giá trị lưu trong .env.

    Chấp nhận cả hai dạng:
      * pbkdf2$muối$băm — dạng chuẩn do --dat-mat-khau tạo ra
      * chữ thường      — khi người dùng sửa tay .env. Vẫn cho vào, nhưng nơi
        gọi sẽ tự nâng cấp lên dạng băm. Không chấp nhận thì người sửa tay bị
        khoá ngoài mà không hiểu vì sao.
    """
    if not la_chuoi_bam(chuoi_luu):
        return hmac.compare_digest(mat_khau, chuoi_luu)
    kieu, muoi, dung = chuoi_luu.split("$", 2)
    # compare_digest: so sánh trong thời gian cố định, tránh lộ thông tin qua
    # thời gian phản hồi.
    return hmac.compare_digest(bam(mat_khau, muoi), dung)


def hoi_mat_khau(chuoi_luu: str, so_lan: int = 3) -> bool:
    """Hỏi mật khẩu ở terminal. True nếu đúng hoặc không cần hỏi."""
    if not chuoi_luu:
        return True
    # Chạy dưới systemd trên droplet thì không có bàn phím -> bỏ qua, nếu
    # không dịch vụ sẽ treo mãi ở chỗ chờ nhập.
    if not sys.stdin or not sys.stdin.isatty():
        return True

    if not la_chuoi_bam(chuoi_luu):
        print(
            "  Lưu ý: START_PASSWORD trong .env đang là chữ thường (ai mở file "
            "cũng đọc được).\n"
            "  Nhập đúng một lần là bot tự thay bằng chuỗi băm."
        )

    for lan in range(so_lan):
        try:
            nhap = getpass.getpass("  Mật khẩu: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if kiem_tra(nhap, chuoi_luu):
            # Đang lưu chữ thường thì nâng cấp ngay, khỏi phải nhớ chạy lệnh.
            if not la_chuoi_bam(chuoi_luu):
                if _ghi_env(tao_chuoi_luu(nhap)):
                    print("  Đã băm mật khẩu và cập nhật .env.")
            return True
        con = so_lan - lan - 1
        print(f"  Sai mật khẩu.{f' Còn {con} lần thử.' if con else ''}")

    if not la_chuoi_bam(chuoi_luu):
        print(
            "\n  Quên mật khẩu? Mở file .env, xoá phần sau dấu = ở dòng\n"
            "  START_PASSWORD rồi lưu lại — bot sẽ không hỏi nữa."
        )
    else:
        print(
            "\n  Quên mật khẩu? Chạy:\n"
            "     .venv\\Scripts\\python.exe -m antispam_bot --dat-mat-khau"
        )
    return False


def _ghi_env(gia_tri: str, duong_dan_env: str = ".env") -> bool:
    """Ghi START_PASSWORD vào .env. Trả về True nếu ghi được."""
    try:
        with open(duong_dan_env, encoding="utf-8") as f:
            dong = f.read().splitlines()
    except OSError:
        return False

    thay = False
    for i, d in enumerate(dong):
        if d.startswith("START_PASSWORD="):
            dong[i] = f"START_PASSWORD={gia_tri}"
            thay = True
            break
    if not thay:
        dong += ["", f"START_PASSWORD={gia_tri}"]

    try:
        with open(duong_dan_env, "w", encoding="utf-8") as f:
            f.write("\n".join(dong) + "\n")
        return True
    except OSError:
        return False


def dat_mat_khau(duong_dan_env: str = ".env") -> int:
    """Đặt/đổi mật khẩu rồi ghi thẳng vào .env. Gọi bằng --dat-mat-khau."""
    print("Đặt mật khẩu mở bot")
    print("(để trống rồi Enter = bỏ mật khẩu, ai cũng bật được)")
    try:
        m1 = getpass.getpass("  Mật khẩu mới: ")
    except (EOFError, KeyboardInterrupt):
        print("\nHuỷ.")
        return 1

    if m1:
        m2 = getpass.getpass("  Nhập lại      : ")
        if m1 != m2:
            print("  Hai lần nhập không khớp. Chưa đổi gì cả.")
            return 1
        gia_tri = tao_chuoi_luu(m1)
    else:
        gia_tri = ""

    if not _ghi_env(gia_tri, duong_dan_env):
        print(f"  Không ghi được vào {duong_dan_env}. Kiểm tra quyền ghi file.")
        return 1

    print(f"  Đã {'đặt' if gia_tri else 'bỏ'} mật khẩu, lưu vào {duong_dan_env}")
    if gia_tri:
        print("  Mật khẩu được băm PBKDF2, file .env không chứa mật khẩu gốc.")
    return 0


# ---------------------------------------------------------------------------
# Phím tắt tắt bot
# ---------------------------------------------------------------------------


class PhimTat:
    """Nghe bàn phím để tắt bot, thay cho Ctrl+C.

    Ctrl+C trùng phím copy nên rất dễ bấm nhầm rồi tắt bot oan. Dùng một phím
    hiếm dùng (mặc định Shift+F) thì không bao giờ nhầm.

    Chỉ chạy khi có bàn phím thật. Trên droplet không có TTY nên bỏ qua, và
    systemd vẫn dừng dịch vụ bằng tín hiệu bình thường.
    """

    # Phím chức năng gửi hai byte: một byte dẫn (0x00 hoặc 0xE0) rồi tới mã
    # quét. Chữ thường chỉ gửi một byte.
    _MA_PHIM_CHUC_NANG = {
        "F1": b"\x00\x3b", "F2": b"\x00\x3c", "F3": b"\x00\x3d", "F4": b"\x00\x3e",
        "F5": b"\x00\x3f", "F6": b"\x00\x40", "F7": b"\x00\x41", "F8": b"\x00\x42",
        "F9": b"\x00\x43", "F10": b"\x00\x44", "F11": b"\xe0\x85", "F12": b"\xe0\x86",
    }

    def __init__(self, phim: str = "F", khi_tat=None):
        raw = (phim or "F").strip().upper()
        if raw in self._MA_PHIM_CHUC_NANG:
            # Phím chức năng thật: F4, F8... Bấm một mình, không cần Shift.
            self.ten = raw
            self.can_shift = False
            self._mong_doi = self._MA_PHIM_CHUC_NANG[raw]
        else:
            # Một chữ cái: bấm kèm Shift để ra chữ HOA.
            chu = raw[:1] or "F"
            self.ten = chu
            self.can_shift = True
            self._mong_doi = chu.encode()
        self.khi_tat = khi_tat
        self._chay = False
        self._luong: threading.Thread | None = None

    @property
    def mo_ta(self) -> str:
        """Câu hướng dẫn hiện cho người dùng."""
        return f"Shift+{self.ten}" if self.can_shift else self.ten

    @property
    def dung_duoc(self) -> bool:
        if os.name != "nt":
            return False
        if not sys.stdin or not sys.stdin.isatty():
            return False
        try:
            import msvcrt  # noqa: F401
            return True
        except ImportError:
            return False

    def bat_dau(self) -> None:
        if not self.dung_duoc:
            return
        self._chay = True
        self._luong = threading.Thread(target=self._nghe, daemon=True)
        self._luong.start()

    def dung(self) -> None:
        self._chay = False

    def _nghe(self) -> None:
        import msvcrt
        import time

        while self._chay:
            if msvcrt.kbhit():
                phim = msvcrt.getch()
                # Byte dẫn 0x00 / 0xE0 báo hiệu phím chức năng: phải đọc thêm
                # byte thứ hai mới biết là phím nào.
                if phim in (b"\x00", b"\xe0"):
                    phim += msvcrt.getch()
                # So khớp đúng chữ HOA: Shift+F ra b"F", còn f thường ra b"f".
                if phim == self._mong_doi and self.khi_tat:
                    self.khi_tat()
                    return
            time.sleep(0.08)
