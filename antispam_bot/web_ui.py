"""Giao diện bảng điều khiển. Tách khỏi web.py cho dễ đọc.

Thiết kế cho điện thoại trước: một cột, nút to đủ bấm bằng ngón tay, không
cần thư viện ngoài (không CDN) nên mở được cả khi mạng chặn.
"""

TRANG_CHUA_DANG_NHAP = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cần đăng nhập</title>
<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;
display:grid;place-items:center;height:100vh;margin:0;text-align:center;padding:20px}
code{background:#222;padding:2px 8px;border-radius:6px}</style>
<div><h2>Chưa đăng nhập</h2>
<p>Nhắn <code>/web</code> cho bot trong Telegram để lấy liên kết vào.</p></div>
"""

TRANG_VE_HET_HAN = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Liên kết hết hạn</title>
<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;
display:grid;place-items:center;height:100vh;margin:0;text-align:center;padding:20px}
code{background:#222;padding:2px 8px;border-radius:6px}</style>
<div><h2>Liên kết đã hết hạn</h2>
<p>Mỗi liên kết chỉ dùng được một lần, trong 5 phút.</p>
<p>Nhắn <code>/web</code> cho bot để lấy liên kết mới.</p></div>
"""

TRANG_CHINH = r"""<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Bảng điều khiển chống spam</title>
<style>
*{box-sizing:border-box}
:root{
  --nen:#0f1115; --the:#181b22; --vien:#262a33; --chu:#e8eaed; --mo:#9aa0a8;
  --xanh:#2ea043; --do:#da3633; --vang:#d29922; --xanhduong:#316dca;
}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  background:var(--nen);color:var(--chu);padding:12px;padding-bottom:40px;
  max-width:820px;margin:0 auto;-webkit-text-size-adjust:100%}
h1{font-size:19px;margin:4px 0 14px}
h2{font-size:15px;margin:0 0 10px;color:var(--mo);font-weight:600}
.the{background:var(--the);border:1px solid var(--vien);border-radius:12px;
  padding:14px;margin-bottom:12px}
.trangthai{font-size:17px;font-weight:600;margin-bottom:10px}
.hang{display:flex;gap:8px;flex-wrap:wrap}
button{font:inherit;font-size:15px;padding:11px 14px;border-radius:9px;
  border:1px solid var(--vien);background:#20242c;color:var(--chu);
  cursor:pointer;flex:1;min-width:120px;min-height:44px}
button:active{transform:scale(.97)}
button.chinh{background:var(--xanh);border-color:var(--xanh);color:#fff}
button.canh{background:var(--vang);border-color:var(--vang);color:#000}
button.nguyhiem{background:var(--do);border-color:var(--do);color:#fff}
button.nho{flex:0 0 auto;min-width:auto;padding:7px 11px;font-size:13px;min-height:36px}
textarea{width:100%;min-height:130px;background:#0c0e12;color:var(--chu);
  border:1px solid var(--vien);border-radius:9px;padding:10px;font:14px/1.5 ui-monospace,monospace;
  resize:vertical}
.tab{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;padding-bottom:4px;
  -webkit-overflow-scrolling:touch}
.tab button{flex:0 0 auto;font-size:14px;padding:9px 13px;min-width:auto}
.tab button.chon{background:var(--xanhduong);border-color:var(--xanhduong);color:#fff}
.muc{display:flex;justify-content:space-between;align-items:center;gap:10px;
  padding:9px 0;border-bottom:1px solid var(--vien);font-size:14px}
.muc:last-child{border-bottom:none}
.mo{color:var(--mo);font-size:12.5px}
.nhan{display:inline-block;padding:2px 8px;border-radius:20px;font-size:12px;
  background:#20242c;border:1px solid var(--vien);margin:2px 4px 2px 0}
.trong{color:var(--mo);text-align:center;padding:18px;font-size:14px}
#bao{position:fixed;left:50%;transform:translateX(-50%);bottom:20px;
  background:#fff;color:#000;padding:11px 20px;border-radius:24px;font-size:14px;
  font-weight:600;opacity:0;transition:.25s;pointer-events:none;z-index:9;
  box-shadow:0 4px 20px rgba(0,0,0,.4)}
#bao.hien{opacity:1}
.tt{font-size:13px;color:var(--mo);margin:8px 0 0}
</style></head><body>

<h1>🛡 Bảng điều khiển chống spam</h1>

<div class="the">
  <div class="trangthai" id="trangthai">Đang tải…</div>
  <div class="hang" id="nutdk"></div>
  <p class="tt" id="tomtat"></p>
</div>

<div class="the">
  <h2>Nhóm đang quản lý</h2>
  <div id="nhom"><div class="trong">Đang tải…</div></div>
</div>

<div class="the">
  <h2>Danh sách áp dụng cho mọi nhóm</h2>
  <div class="tab" id="tab"></div>
  <textarea id="oban" placeholder="Mỗi dòng một mục…"></textarea>
  <p class="tt" id="gopy"></p>
  <div class="hang" style="margin-top:9px">
    <button class="chinh" onclick="them()">Thêm các dòng trên</button>
    <button class="nguyhiem" onclick="xoa()">Xoá các dòng trên</button>
  </div>
  <div id="dsach" style="margin-top:12px"></div>
</div>

<div class="the" id="thePreset">
  <h2>Bộ từ cấm dựng sẵn</h2>
  <div id="preset"></div>
</div>

<div class="the">
  <h2>Đã xử lý gần đây</h2>
  <div id="bans"><div class="trong">Đang tải…</div></div>
</div>

<div id="bao"></div>

<script>
const $ = s => document.querySelector(s);
let tabHienTai = 'tucam';

const TABS = [
  ['tucam',   'Từ cấm',      'Mỗi dòng một cụm từ. Ai gửi tin chứa nó là bị ban ngay.'],
  ['sdt',     'SĐT cho phép','Số được phép xuất hiện. Số khác sẽ bị chặn.'],
  ['at',      '@ cho phép',  'Không cần gõ dấu @. @ của admin nhóm đã tự được phép.'],
  ['domain',  'Link cho phép','Ghi t.me/kenh-abc để chỉ mở đúng kênh đó, hoặc example.com để mở cả tên miền.'],
  ['seeding', 'Acc seeding', 'user_id của acc được phép chuyển tiếp. Mỗi dòng một số.'],
  ['chancung','Chặn cứng',   'user_id hoặc channel_id bị ban bất kể nội dung.'],
];

function bao(t){const b=$('#bao');b.textContent=t;b.classList.add('hien');
  clearTimeout(b._t);b._t=setTimeout(()=>b.classList.remove('hien'),2200);}

async function api(url, opt){
  const r = await fetch(url, opt);
  if(r.status===401){location.reload();return null;}
  return r.json();
}
const post = (url,body)=>api(url,{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});

function veTabs(){
  $('#tab').innerHTML = TABS.map(([ma,ten])=>
    `<button class="${ma===tabHienTai?'chon':''}" onclick="doiTab('${ma}')">${ten}</button>`
  ).join('');
  $('#gopy').textContent = (TABS.find(t=>t[0]===tabHienTai)||[])[2] || '';
}
function doiTab(ma){tabHienTai=ma;veTabs();taiDanhSach();}

async function taiTrangThai(){
  const d = await api('/api/trangthai'); if(!d) return;
  let tt, nut;
  if(d.dang_ngung){
    tt = `⏸ <b>Đang tạm ngưng</b> — còn ${d.con_lai_phut} phút`;
    nut = `<button class="chinh" onclick="dk('batlai')">▶️ Bật lại ngay</button>`;
  } else if(d.che_do==='report'){
    tt = `🧪 <b>Chế độ thử</b> — chỉ ghi log, không ban ai`;
    nut = `<button class="chinh" onclick="dk('chedo','ban')">🔨 Bật ban lại</button>
           <button onclick="dk('ngung',30)">⏸ Ngưng 30′</button>`;
  } else {
    tt = `✅ <b>Đang bảo vệ</b> — chế độ <code>${d.che_do}</code>`;
    nut = `<button onclick="dk('ngung',30)">⏸ Ngưng 30′</button>
           <button onclick="dk('ngung',120)">⏸ Ngưng 2h</button>
           <button class="canh" onclick="dk('chedo','report')">🧪 Chế độ thử</button>`;
  }
  $('#trangthai').innerHTML = tt;
  $('#nutdk').innerHTML = nut;
  let tom = `Đã xử lý 1 giờ qua: <b>${d.ban_1h}</b> người · QR: ${d.qr?'bật':'tắt'} · OCR: ${d.ocr?'bật':'tắt'}`;
  if(d.phanh_luc && (Date.now()/1000 - d.phanh_luc) < 86400){
    tom += `<br>🛑 Bot đã tự phanh lúc ${new Date(d.phanh_luc*1000).toLocaleString('vi')}`;
  }
  $('#tomtat').innerHTML = tom;

  $('#nhom').innerHTML = d.nhom.length ? d.nhom.map(g=>
    `<div class="muc"><div>${esc(g.ten)}<div class="mo">${g.id}</div></div>
     <div class="mo" style="text-align:right">${g.tong} lượt<br>24h: ${g.ngay}</div></div>`
  ).join('') : '<div class="trong">Chưa có nhóm nào</div>';
}

async function dk(viec, giatri){
  const body = viec==='ngung' ? {viec:'ngung',phut:giatri}
             : viec==='chedo' ? {viec:'chedo',gia_tri:giatri}
             : {viec:'batlai'};
  await post('/api/dieukhien', body);
  bao('Đã cập nhật');
  taiTrangThai();
}

function esc(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML;}

async function taiDanhSach(){
  const d = await api('/api/danhsach/'+tabHienTai); if(!d) return;
  const el = $('#dsach');
  if(!d.muc.length){el.innerHTML='<div class="trong">Danh sách trống</div>';return;}
  el.innerHTML = `<div class="mo" style="margin-bottom:7px">${d.muc.length} mục</div>`
    + d.muc.map(m=>`<span class="nhan">${esc(m)}</span>`).join('');
}

function layDong(){
  return $('#oban').value.split('\n').map(s=>s.trim()).filter(Boolean);
}
async function them(){
  const muc = layDong();
  if(!muc.length){bao('Chưa nhập gì');return;}
  const r = await post('/api/danhsach/'+tabHienTai,{muc}); if(!r) return;
  $('#oban').value='';bao(`Đã thêm ${r.so} mục`);taiDanhSach();
}
async function xoa(){
  const muc = layDong();
  if(!muc.length){bao('Chưa nhập gì');return;}
  const r = await post('/api/danhsach/'+tabHienTai,{muc,xoa:true}); if(!r) return;
  $('#oban').value='';bao(`Đã xoá ${r.so} mục`);taiDanhSach();
}

async function taiPreset(){
  const d = await api('/api/preset'); if(!d) return;
  $('#preset').innerHTML = d.bo.map(b=>
    `<div class="muc"><div>${esc(b.ten)}<div class="mo">${b.so} cụm</div></div>
     <div class="hang" style="flex:0 0 auto">
       <button class="nho chinh" onclick="preset('${b.ma}',0)">Nạp</button>
       <button class="nho" onclick="preset('${b.ma}',1)">Gỡ</button>
     </div></div>`).join('');
}
async function preset(ma, xoa){
  const r = await post('/api/preset',{ma,xoa:!!xoa}); if(!r) return;
  bao(xoa?`Đã gỡ ${r.so} cụm`:`Đã nạp ${r.so} cụm`);
  if(tabHienTai==='tucam') taiDanhSach();
}

async function taiBans(){
  const d = await api('/api/banganday?limit=25'); if(!d) return;
  const el = $('#bans');
  if(!d.muc.length){el.innerHTML='<div class="trong">Chưa có lượt nào</div>';return;}
  el.innerHTML = d.muc.map(b=>{
    const khi = new Date(b.luc*1000).toLocaleString('vi',{day:'2-digit',month:'2-digit',
      hour:'2-digit',minute:'2-digit'});
    return `<div class="muc"><div style="min-width:0">
      <b>${esc(b.ten||b.uid)}</b> <span class="mo">${b.uid}</span>
      <div class="mo">${khi} · ${esc(b.ly_do).slice(0,110)}</div>
      ${b.trich?`<div class="mo">“${esc(b.trich).slice(0,70)}”</div>`:''}
      </div>
      <button class="nho" onclick="goBan(${b.nhom},${b.uid},this)">Gỡ</button></div>`;
  }).join('');
}
async function goBan(nhom, uid, nut){
  nut.disabled=true;nut.textContent='…';
  const r = await post('/api/goban',{nhom,uid});
  if(r && r.ok){nut.textContent='Đã gỡ';bao('Đã gỡ ban');}
  else{nut.disabled=false;nut.textContent='Gỡ';bao('Không gỡ được');}
}

function taiTatCa(){taiTrangThai();taiDanhSach();taiBans();}
veTabs();taiTatCa();taiPreset();
setInterval(taiTrangThai, 20000);
</script></body></html>
"""
