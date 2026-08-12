#!/bin/bash
# Bật chế độ tự cập nhật từ GitHub. Chạy MỘT LẦN trên droplet:
#
#   bash /opt/antispam/app/deploy/bat-tu-cap-nhat.sh
#
# Sau đó chỉ cần git push trên máy, droplet tự lấy code mới trong vòng 2 phút.
set -eux

REPO=${REPO:-https://github.com/mongdao8386/tg-antispam-bot.git}
APP=/opt/antispam/app

apt-get install -y git

# Biến thư mục app thành bản sao của repo mà KHÔNG đụng .env / antispam.db.
# Cách làm: clone ra chỗ khác rồi chuyển thư mục .git sang, sau đó reset.
if [ ! -d "$APP/.git" ]; then
    rm -rf /tmp/antispam-clone
    sudo -u antispam git clone --quiet "$REPO" /tmp/antispam-clone
    mv /tmp/antispam-clone/.git "$APP/.git"
    rm -rf /tmp/antispam-clone
    chown -R antispam:antispam "$APP"
    sudo -u antispam git -C "$APP" reset --hard --quiet origin/main
fi

# git từ chối chạy trên thư mục thuộc user khác nếu không khai báo.
git config --global --add safe.directory "$APP"

chmod +x "$APP/deploy/tu-cap-nhat.sh"

cat >/etc/systemd/system/antispam-update.service <<'UNIT'
[Unit]
Description=Kiem tra va cap nhat bot chong spam tu GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/antispam/app/deploy/tu-cap-nhat.sh
UNIT

cat >/etc/systemd/system/antispam-update.timer <<'UNIT'
[Unit]
Description=Kiem tra ban moi tren GitHub moi 2 phut

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
# Lech ngau nhien vai giay cho do dinh dung luc GitHub ban
RandomizedDelaySec=20s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now antispam-update.timer

echo
echo "=== Xong. Tu cap nhat da bat ==="
echo "  Kiem tra lich chay : systemctl list-timers antispam-update"
echo "  Xem nhat ky cap nhat: tail -f /var/log/antispam-update.log"
echo "  Cap nhat ngay lap tuc: systemctl start antispam-update"
