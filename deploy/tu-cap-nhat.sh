#!/bin/bash
# Kéo code mới từ GitHub rồi khởi động lại bot. Chạy trên VPS.
#
# Điểm quan trọng: nếu code mới lỗi, script TỰ LÙI về bản cũ và chạy lại.
# Không có bước này thì một commit hỏng sẽ làm bot chết im cho tới khi
# bạn tình cờ phát hiện.
#
# Được gọi tự động 2 phút một lần bởi antispam-update.timer.
set -u

APP=/opt/antispam/app
LOG=/var/log/antispam-update.log

exec >>"$LOG" 2>&1
echo "--- $(date '+%F %T') ---"

cd "$APP" || { echo "Không vào được $APP"; exit 1; }

# Chạy git dưới quyền user antispam để không tạo file thuộc root.
git_as() { sudo -u antispam git -C "$APP" "$@"; }

if ! git_as fetch --quiet origin main; then
    echo "Không kết nối được GitHub, bỏ qua lượt này."
    exit 0
fi

CU=$(git_as rev-parse HEAD)
MOI=$(git_as rev-parse origin/main)

if [ "$CU" = "$MOI" ]; then
    exit 0   # không có gì mới
fi

echo "Có bản mới: ${CU:0:7} -> ${MOI:0:7}"
git_as log --oneline "${CU}..${MOI}" | sed 's/^/    /'

# reset --hard cho sạch, tránh xung đột nếu file trên VPS bị sửa tay.
# Không đụng tới file chưa theo dõi (.env, antispam.db) - chúng nằm trong
# .gitignore nên vẫn nguyên.
git_as reset --hard --quiet origin/main || { echo "reset thất bại"; exit 1; }
# Git trên Windows commit file .sh với mode 644: lần reset --hard đầu tiên tước
# mất +x của CHÍNH script này, và tự cập nhật chết im lặng (systemd 203/EXEC)
# từ đó về sau - đã xảy ra thật, VPS đứng ở bản cũ 13 ngày. Unit giờ chạy qua
# /bin/bash nên không cần +x nữa, nhưng vẫn cấp lại cho chắc.
chmod +x "$APP"/deploy/*.sh 2>/dev/null || true

# Thư viện có thể đổi theo commit.
sudo -u antispam /opt/antispam/venv/bin/pip install -q -r requirements.txt

# KIỂM TRA TRƯỚC KHI KHỞI ĐỘNG LẠI: nạp thử module. Bắt được lỗi cú pháp,
# thiếu import, thiếu thư viện - tức là phần lớn commit hỏng.
if sudo -u antispam /opt/antispam/venv/bin/python -c "import antispam_bot.bot" 2>&1; then
    systemctl restart antispam
    sleep 3
    if systemctl is-active --quiet antispam; then
        echo "Đã cập nhật lên ${MOI:0:7} và chạy bình thường."
        exit 0
    fi
    echo "Bot không lên được sau khi cập nhật."
else
    echo "Code mới lỗi khi nạp thử."
fi

# Tới đây là hỏng: lùi lại bản cũ.
echo "LÙI VỀ ${CU:0:7}"
git_as reset --hard --quiet "$CU"
sudo -u antispam /opt/antispam/venv/bin/pip install -q -r requirements.txt
systemctl restart antispam
sleep 2
if systemctl is-active --quiet antispam; then
    echo "Đã lùi về bản cũ, bot chạy lại bình thường. Sửa commit ${MOI:0:7} rồi đẩy lại."
else
    echo "NGHIÊM TRỌNG: lùi rồi mà bot vẫn không chạy. Xem: journalctl -u antispam -n 50"
fi
exit 1
