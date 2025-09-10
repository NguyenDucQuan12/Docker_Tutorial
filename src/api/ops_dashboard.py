# app/routers/ops_dashboard.py
# -*- coding: utf-8 -*-

"""
Dashboard vận hành (ops) dạng single-file:
- HTML: /ops/dashboard  → Form đăng nhập (dùng /auth/login của bạn) + 3 biểu đồ + 2 bảng + nút Export Excel
- JSON:  /ops/metrics/summary, /ops/metrics/top_suspicious, /ops/metrics/current_bans
- Export: /ops/export/metrics.xlsx
Bảo vệ:
- Tất cả API JSON/Export yêu cầu Authorization: Bearer <Access_token> (token từ /auth/login của bạn)
- Chỉ người dùng có Privilege ∈ {"Admin","Boss"} mới truy cập /ops/* (trừ /ops/dashboard là HTML tĩnh)

Lưu ý kỹ thuật:
- Biểu đồ dùng Chart.js (time scale) + date-fns adapter, trục X là epoch ms (real time axis).
- Tránh lỗi vẽ trắng: showDash() trước rồi mới bootstrap() tạo chart; và feed data dạng {x, y}.
- Không dùng f-string cho HTML để không xung đột với JS template literal `${...}`.
"""

import io                                   # Tạo file Excel in-memory
import time                                 # Tính bucket phút hiện tại
from typing import Any                      # Type hint tổng quát

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse

from auth.oauth2 import required_token_user            # ⬅️ Auth có sẵn của bạn (decode JWT)
from security.redis_client import get_redis            # ⬅️ Redis client (connection pool)
from security.keyspace import (                        # ⬅️ Bộ tạo key tập trung (đã tách riêng)
    k_metric_req, k_metric_5xx, k_metric_bans
)

# Thư viện Excel (cài: pip install openpyxl)
from openpyxl import Workbook

# ===== Khởi tạo Router & Redis =====
router = APIRouter(prefix="/ops", tags=["Ops Dashboard"])
_r = get_redis()  # Redis singleton/pool dùng chung


# ====== Guard quyền cho API /ops/* (trừ /ops/dashboard) ======
def require_ops_admin(user: Any = Depends(required_token_user)) -> Any:
    """
    - required_token_user: Dependency của bạn → giải mã JWT từ header Authorization: Bearer <Access_token>
    - Chỉ cho phép Privilege 'Admin' hoặc 'Boss' truy cập các API JSON/Export.
    - Trả lại object/dict user đã xác thực để dùng tiếp (nếu cần).
    """
    # user có thể là pydantic model hoặc dict; lấy Privilege linh hoạt:
    priv = getattr(user, "Privilege", None) if not isinstance(user, dict) else user.get("Privilege")
    if priv not in {"Admin", "Boss"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privilege")
    return user


# =======================
# (1) HTML DASHBOARD
# =======================
@router.get("/dashboard", response_class=HTMLResponse, summary="Dashboard HTML (login + Chart.js time scale)")
def ops_dashboard():
    """
    Trả về một trang HTML độc lập, chứa:
    - Form Login: gọi POST /auth/login (form-urlencoded: username, password) → nhận Access_token → lưu localStorage
    - Sau khi login, show panel dashboard rồi bootstrap() vẽ 3 biểu đồ và 2 bảng
    - Nút Export Excel: tải /ops/export/metrics.xlsx
    """
    # ❗️KHÔNG dùng f-string để giữ nguyên ${...} trong JS.
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Ops Dashboard</title>

  <!-- BẮT BUỘC: nạp date-fns trước adapter của Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/date-fns@2"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>

  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 16px; background: #fafafa; color: #222; }
    .container { max-width: 1200px; margin: 0 auto; }
    header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    h1 { font-size: 20px; margin: 0; }
    .note { color: #666; font-size: 12px; }
    .card { background: #fff; border: 1px solid #e5e5e5; border-radius: 12px; padding: 12px 12px 16px; box-shadow: 0 1px 2px rgba(0,0,0,.04); margin-bottom: 14px; }
    canvas { width: 100% !important; height: 300px !important; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #eee; padding: 8px; font-size: 13px; }
    th { background: #f9fafb; text-align: left; }
    code { background: #f3f3f3; padding: 2px 6px; border-radius: 4px; }
    .row { display: grid; grid-template-columns: 1fr; gap: 14px; }
    @media (min-width: 1100px) { .row { grid-template-columns: 1.2fr 0.8fr; } }
    .actions { display: flex; gap: 8px; align-items: center; }
    .btn { border: 1px solid #ddd; background: #fff; padding: 6px 10px; border-radius: 8px; cursor: pointer; }
    .btn:hover { background: #f6f6f6; }
    .hidden { display: none; }
    .error { color: #b40000; font-size: 12px; }
    input[type=text], input[type=password] { padding: 8px; border-radius: 8px; border: 1px solid #ddd; width: 260px; }
    label { font-size: 13px; color: #444; }
  </style>
</head>
<body>
<div class="container">

  <header>
    <h1>Ops Dashboard</h1>
    <div class="note">Đăng nhập để xem số liệu. Tự refresh 5 giây/lần.</div>
  </header>

  <!-- Panel Login -->
  <div id="loginPanel" class="card">
    <h2>Đăng nhập</h2>
    <div style="display:flex; gap:12px; align-items:center; flex-wrap: wrap;">
      <div>
        <label>Email</label><br/>
        <input id="email" type="text" placeholder="admin@example.com" />
      </div>
      <div>
        <label>Password</label><br/>
        <input id="password" type="password" placeholder="••••••••" />
      </div>
      <div style="align-self:flex-end;">
        <button class="btn" onclick="login()">Login</button>
      </div>
      <div class="error" id="loginError"></div>
    </div>
  </div>

  <!-- Panel Dashboard (ẩn trước, show sau khi login để tránh Chart.js vẽ khi width=0) -->
  <div id="dashPanel" class="hidden">
    <div class="row">
      <div>
        <div class="card">
          <div class="actions">
            <h2 style="margin-right:auto;">Requests / minute</h2>
            <button class="btn" onclick="exportExcel()">Export Excel</button>
            <button class="btn" onclick="logout()">Logout</button>
          </div>
          <canvas id="chartReq"></canvas>
        </div>
        <div class="card">
          <h2>5xx / minute</h2>
          <canvas id="chart5xx"></canvas>
        </div>
        <div class="card">
          <h2>Bans / minute</h2>
          <canvas id="chartBans"></canvas>
        </div>
      </div>
      <div>
        <div class="card">
          <h2>Top Suspicious (điểm nghi vấn còn TTL)</h2>
          <div id="suspicious"></div>
        </div>
        <div class="card">
          <h2>Current Bans (IP đang bị BAN + TTL)</h2>
          <div id="bans"></div>
        </div>
      </div>
    </div>
  </div>

</div>

<script>
// ===== Token helpers: lưu token vào localStorage (đơn giản) =====
function getToken() { return localStorage.getItem('ops_token') || ''; }
function setToken(t) { localStorage.setItem('ops_token', t); }
function clearToken() { localStorage.removeItem('ops_token'); }

// ===== Toggle UI =====
function showLogin() { document.getElementById('loginPanel').classList.remove('hidden'); document.getElementById('dashPanel').classList.add('hidden'); }
function showDash()  { document.getElementById('loginPanel').classList.add('hidden');   document.getElementById('dashPanel').classList.remove('hidden'); }

// ===== Login dùng /auth/login của bạn (OAuth2PasswordRequestForm) =====
async function login() {
  const email = document.getElementById('email').value.trim();   // → request.username
  const password = document.getElementById('password').value;    // → request.password
  document.getElementById('loginError').innerText = '';

  // /auth/login cần body dạng form-urlencoded
  const body = new URLSearchParams({ username: email, password });

  try {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body
    });
    if (!res.ok) {
      const t = await res.json().catch(() => ({}));
      throw new Error(t.detail?.message || ('HTTP ' + res.status));
    }
    const data = await res.json();
    const token = data.Access_token;  // API của bạn trả "Access_token"
    if (!token) throw new Error('Không nhận được Access_token');

    setToken(token);

    // ❗️Quan trọng: show panel trước, sau đó mới vẽ chart
    showDash();
    setTimeout(() => { bootstrap().catch(e => console.error(e)); }, 0);
  } catch (e) {
    document.getElementById('loginError').innerText = e.message || 'Login failed';
  }
}

function logout() {
  clearToken();
  if (window.__opsInterval) clearInterval(window.__opsInterval);
  showLogin();
}

// ===== Fetch JSON kèm Bearer token =====
async function fetchJSON(url) {
  const token = getToken();
  const headers = token ? { 'Authorization': 'Bearer ' + token } : {};
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(url + ' -> ' + res.status);
  return res.json();
}

// ===== Chuyển minutes + values → mảng điểm {x (epoch ms), y} =====
function toXY(minutes, values) {
  const out = [];
  for (let i = 0; i < minutes.length; i++) {
    const ms = (minutes[i] || 0) * 60 * 1000;    // minute bucket → epoch ms
    const v  = Number(values[i] || 0);
    out.push({ x: ms, y: v });
  }
  return out;
}

// ===== Tạo Line chart theo time-scale, feed data dạng {x,y} (không cần labels) =====
function createLineChart(canvasId, label, xy) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [{
        label,
        data: xy,
        tension: 0.25,
        fill: false,
        pointRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: true, // để Chart.js tự hiểu {x,y}
      scales: {
        x: { type: 'time', time: { unit: 'minute' } },
        y: { beginAtZero: true }
      },
      plugins: { legend: { display: true }, tooltip: { enabled: true } }
    }
  });
  chart.resize(); // đảm bảo vẽ sau khi có kích thước thực
  return chart;
}

// ===== Tạo Bar chart theo time-scale, feed data {x,y} =====
function createBarChart(canvasId, label, xy) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  const chart = new Chart(ctx, {
    type: 'bar',
    data: {
      datasets: [{
        label,
        data: xy
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: true,
      scales: {
        x: { type: 'time', time: { unit: 'minute' }, grid: { display: false } },
        y: { beginAtZero: true }
      },
      plugins: { legend: { display: true }, tooltip: { enabled: true } }
    }
  });
  chart.resize();
  return chart;
}

// ===== Render bảng Top Suspicious =====
function renderSuspicious(data) {
  const rows = (data.items || []).map(it => `
    <tr>
      <td><code>${it.ip}</code></td>
      <td>${it.score}</td>
      <td>${it.ttl_seconds ?? '-'}</td>
    </tr>
  `).join('');
  const html = `
    <table>
      <thead><tr><th>IP</th><th>Score (5min)</th><th>TTL(s)</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  document.getElementById('suspicious').innerHTML = html;
}

// ===== Render bảng Current Bans =====
function renderBans(data) {
  const rows = (data.items || []).map(it => `
    <tr>
      <td><code>${it.ip}</code></td>
      <td>${it.ttl_seconds}</td>
    </tr>
  `).join('');
  const html = `
    <table>
      <thead><tr><th>IP</th><th>TTL(s)</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  document.getElementById('bans').innerHTML = html;
}

// ===== Biến chart toàn cục =====
let chartReq = null, chart5xx = null, chartBans = null;

// ===== Khởi tạo sau khi login =====
async function bootstrap() {
  // (1) Lấy summary 10 phút gần nhất
  const summary = await fetchJSON('/ops/metrics/summary');
  const xyReq  = toXY(summary.minutes, summary.req);
  const xy5xx  = toXY(summary.minutes, summary.s5xx);
  const xyBans = toXY(summary.minutes, summary.bans);

  // (2) Huỷ chart cũ (nếu có) để render lại trong trạng thái panel đã hiện
  if (chartReq)  { chartReq.destroy();  chartReq = null; }
  if (chart5xx)  { chart5xx.destroy();  chart5xx = null; }
  if (chartBans) { chartBans.destroy(); chartBans = null; }

  // (3) Tạo chart mới
  chartReq  = createLineChart('chartReq',  'Requests/min', xyReq);
  chart5xx  = createLineChart('chart5xx',  '5xx/min',      xy5xx);
  chartBans = createBarChart ('chartBans', 'Bans/min',     xyBans);

  // (4) Render 2 bảng
  renderSuspicious(await fetchJSON('/ops/metrics/top_suspicious?limit=50'));
  renderBans(await fetchJSON('/ops/metrics/current_bans'));

  // (5) Bật auto refresh 5s/lần
  if (window.__opsInterval) clearInterval(window.__opsInterval);
  window.__opsInterval = setInterval(refresh, 5000);
}

// ===== Refresh định kỳ =====
async function refresh() {
  try {
    const summary = await fetchJSON('/ops/metrics/summary');
    const xyReq  = toXY(summary.minutes, summary.req);
    const xy5xx  = toXY(summary.minutes, summary.s5xx);
    const xyBans = toXY(summary.minutes, summary.bans);

    if (chartReq && chart5xx && chartBans) {
      chartReq.data.datasets[0].data  = xyReq;
      chart5xx.data.datasets[0].data  = xy5xx;
      chartBans.data.datasets[0].data = xyBans;
      chartReq.update('none');
      chart5xx.update('none');
      chartBans.update('none');
    } else {
      // Nếu vì lý do gì chart bị null (VD: hot reload), khởi tạo lại
      await bootstrap();
      return;
    }

    const [susp, bans] = await Promise.all([
      fetchJSON('/ops/metrics/top_suspicious?limit=50'),
      fetchJSON('/ops/metrics/current_bans')
    ]);
    renderSuspicious(susp);
    renderBans(bans);
  } catch (e) {
    console.error('refresh error', e);
    // Token hết hạn/không hợp lệ → tự logout
    if (String(e).includes('401')) { logout(); }
  }
}

// ===== Nếu đã có token (đăng nhập lần trước) → vào thẳng dashboard =====
(function init() {
  if (getToken()) {
    showDash();                              // show panel trước
    setTimeout(() => {                       // cho layout ổn định rồi vẽ
      bootstrap().catch(() => logout());
    }, 0);
  } else {
    showLogin();
  }
})();
</script>

</body>
</html>
"""
    return HTMLResponse(html)


# =======================
# (2) API: SUMMARY (10 phút gần nhất)
# =======================
@router.get("/metrics/summary", summary="Timeseries req/min, 5xx/min, bans/min (10 phút gần nhất)")
def metrics_summary(_: Any = Depends(require_ops_admin)):
    """
    Trả timeseries 10 phút gần nhất:
    - minutes: list[int] bucket phút (floor(epoch_sec/60))
    - req/s5xx/bans: list[int] cùng độ dài với minutes
    UI sẽ nhân minutes * 60 * 1000 để vẽ trục thời gian thực (ms).
    """
    now_min = int(time.time() // 60)                  # phút hiện tại (epoch minutes)
    minutes = list(range(now_min - 9, now_min + 1))  # 10 bucket (cũ → mới)

    # Batch keys theo từng dòng metric
    keys_req  = [k_metric_req(m)  for m in minutes]
    keys_5xx  = [k_metric_5xx(m)  for m in minutes]
    keys_bans = [k_metric_bans(m) for m in minutes]

    # Đọc nhanh bằng MGET (trả list[bytes|None])
    v_req  = _r.mget(keys_req)
    v_5xx  = _r.mget(keys_5xx)
    v_bans = _r.mget(keys_bans)

    # Chuyển sang int (None → 0)
    to_int = lambda v: int(v) if v is not None else 0

    return {
        "minutes": minutes,
        "req":  [to_int(x) for x in v_req],
        "s5xx": [to_int(x) for x in v_5xx],
        "bans": [to_int(x) for x in v_bans]
    }


# =======================
# (3) API: Top-N IP nghi vấn (còn TTL)
# =======================
@router.get("/metrics/top_suspicious", summary="Top-N IP nghi vấn còn TTL (quét sus:ip:*:5min)")
def top_suspicious(limit: int = 50, _: Any = Depends(require_ops_admin)):
    """
    Quét các key 'sus:ip:*:5min' còn TTL, đọc score và TTL, sắp theo score giảm dần.
    Lưu ý: Đây là "điểm nghi vấn" trong cửa sổ 5 phút (middleware tăng khi vượt rate/pattern xấu/UA rỗng).
    """
    items = []
    for k in _r.scan_iter(match=b"sus:ip:*:5min", count=2000):
        k_str = k.decode("utf-8", "ignore")
        prefix, suffix = "sus:ip:", ":5min"
        if not (k_str.startswith(prefix) and k_str.endswith(suffix)):
            continue
        ip = k_str[len(prefix):-len(suffix)]
        try:
            score = int(_r.get(k) or 0)
        except Exception:
            score = 0
        ttl = _r.ttl(k)  # giây (None khi không có TTL hoặc -1/-2 theo Redis → normalize bên UI)
        items.append({"ip": ip, "score": score, "ttl_seconds": (ttl if ttl and ttl > 0 else None)})

    items.sort(key=lambda x: (x["score"], x["ttl_seconds"] or 0), reverse=True)
    return {"count": min(limit, len(items)), "items": items[:limit]}


# =======================
# (4) API: IP đang bị BAN + TTL
# =======================
@router.get("/metrics/current_bans", summary="Danh sách IP đang bị BAN + TTL")
def current_bans(_: Any = Depends(require_ops_admin)):
    """
    Liệt kê IP đang bị BAN: duyệt key 'ban:ip:*' và lấy TTL > 0.
    """
    out = []
    for k in _r.scan_iter(match=b"ban:ip:*", count=2000):
        k_str = k.decode("utf-8", "ignore")
        prefix = "ban:ip:"
        if not k_str.startswith(prefix):
            continue
        ip = k_str[len(prefix):]
        ttl = _r.ttl(k)
        if ttl and ttl > 0:
            out.append({"ip": ip, "ttl_seconds": ttl})
    out.sort(key=lambda x: x["ttl_seconds"])  # TTL tăng dần
    return {"items": out}


# =======================
# (5) EXPORT EXCEL (3 sheet)
# =======================
@router.get("/export/metrics.xlsx", summary="Xuất Excel tổng hợp (summary + suspicious + bans)")
def export_excel(minutes: int = 10, _: Any = Depends(require_ops_admin)):
    """
    Tạo file Excel (.xlsx) in-memory:
    - Sheet 'Summary': MinuteBucket, Timestamp(UTC), Requests, 5xx, Bans
    - Sheet 'TopSuspicious': IP, Score(5min), TTL(s)
    - Sheet 'CurrentBans': IP, TTL(s)
    """
    if minutes < 1 or minutes > 240:
        raise HTTPException(status_code=400, detail="minutes phải trong [1, 240]")

    now_min = int(time.time() // 60)
    mins = list(range(now_min - (minutes - 1), now_min + 1))

    keys_req  = [k_metric_req(m)  for m in mins]
    keys_5xx  = [k_metric_5xx(m)  for m in mins]
    keys_bans = [k_metric_bans(m) for m in mins]
    v_req  = _r.mget(keys_req)
    v_5xx  = _r.mget(keys_5xx)
    v_bans = _r.mget(keys_bans)

    to_int = lambda v: int(v) if v is not None else 0

    wb = Workbook()

    # --- Summary ---
    ws1 = wb.active
    ws1.title = "Summary"
    ws1.append(["MinuteBucket", "Timestamp(UTC)", "Requests", "5xx", "Bans"])
    for m, r, s5, b in zip(mins, v_req, v_5xx, v_bans):
        # Hiển thị thời gian UTC đơn giản; nếu cần theo timezone VN: dùng datetime + pytz/zoneinfo
        iso_utc = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(m * 60))
        ws1.append([m, iso_utc, to_int(r), to_int(s5), to_int(b)])

    # --- TopSuspicious ---
    ws2 = wb.create_sheet("TopSuspicious")
    ws2.append(["IP", "Score(5min)", "TTL(s)"])
    susp = []
    for k in _r.scan_iter(match=b"sus:ip:*:5min", count=2000):
        k_str = k.decode("utf-8", "ignore")
        prefix, suffix = "sus:ip:", ":5min"
        if not (k_str.startswith(prefix) and k_str.endswith(suffix)): continue
        ip = k_str[len(prefix):-len(suffix)]
        try: score = int(_r.get(k) or 0)
        except: score = 0
        ttl = _r.ttl(k)
        susp.append((ip, score, ttl if ttl and ttl > 0 else None))
    susp.sort(key=lambda x: (x[1], x[2] or 0), reverse=True)
    for ip, score, ttl in susp:
        ws2.append([ip, score, ttl])

    # --- CurrentBans ---
    ws3 = wb.create_sheet("CurrentBans")
    ws3.append(["IP", "TTL(s)"])
    bans = []
    for k in _r.scan_iter(match=b"ban:ip:*", count=2000):
        k_str = k.decode("utf-8", "ignore")
        prefix = "ban:ip:"
        if not k_str.startswith(prefix): continue
        ip = k_str[len(prefix):]
        ttl = _r.ttl(k)
        if ttl and ttl > 0: bans.append((ip, ttl))
    bans.sort(key=lambda x: x[1])
    for ip, ttl in bans:
        ws3.append([ip, ttl])

    # Gói vào bytes và trả về dưới dạng streaming
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    headers = {"Content-Disposition": 'attachment; filename="ops_metrics.xlsx"'}
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
