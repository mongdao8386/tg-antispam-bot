#!/bin/bash
# =============================================================================
#  CỨU HỘ: chạy trong RECOVERY / EMERGENCY MODE của Hostinger khi không SSH
#  được vào VPS dù khoá đã nằm trong authorized_keys.
#
#  Triệu chứng đúng của ca này:  ssh -v báo "Server accepts key" rồi vẫn
#  "Permission denied"  ->  sshd cấm root (PermitRootLogin no / AllowUsers /
#  AuthenticationMethods đòi thêm mật khẩu). Console cũng "Login incorrect".
#
#  Bản 2 - rút kinh nghiệm lần chạy đầu: hệ cứu hộ có thể mount NHIỀU đĩa
#  (đĩa thật + đĩa backup) và ta đã sửa nhầm đĩa. Bản này:
#    - liệt kê mọi đĩa/phân vùng kèm dung lượng để nhìn ra đĩa thật
#    - sửa TẤT CẢ phân vùng có /etc/ssh (sửa nhầm đĩa backup thì vô hại)
#    - sau khi sửa, chạy `sshd -T` trong chroot để in cấu hình HIỆU LỰC,
#      không tin vào việc sed đã chạy
#    - gỡ cả AuthenticationMethods, AllowUsers/Groups, DenyUsers chặn root
#    - xoá khoá faillock/tally của root nếu có
#
#  KHÔNG đụng website, không đổi mật khẩu ai. Xong thì tắt emergency mode.
#
#  Dùng:  curl -fsSL https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/cuu-ho.sh | bash
# =============================================================================
set -u

KHOA_URL="https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/khoa-admin.pub"
KHOA_SAN="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHlXGqqZO8MTdv6emrNc/ymk1WO8Fr5kgAqvBEP5i/2B admin@DESKTOP-3P46HDN"

echo "=============================================="
echo " Cứu hộ SSH cho VPS (bản 2)"
echo "=============================================="

# --- 0. Toàn cảnh đĩa: đĩa nào là đĩa thật? --------------------------------
echo
echo " Đĩa và phân vùng (đĩa thật của VPS là đĩa ~100G):"
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT 2>/dev/null | sed 's/^/   /'
vgchange -ay >/dev/null 2>&1 || true

# --- 1. Gom mọi phân vùng gốc: đã mount ở /mnt/* + mount thêm cái chưa mount ---
GOCS=()
for D in /mnt /mnt/*; do
    [ -d "$D/etc/ssh" ] && GOCS+=("$D")
done
# Phân vùng Linux nào chưa được hệ cứu hộ mount (LVM, đĩa thứ hai...) thì mount thêm.
i=0
while read -r DEV FS; do
    [ -n "$FS" ] || continue
    case "$FS" in ext4|ext3|xfs|btrfs) ;; *) continue ;; esac
    grep -qs " $DEV " /proc/mounts && continue          # đã mount rồi
    grep -qs "^$DEV " /proc/mounts && continue
    i=$((i+1)); M="/mnt/cuu-ho-$i"; mkdir -p "$M"
    if mount "$DEV" "$M" 2>/dev/null; then
        if [ -d "$M/etc/ssh" ]; then GOCS+=("$M"); else umount "$M" 2>/dev/null; fi
    fi
done < <(lsblk -rno PATH,FSTYPE 2>/dev/null)

if [ ${#GOCS[@]} -eq 0 ]; then
    echo " ✗ Không thấy phân vùng nào có /etc/ssh. Gửi ảnh 'lsblk -f' ở trên cho người hỗ trợ."
    exit 1
fi

KHOA="$(curl -fsSL --max-time 10 "$KHOA_URL" 2>/dev/null || true)"
[ -n "$KHOA" ] || { KHOA="$KHOA_SAN"; echo " (không tải được khoá từ GitHub, dùng khoá ghi sẵn)"; }

# --- 2. Sửa TỪNG phân vùng gốc ------------------------------------------------
for MNT in "${GOCS[@]}"; do
    echo
    echo "=============================================="
    echo " Phân vùng: $MNT"
    echo "   hostname : $(cat "$MNT/etc/hostname" 2>/dev/null)"
    echo "   machine  : $(cut -c1-12 "$MNT/etc/machine-id" 2>/dev/null)..."
    echo "   log mới  : $(ls -t --time-style=long-iso -l "$MNT"/var/log/ 2>/dev/null | sed -n 2p | awk '{print $6, $7, $8}')"
    echo "   web      : $(ls "$MNT/var/www" "$MNT/opt" 2>/dev/null | tr '\n' ' ' | cut -c1-60)"

    echo
    echo "   sshd TRƯỚC khi sửa:"
    grep -rHnE "^\s*(PermitRootLogin|AllowUsers|DenyUsers|AllowGroups|DenyGroups|AuthenticationMethods|PubkeyAuthentication|PasswordAuthentication|AuthorizedKeysFile|Match|Include)" \
        "$MNT/etc/ssh/sshd_config" "$MNT"/etc/ssh/sshd_config.d/*.conf 2>/dev/null | sed "s#^$MNT#     #" \
        || echo "     (mặc định)"
    grep -q '^root:!' "$MNT/etc/shadow" 2>/dev/null && echo "     root: mật khẩu bị khoá trong /etc/shadow"

    # -- sửa --
    for F in "$MNT/etc/ssh/sshd_config" "$MNT"/etc/ssh/sshd_config.d/*.conf; do
        [ -f "$F" ] || continue
        sed -i -E 's/^\s*#?\s*PermitRootLogin\s+.*/PermitRootLogin prohibit-password/' "$F"
        sed -i -E 's/^\s*PubkeyAuthentication\s+no/PubkeyAuthentication yes/' "$F"
        # Những dòng có thể chặn root hoặc đòi thêm mật khẩu -> vô hiệu hoá (giữ dạng chú thích).
        sed -i -E 's/^(\s*(AllowUsers|DenyUsers|AllowGroups|DenyGroups|AuthenticationMethods)\s+.*)$/# [cuu-ho] \1/' "$F"
    done
    grep -qE '^PermitRootLogin' "$MNT/etc/ssh/sshd_config" \
        || echo "PermitRootLogin prohibit-password" >> "$MNT/etc/ssh/sshd_config"
    # Bảo đảm main config có Include (Ubuntu mặc định có; nếu bị xoá thì file .d vô dụng).
    grep -qE '^\s*Include\s+/etc/ssh/sshd_config.d' "$MNT/etc/ssh/sshd_config" \
        || sed -i '1i Include /etc/ssh/sshd_config.d/*.conf' "$MNT/etc/ssh/sshd_config"
    mkdir -p "$MNT/etc/ssh/sshd_config.d"
    printf 'PermitRootLogin prohibit-password\nPubkeyAuthentication yes\nAuthorizedKeysFile .ssh/authorized_keys\n' \
        > "$MNT/etc/ssh/sshd_config.d/00-cuu-ho.conf"

    # -- khoá --
    mkdir -p "$MNT/root/.ssh"; touch "$MNT/root/.ssh/authorized_keys"
    grep -qF "$KHOA" "$MNT/root/.ssh/authorized_keys" || echo "$KHOA" >> "$MNT/root/.ssh/authorized_keys"
    chmod 700 "$MNT/root/.ssh"; chmod 600 "$MNT/root/.ssh/authorized_keys"; chown -R 0:0 "$MNT/root/.ssh"
    chmod 755 "$MNT/root" 2>/dev/null || chmod 700 "$MNT/root"

    # -- gỡ khoá tài khoản do đăng nhập sai nhiều (faillock/tally) --
    rm -f "$MNT"/var/run/faillock/root "$MNT"/var/lib/faillock/root 2>/dev/null
    rm -f "$MNT"/var/log/tallylog 2>/dev/null

    # -- Lối thứ hai, không phụ thuộc PermitRootLogin: user botadmin có sudo --
    # Root bị cấm kiểu gì thì 'ssh botadmin@IP' rồi 'sudo -i' vẫn thành root.
    if ! grep -q '^botadmin:' "$MNT/etc/passwd"; then
        chroot "$MNT" useradd -m -s /bin/bash -u 1500 botadmin 2>/dev/null \
            || chroot "$MNT" useradd -m -s /bin/bash botadmin 2>/dev/null
    fi
    if grep -q '^botadmin:' "$MNT/etc/passwd"; then
        HOME_BA="$MNT/home/botadmin"
        mkdir -p "$HOME_BA/.ssh"; touch "$HOME_BA/.ssh/authorized_keys"
        grep -qF "$KHOA" "$HOME_BA/.ssh/authorized_keys" || echo "$KHOA" >> "$HOME_BA/.ssh/authorized_keys"
        chmod 700 "$HOME_BA/.ssh"; chmod 600 "$HOME_BA/.ssh/authorized_keys"
        UID_BA=$(grep '^botadmin:' "$MNT/etc/passwd" | cut -d: -f3)
        GID_BA=$(grep '^botadmin:' "$MNT/etc/passwd" | cut -d: -f4)
        chown -R "$UID_BA:$GID_BA" "$HOME_BA"
        mkdir -p "$MNT/etc/sudoers.d"
        echo 'botadmin ALL=(ALL) NOPASSWD:ALL' > "$MNT/etc/sudoers.d/botadmin"
        chmod 440 "$MNT/etc/sudoers.d/botadmin"
        # Mở khoá mật khẩu (useradd tạo tài khoản ở trạng thái khoá '!' - key
        # login vẫn được, nhưng vài PAM từ chối tài khoản khoá).
        sed -i 's/^botadmin:!:/botadmin:*:/' "$MNT/etc/shadow"
        echo "   ✓ user botadmin (sudo không mật khẩu) + khoá"
    else
        echo "   ✗ không tạo được user botadmin trong chroot"
    fi

    echo
    echo "   sshd SAU khi sửa (cấu hình hiệu lực, chạy sshd -T trong chroot):"
    chroot "$MNT" /usr/sbin/sshd -T 2>/dev/null \
        | grep -iE "^(permitrootlogin|pubkeyauthentication|passwordauthentication|authenticationmethods|allowusers|denyusers|allowgroups|authorizedkeysfile)" \
        | sed 's/^/     /' \
        || echo "     (không chạy được sshd -T trong chroot - xem lại bằng grep bên dưới)"
    grep -hE "^PermitRootLogin" "$MNT/etc/ssh/sshd_config.d/00-cuu-ho.conf" "$MNT/etc/ssh/sshd_config" | sed 's/^/     file: /'
    echo "   authorized_keys: $(wc -l < "$MNT/root/.ssh/authorized_keys") khoá"
    cut -c1-45 "$MNT/root/.ssh/authorized_keys" | sed 's/^/     /'
done

sync
for M in /mnt/cuu-ho-*; do [ -d "$M" ] && umount "$M" 2>/dev/null; done
echo
echo "=============================================="
echo " XONG. Vào hPanel TẮT emergency mode để máy khởi động lại."
echo " Nếu ở trên có NHIỀU phân vùng, gửi toàn bộ màn hình này cho người hỗ trợ."
echo "=============================================="
