# Bot chống spam Telegram (chạy im lặng)

Bot tự động **xoá tin nhắn spam và xử lý người gửi mà không thông báo gì trong nhóm**.
Không có tin "đã ban X", không có cảnh báo, không có phản hồi — thành viên bình thường
gần như không nhận ra bot tồn tại. Mọi thứ chỉ được ghi vào console và (tuỳ chọn) một
kênh log riêng.

## Bot bắt được gì

Mỗi luật ở đây **tự nó đủ để xử lý** — khớp là ban, không khớp thì thôi. Không có
cộng dồn, không có ngưỡng, không có "gần đủ điểm".

| Luật | Bật/tắt được |
|---|---|
| Tin nhắn chuyển tiếp (forward) từ người/kênh khác | có |
| Tin gửi dưới danh nghĩa kênh lạ (`sender_chat`) | có |
| Link ngoài whitelist | có |
| Link rút gọn (bit.ly, cutt.ly…), tên miền rác (.xyz, .top, .icu…) | không |
| Link mời vào nhóm riêng `t.me/+…`, `t.me/joinchat/…` | không |
| Link viết né bộ lọc: `abc (dot) com`, `abc [.] com` | không |
| **Nội dung mã QR trong ảnh** | có (`SCAN_QR`) |
| Từ khoá lừa đảo tiếng Việt & tiếng Anh (~110 cụm) — **có xét ngữ cảnh** | không |
| Địa chỉ ví crypto | không |
| Số điện thoại lạ | có |
| Tên giả mạo ban quản trị ("Trợ lý", "QTV", "Admin"…) | có |
| Nhắc `@username` không được phép | có |
| Ký tự vô hình, cắt vụn chữ bằng dấu câu (`l.ừ.a đ.ả.o`) | không |
| Tin chia sẻ story, tin kèm nút bấm | không |
| Dồn tin / lặp nội dung / nhiều acc phối hợp | có (`CHONG_RAI`) |

Từ khoá phủ các nhóm lừa đảo phổ biến: việc nhẹ lương cao, tuyển CTV, cờ bạc/nhà cái,
đầu tư "cam kết lợi nhuận", airdrop crypto, vay nặng lãi, làm bằng giả, chiếm OTP,
mua bán tài khoản ngân hàng, nội dung người lớn.

### Vì sao không còn chấm điểm

Bot này từng cộng điểm: mỗi dấu hiệu một số điểm, vượt ngưỡng thì xử lý. Nghe hợp lý,
nhưng đo trên **1.761 lượt ban thật** của chính nó:

| | Số lượt | |
|---|---|---|
| Có sẵn một luật đủ mạnh, cộng dồn không đổi gì | 1.508 | 99,4% |
| Thật sự do cộng dồn quyết định | **10** | **0,6%** |

Mười lượt đó gần như đều là ban oan: *"số điện thoại + nhiều emoji"*, *"uy tín + đã vi
phạm 1 lần trước đó"*. Lớp điểm số không cứu được ca nào mà chỉ thêm oan sai.

Nguyên nhân sâu hơn: các dấu hiệu yếu **không độc lập với nhau**. Tổ hợp hay gặp nhất
là *"link lạ + thành viên mới gửi link + không có username gửi link"* — nhìn tưởng ba
bằng chứng, thực ra là **một sự việc đếm ba lần**. Cộng lại thành tự tin giả.

Nên bỏ hẳn. Luật nào không đủ chắc để một mình kết tội thì không có lý do tồn tại, và
đã xoá luôn: lạm dụng emoji, viết hoa toàn bộ, nhắc con số tiền, nhắc từ 3 tài khoản
trở lên, "ảnh này *có vẻ* chứa mã QR", và toàn bộ luật về lý lịch người gửi (thành
viên mới, không username, đã từng vi phạm).

**Lý lịch không kết tội.** Người từng vi phạm gửi một tin sạch thì tin đó vẫn sạch.

Chạy lại 1.766 lượt ban cũ qua bộ luật mới: **95% vẫn bị ban**. Phần rơi ra gần như
toàn bộ là luật bill ngân hàng đã bỏ từ trước, cộng đúng những tổ hợp ban oan kể trên.
Bù lại mỗi lần ban giờ chỉ ra được **một lý do đọc hiểu ngay**, thay vì bốn dấu hiệu
mơ hồ cộng lại thành 5/5. Tốc độ: **0,12 ms/tin**.

### Xét ngữ cảnh trước khi kết tội

Bot phổ thông chỉ so chuỗi: thấy "lừa đảo" là ban. Kết quả là ban oan người kể chuyện
phim, người trích tin tức, người đặt câu hỏi. Bot này xét thêm **người viết đang nhắm
vào ai**:

| Câu | Kết luận |
|---|---|
| "nhóm này lừa đảo đấy" | nhắm vào nhóm → xử lý |
| "bộ phim nói về một vụ lừa đảo" | đang kể chuyện → bỏ qua |
| "nhóm này có lừa đảo không?" | đang hỏi → bỏ qua |
| "công an vừa bắt nhóm lừa đảo" | trích tin tức → bỏ qua |
| "sàn kia lừa đảo, qua đây uy tín nè, ib" | kèm dấu hiệu quảng cáo → xử lý |

Áp dụng cho cả từ khoá dựng sẵn lẫn danh sách từ cấm tự đặt. Xem [ngucanh.py](antispam_bot/ngucanh.py).

## Quét mã QR trong ảnh

Bot tải ảnh về, giải mã QR bằng OpenCV, rồi đưa nội dung giải ra qua **đúng bộ luật
link và từ khoá** như chữ trong tin nhắn. Ngoài ra có luật riêng cho QR:

| Nội dung QR | Xử lý |
|---|---|
| QR chuyển khoản ngân hàng (VietQR/EMVCo) | chặn cứng |
| QR chứa ví crypto (`bitcoin:`, `ethereum:`, địa chỉ ví) | chặn cứng |
| QR dẫn tới link ngoài whitelist | chặn cứng |
| QR mời vào nhóm/kênh Telegram (`t.me/+…`, `tg://`) | chặn cứng |
| Ảnh có QR nhưng không đọc được nội dung (mờ, chụp nghiêng) | **bỏ qua** |
| QR dẫn tới domain trong whitelist, QR wifi | **bỏ qua** |

Bot xử lý ảnh (`photo`), file ảnh (`document` mime `image/*`) và sticker tĩnh. Ảnh quá
mờ hoặc QR bị bóp méo nhiều thì có thể không giải được. Riêng việc *dò ra khung QR mà
không đọc nổi* thì **cố ý không tính là vi phạm**: bộ dò nhận nhầm hoa văn ảnh đời
thường (đĩa cơm, vân vải) rất nhiều — đã từng gây 15/15 lượt ban oan liên tiếp.
Chỉ **nội dung giải được** mới bị xét.

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

## Chống rải hàng loạt

Ba luật trên đây xét **nội dung** từng tin. Phần này xét **hành vi** — bắt được
cả những tin mà đọc riêng từng cái thì hoàn toàn vô hại:

| Kiểu | Bắt khi | Chỉnh bằng |
|---|---|---|
| Dồn tin | Một người gửi 10 tin trong 10 giây | `FLOOD_MSGS`, `FLOOD_WINDOW` |
| Lặp lại | Một người gửi lại cùng nội dung 4 lần trong 2 phút | `REPEAT_LIMIT`, `REPEAT_WINDOW` |
| Phối hợp | 3 tài khoản khác nhau cùng đăng một đoạn chữ trong 5 phút | `RAID_USERS`, `RAID_WINDOW` |

Luật "phối hợp" là thứ bot thường bỏ lọt hoàn toàn, vì từng tin một nhìn không
có gì sai — chỉ khi đặt cạnh nhau mới lộ ra là chiến dịch. Bắt được rồi thì bot
**hốt cả ổ**: đuổi luôn những tài khoản đã đăng cùng nội dung trước đó, chứ
không chỉ xử cái acc cuối cùng vừa bị bắt.

Vài điểm đã cân nhắc để khỏi bắt oan:

- **Acc seeding được bỏ qua hoàn toàn** — nick của mình đăng trùng nhau giữa
  các nhóm là chuyện bình thường.
- **Luật phối hợp chỉ xét chữ, không xét ảnh.** Ba người cùng đăng lại một tấm
  meme trong 5 phút là chuyện thường ở nhóm đông.
- **Nội dung dưới 12 ký tự không tính lặp.** "ok", "vâng", "=))" lặp bao nhiêu
  lần cũng được.
- **Mỗi nhóm đếm riêng.** Đăng ở 3 nhóm khác nhau không cộng dồn thành chiến dịch.

Tắt bằng `CHONG_RAI=false`, hoặc bấm trong menu công tắc của bot. Toàn bộ chạy
trong bộ nhớ (0,02 ms mỗi tin, không đụng database); khởi động lại là quên hết,
nên không ai bị phạt vì chuyện hôm qua.

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
- `BLOCK_PHONES` / `BLOCK_MENTIONS` — tắt là tắt hẳn, không còn "phạt nhẹ" nữa.
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

Kiểm thử QR đầu-cuối: tự tạo ảnh QR, giải mã, rồi đưa qua bộ luật. Tự bỏ qua nếu
có OpenCV.

Lần chạy đầu mất khoảng 5–6 giây để biên dịch `.pyc`, các lần sau chỉ hơn 1 giây.
Đừng bấm Ctrl+C khi thấy nó "đứng im" lúc khởi động.

## Cấu trúc

```
antispam_bot/
  config.py     đọc .env
  normalize.py  chuẩn hoá text: bỏ dấu, ký tự ẩn, homoglyph, leetspeak
  detector.py   từ khoá + regex + luật dứt khoát  ← chỉnh ở đây khi muốn thêm luật
  ngucanh.py    xét ngữ cảnh quanh từ cấm trước khi kết luận
  raivai.py     chống rải hàng loạt (dồn tin / lặp / phối hợp)
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
