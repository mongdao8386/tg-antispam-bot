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

Các luật trên xét **nội dung** từng tin. Phần này xét **hành vi** — bắt được cả
những tin mà đọc riêng từng cái thì hoàn toàn vô hại.

| Kiểu | Bắt khi | Nhớ ở đâu |
|---|---|---|
| Dồn tin | Một người gửi 10 tin trong 10 giây | bộ nhớ tạm |
| Lặp lại | Một người gửi lại cùng nội dung 4 lần trong 2 phút | bộ nhớ tạm |
| **Chiến dịch (chữ)** | **3 tài khoản khác nhau cùng đăng một bài** | **database** |
| **Chiến dịch (ảnh)** | **4 tài khoản khác nhau cùng đăng một tấm ảnh** | **database** |

### Chiến dịch: thứ bot khác không thấy

Đây là kiểu tấn công nguy hiểm nhất, và cũng là thứ bot chống spam thường bỏ lọt
hoàn toàn: từng tin một nhìn không có gì sai, chỉ khi đặt cạnh nhau mới lộ ra.

Đo trên dữ liệu thật của nhóm, chiến dịch lớn nhất:

| | |
|---|---|
| Tài khoản tham gia | **334** |
| Nhóm bị rải | 16 |
| Kéo dài | **27 ngày** |
| Chỗ dày nhất | 14 tin / 5 phút |

Vì rải chậm như vậy nên bộ nhớ tạm vài phút, lại đếm riêng từng nhóm, gần như mù.
Bot này nhớ vân tay nội dung **trong database, đếm trên mọi nhóm, không giới hạn
thời gian**. Chạy lại toàn bộ lịch sử: nhận ra **36 chiến dịch**, bắt được **30%
số lượt ban ngay từ tin đầu tiên**.

Điểm mấu chốt: luật này **không quan tâm tin nhắn nói gì**. Kẻ spam đổi hết từ
khoá, bỏ hết link, viết lại cả bài vẫn dính — vì cái lộ ra không nằm trong một
tin, mà nằm ở chỗ nhiều tài khoản cùng đăng một thứ.

Bắt được rồi thì **hốt cả ổ**: database nhớ ai đã đăng bài đó ở nhóm nào, kể cả
từ nhiều ngày trước, nên đuổi được cả những acc đã đăng xong đi mất từ lâu.

### Xào lại vài chữ cũng không thoát

Vân tay dùng SimHash trên cụm 3 ký tự, nên sửa vặt chỉ làm **lật vài bit** chứ
không đổi hẳn vân tay như hàm băm thường:

| Biến thể | Lệch | Kết luận |
|---|---|---|
| Thêm emoji, đổi HOA/thường, thêm dấu chấm than | 0 bit | cùng một bài |
| Chèn dấu chấm giữa chữ (`S.a.n`) | 0 bit | cùng một bài |
| Thêm một cụm ngắn ở cuối | 5 bit | cùng một bài |
| Đổi con số tiền (`100k` → `200k`) | 6 bit | cùng một bài |
| Đổi hẳn tên sàn | 9 bit | bài khác |
| Hai câu nội dung khác hẳn | 24–35 bit | bài khác |

Ngưỡng đặt ở 6 bit — nằm giữa hai vùng, cách xa cả hai bên.

Tra cứu vân tay gần giống mà không quét cả bảng: cắt 64 bit thành 8 băng rồi
đánh chỉ mục từng băng. Theo nguyên lý chuồng bồ câu, hai vân tay lệch không quá
7 bit thì chắc chắn có ít nhất một băng trùng khít — nên chỉ cần tra khoá chính.

### Vân tay ảnh: chiến dịch không có một chữ nào

19% số lượt ban không có chữ — ảnh, QR, forward. Bộ nhớ chữ mù hoàn toàn trước
kiểu rải bằng ảnh, mà `file_unique_id` của Telegram thì vô dụng: tải lên lại là
có mã mới, dù mắt người nhìn vẫn đúng tấm đó.

Nay dùng **pHash**: đưa ảnh về xám 32×32, DCT, lấy góc trên trái 8×8 — phần
chứa những nét *lớn* của ảnh — rồi so từng hệ số với trung vị.

| Biến dạng | Lệch |
|---|---|
| Nén JPEG q=15, thu nhỏ ½, phóng to 150%, chỉnh sáng | **0 bit** |
| Chèn thêm chữ ở góc | 0 bit |
| Cắt viền 5% | 14 bit — **không nhận ra** |
| Hai ảnh khác nhau | 16–26 bit |

Cắt xén thì thua, đó là giới hạn đã biết của pHash. Bù lại nén và đổi kích
thước — hai thứ Telegram tự làm mỗi lần tải lên — không hề ảnh hưởng.

**Ảnh phẳng bị bỏ qua.** Ảnh gần một màu cho vân tay vô nghĩa và đụng nhau hàng
loạt; bot đo độ tương phản trước, dưới ngưỡng thì không lấy vân tay. Thà bỏ lọt
còn hơn gộp ba tấm ảnh trắng của ba người thành một "chiến dịch".

**Ngưỡng ảnh cao hơn chữ một bậc** (`RAID_USERS_ANH=4`): ba người cùng đăng lại
một tấm meme là chuyện thường, ba người cùng gõ y hệt một đoạn chữ dài thì
không. Hai loại vân tay dùng chung bảng nhưng `loai` nằm trong khoá chính nên
**không bao giờ lẫn nhau** — có test khoá lại điều đó.

### Tự học từ những lần bạn gỡ ban

Mỗi lần bạn gõ `/undo` là bạn đang nói *"luật này bắt sai"*. Đó là dữ liệu quý
nhất bot có — đúng nhóm, đúng người, đúng kiểu tin nhắn của bạn. Trước đây nó bị
vứt đi.

Nay bot làm hai việc:

**1. Tha ngay cái vừa bắt sai.** Gỡ một lượt ban vì chiến dịch rải thì bot tha
luôn nội dung (hoặc tấm ảnh) đó — lần sau ai đăng lại cũng không bị. Hành động
hẹp, chỉ đụng đúng bài bạn vừa tuyên là oan.

**2. Tự tắt luật bắt sai quá nhiều.** Một luật bị gỡ đủ `TU_HOC_NGUONG` lần
(mặc định 5) là nó không hợp với nhóm của bạn — bot tự tắt công tắc tương ứng và
báo rõ trong terminal lẫn tin trả lời.

Ranh giới cố ý hẹp: **bot chỉ tắt được những công tắc mà chính bạn cũng bật lại
được bằng tay trong `/panel`**. Nó không tự nghĩ ra luật mới, không nới lỏng thứ
gì nằm ngoài tầm tay bạn — có test khoá lại đúng điều kiện đó. Từ khoá tự đặt
thì bot chỉ đếm và báo, việc bỏ từ nào là quyết định của bạn.

`/learned` xem bot đã học gì và còn mấy lần nữa thì một luật bị tắt.
`/learned reset` xoá sạch bộ đếm. Tắt hẳn bằng `TU_HOC=false`.

Vì sao không học trọng số như học máy: đã bỏ hệ thống điểm số vì nó không giải
thích được, học ra một mớ trọng số cũng y hệt vậy mà còn khó đoán hơn. Đếm và
tắt thì đọc log là hiểu ngay chuyện gì đã xảy ra.

### Nhân đôi chữ cái — chiêu né rẻ nhất

`normalize()` chỉ gộp khi một chữ lặp **từ 3 lần**, nên gõ đúng **hai lần** là
lọt sạch mọi luật từ khoá — kể cả danh sách tự đặt:

| Viết | Trước | Nay |
|---|---|---|
| `nhà cái uy tín` | chặn | chặn |
| `nhàa cáii uy tínn` | **lọt** | chặn |
| `lừaa đảoo`, `luaa daoo` | **lọt** | chặn |
| `gaii gooi`, `taii xiuu` | **lọt** | chặn |

Gặp ngoài thực tế dưới dạng `lộcc 70k nhắnn tele`. Nay có thêm dạng so khớp
**đã gộp mọi chữ lặp**, áp cho cả hai vế nên không lệch nhau.

Không gộp thẳng trong `normalize()` vì "xoong" và "xong" là hai từ khác nhau —
chỉ dùng làm dạng **dự phòng**, khi các dạng kia đã không khớp. Dạng gộp vẫn
**giữ dấu**, nên `lựa đào` gộp xong vẫn là `lựa đào`, không biến thành
`lua dao`: chống ban oan cũ vẫn nguyên vẹn.

### Đã thử và bỏ: che chữ số

Kẻ rải hay xoay con số (`70k` → `50k`) để tách vân tay. Thử thay mọi chữ số
bằng `#` trước khi lấy vân tay — đo trên lịch sử thật thì **bắt được ÍT hơn**
(635 so với 648 lượt, 39 so với 41 chiến dịch), lại gộp nhầm *"chuyển khoản
500k"* với *"chuyển khoản 200k"*. Ba thành viên khoe bill khác số tiền sẽ bị
tính thành một chiến dịch. Không đáng.

### Để khỏi bắt oan

- **Acc seeding được bỏ qua hoàn toàn** — nick của mình đăng trùng nhau giữa các
  nhóm là chuyện bình thường.
- **Nội dung dưới 25 ký tự không lấy vân tay.** "ok", "chào cả nhà", "cảm ơn nhé"
  bao nhiêu người cùng nói cũng được.
- **`/allow_content`** (reply) — tha một nội dung hay bị đăng lại hợp lệ: nội quy,
  thông báo định kỳ, mẫu đăng ký sự kiện.
- **`/campaigns`** — xem bot đang coi những gì là chiến dịch, trước khi tin nó.
- Luật dồn tin và lặp lại chỉ nhớ trong bộ nhớ tạm, khởi động lại là quên — không
  ai bị phạt vì chuyện hôm qua.

Tắt bằng `CHONG_RAI=false` hoặc trong menu công tắc. Tốc độ: **0,06 ms** cho vân
tay, **0,13 ms** cho cả lượt tra database.

## Tự xoá tin nhắn dịch vụ## Tự xoá tin nhắn dịch vụ

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
  vantay.py     vân tay chữ chịu được sửa đổi nhỏ (SimHash)
  anhhash.py    vân tay ảnh chịu được nén/thu nhỏ (pHash)
  tuhoc.py      học từ những lần admin gỡ ban
  qrscan.py     giải mã QR trong ảnh (OpenCV, tuỳ chọn)
  storage.py    SQLite: thành viên mới, lịch sử vi phạm, whitelist theo nhóm
  bot.py        handler Telegram, thực thi hình phạt, lệnh quản trị
  __main__.py   khởi chạy
tests/
  test_vantay.py
  test_tuhoc.py
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
