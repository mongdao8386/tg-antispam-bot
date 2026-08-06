# Bot chống spam Telegram (chạy im lặng)

Bot tự động **xoá tin nhắn spam và xử lý người gửi mà không thông báo gì trong nhóm**.
Không có tin "đã ban X", không có cảnh báo, không có phản hồi — thành viên bình thường
gần như không nhận ra bot tồn tại. Mọi thứ chỉ được ghi vào console và (tuỳ chọn) một
kênh log riêng.

## Bot bắt được gì

| Dấu hiệu | Xử lý |
|---|---|
| Tin nhắn chuyển tiếp (forward) từ người/kênh khác | chặn cứng (bật/tắt được) |
| Tin gửi dưới danh nghĩa kênh lạ (`sender_chat`) | chặn cứng, chặn luôn cả kênh đó |
| Link ngoài whitelist | chặn cứng (bật/tắt được) |
| Link rút gọn (bit.ly, cutt.ly…), tên miền rác (.xyz, .top, .icu…) | cộng điểm |
| Link mời vào nhóm riêng `t.me/+…`, `t.me/joinchat/…` | cộng điểm |
| Link viết né bộ lọc: `abc (dot) com`, `abc [.] com` | cộng điểm |
| **Ảnh chứa mã QR** — giải mã rồi soi nội dung | xem mục riêng bên dưới |
| Từ khoá lừa đảo tiếng Việt & tiếng Anh (~150 cụm) | cộng điểm theo mức độ |
| Địa chỉ ví crypto, số tài khoản ngân hàng, số điện thoại | cộng điểm |
| Ký tự vô hình, chữ Cyrillic giả Latin, leetspeak, `l.ừ.a đ.ả.o` | cộng điểm |
| Lạm dụng emoji, viết hoa toàn bộ, tin có nút bấm | cộng điểm |
| Người mới vào nhóm / đã từng vi phạm | hạ ngưỡng, dễ bị chặn hơn |

Từ khoá phủ các nhóm lừa đảo phổ biến: việc nhẹ lương cao, tuyển CTV, cờ bạc/nhà cái,
đầu tư "cam kết lợi nhuận", airdrop crypto, vay nặng lãi, làm bằng giả, chiếm OTP,
mua bán tài khoản ngân hàng, nội dung người lớn.

**Chấm điểm thay vì chặn cứng theo từ khoá** — một từ nhạy cảm đơn lẻ không đủ để bị
xử lý, nên câu như *"Lừa đảo nhiều quá, mọi người cẩn thận nhé"* vẫn được cho qua.

## Quét mã QR trong ảnh

Bot tải ảnh về, giải mã QR bằng OpenCV, rồi đưa nội dung giải ra qua **đúng bộ luật
link và từ khoá** như chữ trong tin nhắn. Ngoài ra có luật riêng cho QR:

| Nội dung QR | Xử lý |
|---|---|
| QR chuyển khoản ngân hàng (VietQR/EMVCo) | chặn cứng |
| QR chứa ví crypto (`bitcoin:`, `ethereum:`, địa chỉ ví) | chặn cứng |
| QR dẫn tới link ngoài whitelist | chặn cứng |
| QR mời vào nhóm/kênh Telegram (`t.me/+…`, `tg://`) | chặn cứng |
| Ảnh có QR nhưng không đọc được nội dung (mờ, chụp nghiêng) | +3 điểm |
| Ảnh có QR nói chung | +2 điểm; thành viên mới thêm +2 → bị chặn |

Bot xử lý ảnh (`photo`), file ảnh (`document` mime `image/*`) và sticker tĩnh. Ảnh quá
mờ hoặc QR bị bóp méo nhiều thì có thể không giải được — nhưng chính việc *dò ra khung
QR mà không đọc nổi* đã là tín hiệu đáng ngờ và vẫn được cộng điểm.

QR vô hại vẫn qua được: QR wifi, QR trỏ tới domain trong whitelist đều dưới ngưỡng khi
người gửi là thành viên cũ.

**Cần cài thêm OpenCV** (`opencv-python-headless`, đã nằm trong `requirements.txt`).
Nếu không nạp được, bot vẫn chạy bình thường và chỉ ghi một cảnh báo lúc khởi động —
mọi luật khác không bị ảnh hưởng. Tắt hẳn bằng `SCAN_QR=false`.

Bot ưu tiên dùng `QRCodeDetectorAruco` (OpenCV ≥ 4.7) vì bản `QRCodeDetector` cổ điển
bỏ sót QR ở ảnh nhỏ hoặc tương phản thấp — đúng kiểu ảnh spam hay gặp. Ảnh nhỏ được
phóng to trước khi dò, ảnh quá lớn thu nhỏ cho nhanh, và có một lượt thử lại sau khi
tăng tương phản (Otsu) cho ảnh mờ.

> **Lưu ý cho Windows có Smart App Control:** lần import đầu tiên numpy/OpenCV có thể
> bị chặn (`DLL load failed ... Application Control policy has blocked this file`).
> Chạy lại thêm một lần nữa là được — Windows kiểm tra danh tiếng đám mây xong sẽ cho
> phép. Log lúc khởi động cho biết trạng thái: `Quét mã QR trong ảnh: BẬT` hoặc `TẮT`.

## Tự xoá tin nhắn dịch vụ

Những dòng chữ xám do Telegram tự sinh (*"X đã tham gia nhóm"*, *"X đã rời nhóm"*,
*"X đã ghim một tin nhắn"*…) được bot xoá luôn để nhóm sạch. Cấu hình bằng
`DELETE_SERVICE_MESSAGES` — liệt kê cách nhau bằng dấu phẩy, hoặc `all` / `none`:

| Giá trị | Xoá gì |
|---|---|
| `join` | "X đã tham gia nhóm" |
| `leave` | "X đã rời nhóm" |
| `pin` | "X đã ghim một tin nhắn" — tin vẫn được ghim, chỉ mất thông báo |
| `title` | đổi tên nhóm |
| `photo` | đổi / xoá ảnh nhóm |
| `videochat` | bắt đầu / kết thúc cuộc gọi nhóm |
| `forum` | tạo / sửa / đóng chủ đề trong nhóm forum |
| `other` | boost, giveaway, hẹn giờ tự xoá, chia sẻ danh bạ… |

Mặc định `join,leave,pin`. Bot vẫn ghi mốc thời gian gia nhập **trước khi** xoá tin, nên
luật "thành viên mới" không bị ảnh hưởng.

## Người dùng thường tra ID của mình

Ai cũng nhắn riêng cho bot rồi bấm **Start** được — bot trả về ID Telegram của họ và
giữ tin nhắn đó lại để copy. Gõ `/id` bất cứ lúc nào để xem lại.

Trong nhóm, `/id` cũng dùng được cho mọi người nhưng **cả lệnh lẫn phản hồi tự xoá sau
20 giây**, nên không làm ồn.

Menu lệnh được phân quyền để nhóm luôn im lặng: thành viên thường trong nhóm **không
thấy lệnh nào**, chat riêng chỉ thấy `/id`, còn admin nhóm thấy đủ bộ lệnh quản trị.

## Cài đặt

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copy `.env.example` thành `.env` rồi điền `BOT_TOKEN` lấy từ [@BotFather](https://t.me/BotFather).

## Chạy

```bash
.venv\Scripts\python.exe -m antispam_bot
```

## Thêm bot vào nhóm

1. Thêm bot vào nhóm, **cấp quyền admin** với hai quyền: *Delete messages* và *Ban users*.
2. Trong @BotFather chạy `/setprivacy` → chọn bot → **Disable**. Không tắt privacy mode
   thì bot chỉ nhìn thấy lệnh, không đọc được tin nhắn thường và sẽ không lọc được gì.
3. Gõ `/id` trong nhóm để lấy `chat_id` và `user_id` — điền vào `OWNER_IDS`, `LOG_CHAT_ID`.

## Cấu hình

Toàn bộ nằm trong `.env` (xem mô tả từng dòng trong `.env.example`). Vài mục quan trọng:

- `ACTION` — `ban` (mặc định) | `mute` | `delete` | `report`.
  **Khuyến nghị chạy `report` 1–2 ngày đầu**: bot không đụng gì cả, chỉ ghi log để bạn
  xem nó *sẽ* xử lý những ai. Xem log ổn rồi mới chuyển sang `ban`.
- `SPAM_THRESHOLD` (mặc định 5) và `NEW_MEMBER_THRESHOLD` (mặc định 3) — hạ xuống thì gắt hơn.
- `BLOCK_FORWARDS` / `BLOCK_LINKS` — chặn cứng forward và link lạ. Nếu nhóm bạn hay
  chia sẻ link, đặt `BLOCK_LINKS_NEW_ONLY=true` để chỉ chặn với thành viên mới.
- `WHITELIST_DOMAINS` — các domain được phép. Áp dụng cho cả link trong QR.
- `SCAN_QR` / `QR_MAX_BYTES` — bật/tắt quét QR và giới hạn dung lượng ảnh tải về.
- `DELETE_SERVICE_MESSAGES` — tin dịch vụ nào cần tự xoá (xem mục riêng ở trên).
- `LOG_CHAT_ID` — kênh/nhóm riêng để nhận log chi tiết từng lượt xử lý.

Ai **không bao giờ** bị đụng tới: admin nhóm, `OWNER_IDS`, người được `/trust`,
bot khác, admin ẩn danh, và bài đăng tự động từ kênh liên kết.

## Lệnh quản trị

Chỉ admin dùng được. **Mọi phản hồi tự xoá sau 20 giây** cùng với lệnh gốc, để nhóm
luôn sạch. Người không phải admin gõ lệnh thì lệnh bị xoá luôn, không có phản hồi.

| Lệnh | Tác dụng |
|---|---|
| `/status` | Xem cấu hình đang chạy + thống kê đã xử lý bao nhiêu |
| `/check` (reply) | Chấm điểm thử một tin nhắn mà không xử lý — dùng để chỉnh ngưỡng. Với ảnh, hiện luôn nội dung QR giải được |
| `/trust` (reply) | Đánh dấu người này tin cậy, bot bỏ qua hoàn toàn |
| `/unban <id>` hoặc reply | Gỡ chặn và xoá lịch sử vi phạm |
| `/whitelist add\|del\|list <domain>` | Whitelist domain riêng cho nhóm này |
| `/id` | Xem `chat_id` / `user_id` — **mọi người đều dùng được**, không riêng admin |
| `/start` | Chỉ trong chat riêng: giới thiệu bot + hiện ID của người dùng |

## Kiểm thử

```bash
.venv\Scripts\python.exe tests\test_detector.py
```

In ra điểm của từng mẫu spam/tin sạch. Khi bạn thêm từ khoá mới vào
`antispam_bot/detector.py`, thêm mẫu vào `tests/test_detector.py` rồi chạy lại để chắc
chắn không chặn oan tin nhắn bình thường.

```bash
.venv\Scripts\python.exe tests\test_qrscan.py
```

Kiểm thử QR đầu-cuối: tự tạo ảnh QR, giải mã, rồi chấm điểm. Tự bỏ qua nếu máy không
có OpenCV.

Lần chạy đầu mất khoảng 5–6 giây để biên dịch `.pyc`, các lần sau chỉ hơn 1 giây.
Đừng bấm Ctrl+C khi thấy nó "đứng im" lúc khởi động.

## Cấu trúc

```
antispam_bot/
  config.py     đọc .env
  normalize.py  chuẩn hoá text: bỏ dấu, ký tự ẩn, homoglyph, leetspeak
  detector.py   từ khoá + regex + chấm điểm  ← chỉnh ở đây khi muốn thêm luật
  qrscan.py     giải mã QR trong ảnh (OpenCV, tuỳ chọn)
  storage.py    SQLite: thành viên mới, lịch sử vi phạm, whitelist theo nhóm
  bot.py        handler Telegram, thực thi hình phạt, lệnh quản trị
  __main__.py   khởi chạy
tests/
  test_detector.py
```

## Bot chạy nhưng không thấy làm gì?

Theo thứ tự hay gặp nhất:

1. **Bot chưa là admin, hoặc thiếu quyền.** Không có quyền thì bot im lặng theo đúng
   nghĩa đen — không xoá được tin nào, không ban được ai. Bot tự phát hiện và ghi log
   đỏ ngay khi nhận tin đầu tiên trong nhóm, hoặc gõ `/status` trong nhóm để xem.
2. **Chưa tắt privacy mode** (`/setprivacy` → Disable ở @BotFather). Bot vẫn thấy tin
   dịch vụ (vào/rời nhóm) nhưng **không đọc được tin nhắn thường**, nên chỉ xoá được
   thông báo vào/rời mà không lọc được spam. Sau khi tắt phải **kick bot ra rồi thêm
   lại** thì mới có hiệu lực.
3. **Bạn đang thử bằng tài khoản admin.** Admin nhóm và `OWNER_IDS` luôn được bỏ qua —
   hãy thử bằng một tài khoản thường.
4. **Tin nhắn thử chưa đủ điểm.** Gõ mỗi chữ "lừa đảo" thì **0 điểm** — đó là chủ ý,
   để mọi người còn cảnh báo nhau về lừa đảo. Muốn thử thật, dùng một tin giống spam
   thật, ví dụ:

   > Tuyển CTV online làm việc tại nhà, thu nhập 500k/ngày, không cần kinh nghiệm.
   > Inbox zalo 0912345678

   Hoặc reply `/check` vào tin nhắn bất kỳ để xem nó được bao nhiêu điểm và vì sao.

## Lưu ý

- `ACTION=ban` dùng `revoke_messages=True`, tức là **xoá luôn toàn bộ tin nhắn của
  người đó trong 48h gần nhất** — dọn sạch cả loạt spam chứ không chỉ tin vừa gửi.
- Bot không thể ban admin nhóm; Telegram không cho phép.
- Không có bộ lọc nào chính xác 100%. `/check` và `ACTION=report` là hai công cụ để
  bạn hiệu chỉnh ngưỡng trước khi bật chế độ ban thật.
- Dữ liệu nằm trong `antispam.db` (SQLite, tạo tự động). File `.env` và `*.db` đã
  được `.gitignore` bỏ qua — đừng commit token.
