#!/bin/bash
# =============================================================================
# Dán TOÀN BỘ file này vào ô "Startup scripts" khi tạo droplet DigitalOcean.
# Khuyến nghị chọn: Ubuntu 24.04 LTS, gói 1GB RAM trở lên.
#
# ⚠️ TUYỆT ĐỐI KHÔNG ghi BOT_TOKEN vào đây.
#    Nội dung ô này hiện nguyên văn trong bảng điều khiển DigitalOcean và bất kỳ
#    tiến trình nào trên droplet cũng đọc được qua metadata (169.254.169.254).
#    Token sẽ được tạo tay ở bước sau, trong file .env với quyền 600.
#
# Script này chỉ dựng sẵn môi trường. Code và .env upload sau.
# =============================================================================
set -eux

export DEBIAN_FRONTEND=noninteractive

timedatectl set-timezone Asia/Ho_Chi_Minh || true

apt-get update
apt-get install -y python3-venv python3-pip ufw unattended-upgrades
# opencv-python-headless cần glib. Ubuntu 24.04 đổi tên gói thành ...0t64.
apt-get install -y libglib2.0-0t64 || apt-get install -y libglib2.0-0

# Swap 1GB: gói droplet nhỏ dễ hết RAM lúc pip biên dịch numpy/opencv.
if [ ! -f /swapfile ]; then
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Tường lửa: chỉ mở SSH. Bot chỉ gọi ra ngoài, không cần mở cổng vào.
ufw allow OpenSSH
ufw --force enable

# Tự cài bản vá bảo mật.
systemctl enable --now unattended-upgrades || true

# Tài khoản riêng cho bot, không đăng nhập được.
id antispam >/dev/null 2>&1 || useradd -r -m -d /opt/antispam -s /usr/sbin/nologin antispam
mkdir -p /opt/antispam/app
chown -R antispam:antispam /opt/antispam

# Môi trường ảo Python.
sudo -u antispam python3 -m venv /opt/antispam/venv
sudo -u antispam /opt/antispam/venv/bin/pip install --upgrade pip wheel
sudo -u antispam /opt/antispam/venv/bin/pip install \
    'python-telegram-bot[job-queue,rate-limiter]>=21.6,<23' \
    'python-dotenv>=1.0.1' \
    'opencv-python-headless>=4.9'

# Dịch vụ systemd: tự chạy lại khi sập, tự bật khi khởi động lại máy.
cat >/etc/systemd/system/antispam.service <<'UNIT'
[Unit]
Description=Telegram anti-spam bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=antispam
WorkingDirectory=/opt/antispam/app
# Dấu - ở đầu: thiếu file thì bỏ qua, không làm dịch vụ chết ngay.
# Bản thân bot cũng tự đọc .env bằng python-dotenv nên vẫn chạy đúng.
EnvironmentFile=-/opt/antispam/app/.env
ExecStart=/opt/antispam/venv/bin/python -m antispam_bot
Restart=always
RestartSec=10

# Giới hạn quyền: nếu bot bị lợi dụng thì cũng không đụng được phần còn lại.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
ReadWritePaths=/opt/antispam/app

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
# CỐ Ý chưa bật: code và .env chưa có, bật bây giờ sẽ lặp lỗi.
# Bật ở bước 4 sau khi upload xong.

echo "=== Môi trường đã sẵn sàng. Bước tiếp theo: upload code + .env ===" \
    > /root/BUOC-TIEP-THEO.txt
