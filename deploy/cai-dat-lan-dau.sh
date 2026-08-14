#!/bin/bash
# =============================================================================
#  CÀI ĐẶT LẦN ĐẦU — chạy MỘT LẦN trên droplet mới.
#
#  Hai cách dùng, chọn một:
#
#  A. Lúc tạo droplet: dán TOÀN BỘ file này vào ô "Startup scripts".
#     Chọn Ubuntu 24.04 LTS, gói 1GB RAM trở lên.
#
#  B. Droplet đã có sẵn: SSH vào rồi chạy
#        curl -fsSL https://raw.githubusercontent.com/mongdao8386/tg-antispam-bot/main/deploy/cai-dat-lan-dau.sh | bash
#
#  Script làm trọn gói: cài thư viện, tải code từ GitHub, dựng dịch vụ, bật tự
#  cập nhật. Xong chỉ còn một việc duy nhất là tạo file .env chứa token.
#
#  ⚠️ KHÔNG ghi BOT_TOKEN vào file này. Nội dung ô "Startup scripts" hiện
#     nguyên văn trong bảng điều khiển DigitalOcean và đọc được từ metadata
#     của droplet. Token sẽ tạo tay ở bước cuối, với quyền 600.
# =============================================================================
set -eu

REPO="${REPO:-https://github.com/mongdao8386/tg-antispam-bot.git}"
APP=/opt/antispam/app
VENV=/opt/antispam/venv
NGUOI=antispam

echo "=============================================="
echo " Cài đặt bot chống spam Telegram"
echo "=============================================="

# --- 1. Gói hệ thống -------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
timedatectl set-timezone Asia/Ho_Chi_Minh || true

echo "[1/7] Cài gói hệ thống..."
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip git ufw unattended-upgrades
# opencv cần glib; Ubuntu 24.04 đổi tên gói thành ...0t64 nên thử cả hai.
apt-get install -y -qq libglib2.0-0t64 || apt-get install -y -qq libglib2.0-0
# OCR: thiếu gói -vie thì đọc tiếng Việt có dấu sai bét.
apt-get install -y -qq tesseract-ocr tesseract-ocr-vie

# --- 2. Swap ---------------------------------------------------------------
# Gói droplet 1GB dễ hết RAM khi pip cài numpy/opencv và khi Tesseract chạy.
if [ ! -f /swapfile ]; then
    echo "[2/7] Tạo swap 1GB..."
    fallocate -l 1G /swapfile
    chmod 600 /swapfile
    mkswap -q /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
    echo "[2/7] Swap đã có, bỏ qua."
fi

# --- 3. Tường lửa ----------------------------------------------------------
# Bot chỉ gọi ra ngoài, không cần mở cổng vào. Bảng web nghe ở 127.0.0.1.
echo "[3/7] Bật tường lửa (chỉ mở SSH)..."
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

# --- 4. Tài khoản riêng ----------------------------------------------------
echo "[4/7] Tạo tài khoản chạy bot..."
id "$NGUOI" >/dev/null 2>&1 || useradd -r -m -d /opt/antispam -s /usr/sbin/nologin "$NGUOI"

# --- 5. Lấy code từ GitHub -------------------------------------------------
echo "[5/7] Tải code từ GitHub..."
mkdir -p "$APP"
chown -R "$NGUOI:$NGUOI" /opt/antispam
if [ -d "$APP/.git" ]; then
    sudo -u "$NGUOI" git -C "$APP" fetch --quiet origin main
    sudo -u "$NGUOI" git -C "$APP" reset --hard --quiet origin/main
else
    # Clone ra chỗ khác rồi chuyển .git sang, để KHÔNG đụng .env và
    # antispam.db nếu thư mục đã có sẵn dữ liệu từ lần cài trước.
    rm -rf /tmp/antispam-clone
    sudo -u "$NGUOI" git clone --quiet "$REPO" /tmp/antispam-clone
    mv /tmp/antispam-clone/.git "$APP/.git"
    rm -rf /tmp/antispam-clone
    chown -R "$NGUOI:$NGUOI" "$APP"
    sudo -u "$NGUOI" git -C "$APP" reset --hard --quiet origin/main
fi
# git từ chối chạy trên thư mục thuộc user khác nếu không khai báo.
git config --global --add safe.directory "$APP"

# --- 6. Môi trường Python --------------------------------------------------
echo "[6/7] Cài thư viện Python (mất vài phút)..."
[ -d "$VENV" ] || sudo -u "$NGUOI" python3 -m venv "$VENV"
sudo -u "$NGUOI" "$VENV/bin/pip" install -q --upgrade pip wheel
sudo -u "$NGUOI" "$VENV/bin/pip" install -q -r "$APP/requirements.txt"

# --- 7. Dịch vụ + tự cập nhật ---------------------------------------------
echo "[7/7] Dựng dịch vụ và bật tự cập nhật..."

cat >/etc/systemd/system/antispam.service <<'UNIT'
[Unit]
Description=Bot chong spam Telegram
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=antispam
WorkingDirectory=/opt/antispam/app
EnvironmentFile=-/opt/antispam/app/.env
ExecStart=/opt/antispam/venv/bin/python -m antispam_bot
Restart=always
RestartSec=10

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

chmod +x "$APP/deploy/tu-cap-nhat.sh"

cat >/etc/systemd/system/antispam-update.service <<'UNIT'
[Unit]
Description=Kiem tra va cap nhat bot tu GitHub
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
RandomizedDelaySec=20s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable antispam-update.timer >/dev/null
systemctl start antispam-update.timer

# Chưa bật dịch vụ bot: còn thiếu .env, bật bây giờ chỉ lặp lỗi.
# Viết dạng if chứ KHÔNG dùng `[ -f ... ] && CO_ENV=1`: với set -e, khi file
# chưa có thì cả biểu thức trả về mã lỗi và script thoát ngay tại đây.
CO_ENV=0
if [ -f "$APP/.env" ]; then
    CO_ENV=1
fi

cat >/root/BUOC-TIEP-THEO.txt <<'HD'
==============================================================
 CÀI XONG. CÒN ĐÚNG MỘT BƯỚC: TẠO FILE .env
==============================================================

Trên máy Windows của bạn, tại thư mục TG-bots, chạy:

    scp .env root@<IP-DROPLET>:/opt/antispam/app/.env

Rồi quay lại đây chạy:

    chmod 600 /opt/antispam/app/.env
    chown -R antispam:antispam /opt/antispam/app
    systemctl enable --now antispam
    systemctl status antispam

Muốn giữ dữ liệu cũ (từ cấm, acc seeding, nhóm đang quản lý) thì chép
thêm database — NHỚ TẮT BOT Ở MÁY WINDOWS TRƯỚC để file không ghi dở:

    scp antispam.db root@<IP-DROPLET>:/opt/antispam/app/

--------------------------------------------------------------
 LỆNH HAY DÙNG
--------------------------------------------------------------
  Xem log bot        : journalctl -u antispam -f
  Khởi động lại      : systemctl restart antispam
  Xem log cập nhật   : tail -f /var/log/antispam-update.log
  Cập nhật ngay      : systemctl start antispam-update
  Xem lịch cập nhật  : systemctl list-timers antispam-update

Từ giờ chỉ cần git push trên máy, droplet tự lấy code mới trong 2 phút.
==============================================================
HD

echo
echo "=============================================="
echo " XONG PHẦN CÀI ĐẶT"
echo "=============================================="
if [ "$CO_ENV" = "1" ]; then
    chmod 600 "$APP/.env"
    chown -R "$NGUOI:$NGUOI" "$APP"
    systemctl enable --now antispam
    sleep 3
    echo " Đã có .env sẵn -> bot đang chạy."
    systemctl is-active antispam && echo " Trạng thái: ĐANG CHẠY" || {
        echo " Bot chưa lên. Xem lỗi: journalctl -u antispam -n 40"
    }
else
    echo
    echo " Còn MỘT bước: đưa file .env lên (chứa BOT_TOKEN)."
    echo
    echo " Từ máy Windows, trong thư mục TG-bots:"
    echo "     scp .env root@\$(hostname -I | awk '{print \$1}'):/opt/antispam/app/.env"
    echo
    echo " Rồi chạy trên droplet:"
    echo "     chmod 600 /opt/antispam/app/.env"
    echo "     chown -R antispam:antispam /opt/antispam/app"
    echo "     systemctl enable --now antispam"
    echo
    echo " Hướng dẫn đầy đủ đã lưu ở: /root/BUOC-TIEP-THEO.txt"
fi
echo "=============================================="
