#!/bin/bash
# =============================================================================
#  CỨU HỘ: chạy trong RECOVERY MODE của Hostinger (hoặc rescue của nhà cung
#  cấp khác) khi không SSH được vào VPS dù khoá đã nằm trong authorized_keys.
#
#  Triệu chứng đúng của ca này:  ssh -v báo "Server accepts key" rồi vẫn
#  "Permission denied"  ->  sshd cấm root đăng nhập (PermitRootLogin no /
#  AllowUsers không có root). Console cũng "Login incorrect" -> root bị khoá.
#
#  Script làm gì (trên ĐĨA của VPS, đang được gắn vào hệ cứu hộ):
#    1. Tìm phân vùng gốc của VPS (kể cả LVM) và mount vào /mnt/vps
#    2. Cho root đăng nhập bằng KHOÁ (PermitRootLogin prohibit-password),
#       gỡ AllowUsers/DenyUsers chặn root, bật PubkeyAuthentication
#    3. Thêm khoá công khai của máy quản trị vào /root/.ssh/authorized_keys
#    4. In ra những gì đã thấy để hiểu vì sao bị chặn
#
#  KHÔNG đụng website, không đụng dữ liệu nào khác, không đổi mật khẩu ai.
#  Xong thì tắt recovery mode trong hPanel để máy khởi động lại bình thường.
#
#  Dùng:  curl -fsSL https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/cuu-ho.sh | bash
# =============================================================================
set -u

KHOA_URL="https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/khoa-admin.pub"
# Dự phòng khi hệ cứu hộ không có mạng: khoá ghi thẳng ở đây (khoá CÔNG KHAI).
KHOA_SAN="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHlXGqqZO8MTdv6emrNc/ymk1WO8Fr5kgAqvBEP5i/2B admin@DESKTOP-3P46HDN"
MNT=/mnt/vps

echo "=============================================="
echo " Cứu hộ SSH cho VPS"
echo "=============================================="

# --- 1. Tìm và mount phân vùng gốc ------------------------------------------
vgchange -ay >/dev/null 2>&1 || true          # bật LVM nếu có
mkdir -p "$MNT"
GOC=""
# Thử từng phân vùng có hệ thống file Linux; cái nào có /etc/ssh là gốc.
while read -r DEV FS; do
    [ -n "$FS" ] || continue
    case "$FS" in ext4|ext3|xfs|btrfs) ;; *) continue ;; esac
    mountpoint -q "$MNT" && umount "$MNT" 2>/dev/null
    if mount "$DEV" "$MNT" 2>/dev/null && [ -d "$MNT/etc/ssh" ]; then
        GOC="$DEV"; break
    fi
done < <(lsblk -rno PATH,FSTYPE 2>/dev/null || lsblk -rno NAME,FSTYPE | sed 's#^#/dev/#')

if [ -z "$GOC" ]; then
    echo " ✗ Không tìm thấy phân vùng gốc của VPS. Chạy 'lsblk -f' rồi mount tay:"
    echo "     mount /dev/vdaX $MNT   (chọn phân vùng ext4 lớn nhất)"
    echo "   sau đó chạy lại script này."
    exit 1
fi
echo " ✓ Phân vùng gốc: $GOC  (đã mount vào $MNT)"

# --- 2. Vì sao bị chặn? In ra trước khi sửa -----------------------------------
echo
echo " Cấu hình sshd hiện tại liên quan tới root:"
grep -rHnE "^\s*(PermitRootLogin|AllowUsers|DenyUsers|AllowGroups|PubkeyAuthentication|PasswordAuthentication|Match)" \
    "$MNT/etc/ssh/sshd_config" "$MNT"/etc/ssh/sshd_config.d/*.conf 2>/dev/null \
    | sed "s#^$MNT#  #" || echo "  (không có dòng nào - dùng mặc định)"
if grep -q '^root:!' "$MNT/etc/shadow" 2>/dev/null; then
    echo "  root: mật khẩu ĐANG BỊ KHOÁ trong /etc/shadow (đăng nhập console không được)"
fi

# --- 3. Sửa sshd: cho root vào bằng khoá ---------------------------------------
echo
echo " Sửa sshd..."
for F in "$MNT/etc/ssh/sshd_config" "$MNT"/etc/ssh/sshd_config.d/*.conf; do
    [ -f "$F" ] || continue
    sed -i -E 's/^\s*#?\s*PermitRootLogin\s+.*/PermitRootLogin prohibit-password/' "$F"
    sed -i -E 's/^\s*PubkeyAuthentication\s+no/PubkeyAuthentication yes/' "$F"
    # AllowUsers/DenyUsers/AllowGroups chặn root -> vô hiệu hoá dòng đó (giữ lại dạng chú thích).
    sed -i -E 's/^(\s*(AllowUsers|DenyUsers|AllowGroups)\s+.*)$/# [cuu-ho] \1/' "$F"
done
# Bảo đảm có đúng một dòng PermitRootLogin ở file chính.
grep -qE '^PermitRootLogin' "$MNT/etc/ssh/sshd_config" \
    || echo "PermitRootLogin prohibit-password" >> "$MNT/etc/ssh/sshd_config"
# Một số bản Ubuntu để file 50-cloud-init.conf đè lên; đặt thêm file ưu tiên cao nhất.
mkdir -p "$MNT/etc/ssh/sshd_config.d"
printf 'PermitRootLogin prohibit-password\nPubkeyAuthentication yes\n' > "$MNT/etc/ssh/sshd_config.d/00-cuu-ho.conf"
echo " ✓ root được đăng nhập bằng khoá (không bằng mật khẩu)"

# --- 4. Khoá công khai của máy quản trị --------------------------------------
echo
KHOA="$(curl -fsSL --max-time 10 "$KHOA_URL" 2>/dev/null || true)"
[ -n "$KHOA" ] || { KHOA="$KHOA_SAN"; echo " (không tải được từ GitHub, dùng khoá ghi sẵn)"; }
mkdir -p "$MNT/root/.ssh"
touch "$MNT/root/.ssh/authorized_keys"
grep -qF "$KHOA" "$MNT/root/.ssh/authorized_keys" || echo "$KHOA" >> "$MNT/root/.ssh/authorized_keys"
chmod 700 "$MNT/root/.ssh"
chmod 600 "$MNT/root/.ssh/authorized_keys"
chown -R 0:0 "$MNT/root/.ssh"
echo " ✓ Khoá đã nằm trong /root/.ssh/authorized_keys ($(wc -l < "$MNT/root/.ssh/authorized_keys") khoá)"

# --- 5. Xong -------------------------------------------------------------------
sync
umount "$MNT" 2>/dev/null && echo " ✓ Đã tháo $MNT"
echo
echo "=============================================="
echo " XONG. Giờ vào hPanel TẮT recovery mode để máy khởi động lại bình thường."
echo " Sau đó từ máy quản trị:  ssh root@<IP>  là vào thẳng, không hỏi gì."
echo "=============================================="
