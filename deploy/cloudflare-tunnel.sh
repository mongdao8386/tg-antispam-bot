#!/bin/bash
# =============================================================================
#  Mở bảng điều khiển web ra Internet qua Cloudflare Tunnel.
#
#  Chạy trên DROPLET:  bash /opt/antispam/app/deploy/cloudflare-tunnel.sh
#
#  Vì sao dùng Tunnel thay vì mở cổng:
#    - Không mở cổng nào ra Internet. Tường lửa vẫn chỉ cho SSH.
#    - Có HTTPS sẵn, khỏi lo chứng chỉ.
#    - Cloudflare đứng trước chặn quét/dò, droplet không lộ IP.
#
#  Chế độ nhanh (mặc định): dùng địa chỉ ngẫu nhiên *.trycloudflare.com,
#  KHÔNG cần tài khoản Cloudflare. Địa chỉ đổi mỗi lần khởi động lại - script
#  tự ghi địa chỉ mới vào database nên lệnh /web luôn ra link đúng.
#
#  Muốn địa chỉ cố định (vd bot.tenmien.com) thì cần tài khoản + tên miền đã
#  trỏ về Cloudflare, xem phần hướng dẫn in ra ở cuối.
# =============================================================================
set -eu

APP=/opt/antispam/app
DB="$APP/antispam.db"
CONG="${WEB_PORT:-8080}"

echo "=============================================="
echo " Mở bảng điều khiển qua Cloudflare Tunnel"
echo "=============================================="

# --- 1. Bảng web phải đang bật ---------------------------------------------
if ! grep -qE '^WEB_ENABLED\s*=\s*true' "$APP/.env" 2>/dev/null; then
    echo
    echo " [DỪNG] Bảng web đang tắt."
    echo " Mở $APP/.env, sửa thành:  WEB_ENABLED=true"
    echo " Rồi chạy: systemctl restart antispam && bash $0"
    exit 1
fi

# --- 2. Cài cloudflared ----------------------------------------------------
if ! command -v cloudflared >/dev/null 2>&1; then
    echo "[1/4] Cài cloudflared..."
    KIEN_TRUC=$(dpkg --print-architecture)
    curl -fsSL -o /tmp/cloudflared.deb \
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${KIEN_TRUC}.deb"
    dpkg -i /tmp/cloudflared.deb >/dev/null
    rm -f /tmp/cloudflared.deb
else
    echo "[1/4] cloudflared đã có."
fi

# --- 3. Script bọc: lấy địa chỉ rồi ghi vào database ------------------------
echo "[2/4] Tạo script chạy tunnel..."
cat >/usr/local/bin/antispam-tunnel <<CHAY
#!/bin/bash
# Chạy tunnel, đọc địa chỉ Cloudflare cấp, ghi vào database để lệnh /web
# sinh đúng link. Chế độ nhanh đổi địa chỉ mỗi lần chạy nên phải làm vậy.
set -u
NHAT_KY=/var/log/antispam-tunnel.log
: > "\$NHAT_KY"

cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${CONG}" \\
    >>"\$NHAT_KY" 2>&1 &
PID=\$!

# Chờ tối đa 60 giây để Cloudflare cấp địa chỉ.
DIA_CHI=""
for _ in \$(seq 1 60); do
    DIA_CHI=\$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "\$NHAT_KY" | head -1)
    [ -n "\$DIA_CHI" ] && break
    sleep 1
done

if [ -n "\$DIA_CHI" ]; then
    echo "Địa chỉ bảng điều khiển: \$DIA_CHI" >> "\$NHAT_KY"
    # Ghi vào bảng bot_settings. Bot đọc khoá này trước cfg.web_url nên
    # KHÔNG cần khởi động lại bot.
    sqlite3 "$DB" \\
      "INSERT INTO bot_settings(key,value) VALUES('web_url','\$DIA_CHI')
       ON CONFLICT(key) DO UPDATE SET value=excluded.value;" 2>/dev/null \\
      || echo "Không ghi được địa chỉ vào database" >> "\$NHAT_KY"
else
    echo "Hết 60 giây mà Cloudflare chưa cấp địa chỉ." >> "\$NHAT_KY"
fi

wait \$PID
CHAY
chmod +x /usr/local/bin/antispam-tunnel

apt-get install -y -qq sqlite3 >/dev/null 2>&1 || true

# --- 4. Dịch vụ systemd ----------------------------------------------------
echo "[3/4] Dựng dịch vụ..."
cat >/etc/systemd/system/antispam-tunnel.service <<'UNIT'
[Unit]
Description=Cloudflare Tunnel cho bang dieu khien chong spam
After=network-online.target antispam.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/antispam-tunnel
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable antispam-tunnel >/dev/null
systemctl restart antispam-tunnel

# --- 5. Chờ và báo địa chỉ -------------------------------------------------
echo "[4/4] Chờ Cloudflare cấp địa chỉ..."
DIA_CHI=""
for _ in $(seq 1 60); do
    if [ -f /var/log/antispam-tunnel.log ]; then
        DIA_CHI=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
                  /var/log/antispam-tunnel.log | head -1 || true)
        [ -n "$DIA_CHI" ] && break
    fi
    sleep 1
done

echo
echo "=============================================="
if [ -n "$DIA_CHI" ]; then
    echo " XONG"
    echo "=============================================="
    echo
    echo " Địa chỉ bảng điều khiển:"
    echo "     $DIA_CHI"
    echo
    echo " Đã ghi vào database, lệnh /web sẽ tự dùng địa chỉ này."
    echo " Vào Telegram, nhắn riêng cho bot: /web"
    echo
    echo " Lưu ý: địa chỉ này ĐỔI mỗi lần tunnel khởi động lại, nhưng bot"
    echo " tự cập nhật nên bạn không phải làm gì."
else
    echo " CHƯA LẤY ĐƯỢC ĐỊA CHỈ"
    echo "=============================================="
    echo " Xem lỗi: tail -30 /var/log/antispam-tunnel.log"
fi
echo
echo "----------------------------------------------"
echo " MUỐN ĐỊA CHỈ CỐ ĐỊNH (vd bot.tenmien.com)?"
echo "----------------------------------------------"
echo " Cần tài khoản Cloudflare + tên miền đã trỏ về Cloudflare:"
echo
echo "   cloudflared tunnel login"
echo "   cloudflared tunnel create antispam"
echo "   cloudflared tunnel route dns antispam bot.tenmien.com"
echo "   cloudflared tunnel --url http://127.0.0.1:${CONG} run antispam"
echo
echo " Rồi đặt WEB_URL=https://bot.tenmien.com trong .env"
echo " và tắt tunnel nhanh: systemctl disable --now antispam-tunnel"
echo
echo " Nên bật thêm Cloudflare Access (Zero Trust) cho địa chỉ đó -"
echo " thêm một lớp đăng nhập nữa trước khi tới bảng điều khiển."
echo "=============================================="
