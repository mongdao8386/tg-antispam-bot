#!/bin/bash
# =============================================================================
#  CHẨN ĐOÁN vì sao SSH bằng khoá vẫn bị từ chối - chạy trên chính VPS (console).
#  Chỉ đọc, không sửa gì. In ra để gửi cho người hỗ trợ.
#
#  Dùng:  curl -fsSL https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/chan-doan.sh | bash
# =============================================================================
echo "=============================================="
echo " 1. sshd đang nghe ở đâu, tiến trình nào"
echo "=============================================="
ss -tlnp 2>/dev/null | grep -E ':22 |:22$' || echo "  (không thấy gì nghe cổng 22!)"
systemctl is-active ssh sshd 2>/dev/null | paste -sd' ' | sed 's/^/  ssh\/sshd: /'
/usr/sbin/sshd -V 2>&1 | head -1 | sed 's/^/  /'

echo
echo "=============================================="
echo " 2. Cấu hình sshd HIỆU LỰC (sshd -T)"
echo "=============================================="
/usr/sbin/sshd -T 2>&1 | grep -iE "^(permitrootlogin|pubkeyauthentication|passwordauthentication|authorizedkeysfile|authorizedkeyscommand|authorizedkeyscommanduser|allowusers|denyusers|allowgroups|denygroups|authenticationmethods|usepam|strictmodes|port |listenaddress|include|match)" | sed 's/^/  /'
echo "  --- các file cấu hình ---"
ls -la /etc/ssh/sshd_config /etc/ssh/sshd_config.d/ 2>/dev/null | sed 's/^/  /'
grep -nE "^\s*Include" /etc/ssh/sshd_config | sed 's/^/  Include tại dòng: /'

echo
echo "=============================================="
echo " 3. Khoá và quyền thư mục"
echo "=============================================="
for U in root botadmin; do
    H=$(getent passwd "$U" | cut -d: -f6)
    echo "  [$U] home=$H  shell=$(getent passwd "$U" | cut -d: -f7)  shadow=$(grep "^$U:" /etc/shadow | cut -d: -f2 | cut -c1-3)..."
    ls -ld "$H" "$H/.ssh" "$H/.ssh/authorized_keys" 2>&1 | sed 's/^/     /'
    cut -c1-45 "$H/.ssh/authorized_keys" 2>/dev/null | sed 's/^/     key: /'
done

echo
echo "=============================================="
echo " 4. Vì sao từ chối - log của sshd (20 dòng cuối)"
echo "=============================================="
journalctl -u ssh -u sshd -n 25 --no-pager 2>/dev/null | grep -viE "Received disconnect|Disconnected from|Connection closed|Connection reset" | tail -15 | sed 's/^/  /'
[ -f /var/log/auth.log ] && grep -iE "sshd" /var/log/auth.log | tail -8 | sed 's/^/  /'

echo
echo "=============================================="
echo " 4b. PAM - thứ hay chặn SAU khi khoá đã đúng"
echo "=============================================="
echo "  /etc/pam.d/sshd (dòng có tác dụng):"
grep -vE '^\s*(#|$)' /etc/pam.d/sshd 2>/dev/null | sed 's/^/     /'
echo "  /etc/pam.d/common-account + common-auth (dòng lạ):"
grep -hE "pam_(access|listfile|succeed_if|nologin|faillock|tally|time|group|shells)" /etc/pam.d/common-account /etc/pam.d/common-auth /etc/pam.d/common-session 2>/dev/null | sed 's/^/     /'
echo "  /etc/security/access.conf (dòng có tác dụng):"
grep -vE '^\s*(#|$)' /etc/security/access.conf 2>/dev/null | sed 's/^/     /' || echo "     (trống)"
[ -e /etc/nologin ] && echo "  !!! /etc/nologin TỒN TẠI - chặn mọi user không phải root: $(head -c 80 /etc/nologin)"
command -v faillock >/dev/null && { echo "  faillock:"; faillock --user root 2>/dev/null | tail -3 | sed 's/^/     /'; faillock --user botadmin 2>/dev/null | tail -3 | sed 's/^/     /'; }
echo "  /etc/ssh/sshd_config dòng UsePAM/Subsystem/ForceCommand:"
grep -nE "^\s*(UsePAM|ForceCommand|ChrootDirectory|Banner)" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null | sed 's/^/     /'

echo
echo "=============================================="
echo " 5. Chặn IP / bảo vệ"
echo "=============================================="
systemctl is-active fail2ban 2>/dev/null | sed 's/^/  fail2ban: /'
fail2ban-client status sshd 2>/dev/null | grep -iE "banned" | sed 's/^/  /'
command -v csf >/dev/null && echo "  csf: có cài"
ufw status 2>/dev/null | head -1 | sed 's/^/  ufw: /'
iptables -S INPUT 2>/dev/null | grep -iE "203.77|DROP|REJECT" | head -5 | sed 's/^/  iptables: /'

echo
echo "=============================================="
echo " 6. Dịch vụ khác đang chạy (website?)"
echo "=============================================="
ss -tlnp 2>/dev/null | awk 'NR>1{print $4, $6}' | sed 's/users:(("//; s/",pid.*//' | sort -u | head -12 | sed 's/^/  /'
command -v docker >/dev/null && docker ps --format '  docker: {{.Names}}  {{.Ports}}' 2>/dev/null
echo "=============================================="
echo " HẾT - chụp toàn bộ màn hình này."
echo "=============================================="
