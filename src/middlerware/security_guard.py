import time
from fastapi import Request
from fastapi.responses import JSONResponse

from services.email_services import InternalEmailSender
from security.redis_client import get_redis
from security.rate_limiter import rl_check
from security.config import TTL, RATE, BUCKET_BY_PATH, BAN_RULE, SUSPICIOUS_PATTERNS
from security.keyspace import (
    k_metric_req, k_metric_5xx, k_metric_bans,
    k_ban_ip, k_ban_notify, k_suspicious
)
from utils.utils import _norm_ip


# Khai báo dịch vụ mail
email_services = InternalEmailSender()


redis_client = get_redis()                                 # Tạo Redis client dùng chung

def _is_banned(ip: str) -> bool:
    """
    Kiểm tra 1 IP có đang bị ban hay không với key định nghĩa trước  
    Nếu trong cache có key này và TTL vẫn đang tồn tại thì có nghĩa là đang bị ban
    """
    # TTL > 0 nghĩa là key tồn tại và còn hạn; TTL -1 không có TTL, -2 không có key
    return redis_client.ttl(k_ban_ip(ip)) > 0

def _ban_now(ip: str) -> None:
    """
    Đặt BAN ngay lập tức cho IP:
    - Ghi key `ban:ip:<ip>` với TTL = TTL.ban_seconds
    - Tăng metric bans theo phút để quan sát tần suất hệ thống đang chặn.
    """
    # Ghi key ban với TTL value "1" (chỉ là flag) vào Redis
    redis_client.setex(k_ban_ip(ip), TTL.ban_seconds, b"1") 
    now_min = int(time.time() // 60)                     # Bucket phút hiện tại
    # Tăng đếm số ban/phút để quan sát
    redis_client.incr(k_metric_bans(now_min))                    # Đếm số ban/phút
    redis_client.expire(k_metric_bans(now_min), TTL.metric_minute)            # TTL 3 phút cho counter phút (tự dọn sau TTL.metric_minute)

def _mark_suspicious(ip: str) -> int:
    """
    Tăng đếm 'nghi vấn' cho IP trong 5 phút; trả về giá trị sau tăng.
    Nếu điểm nghi vấn vượt ngưỡng, sẽ do caller quyết định có BAN hay không.
    Mỗi lần tăng sẽ đặt TTL lại 5 phút (nên cứ tăng là giữ nguyên thời gian sống).
    """
    key = k_suspicious(ip)    # Tạo khoá điểm nghi vấn của IP trong cửa sổ 5 phút
    val = redis_client.incr(key)           # Tăng 1 giá trị (atomic trên Redis), nếu key này chưa có thì Redis tự tạo mới với giá trị 1
    if val == 1:
        redis_client.expire(key, TTL.suspicious_5min)      # Nếu vừa tạo, đặt TTL 300s (5 phút)
    
    return int(val)

def _notify_ban_once(ip: str, reason: str, path: str, ua: str) -> None:
    """
    Gửi email CHỈ LẦN ĐẦU khi IP bị BAN trong 1 chu kỳ BAN.  
    Dùng khoá 'ban:notify:<ip>' (SETNX) để chống spam email.
    """
    k_notify = k_ban_notify(ip)        # Tạo khoá chặn email gửi lặp lại
    if redis_client.setnx(k_notify, b"1"):         # True nếu chưa có -> lần đầu trong chu kỳ
        redis_client.expire(k_notify, TTL.ban_seconds)      # # TTL trùng TTL ban

        subject = f"[ALERT] BAN IP {ip}"             # Tiêu đề email

        # Gửi email
        email_services.send_mail_alert(to_email="tvc_adm_it@terumo.co.jp",subject_mail=subject, 
                                        ip=ip, reason=reason, path_api=path, user_agent=ua, time_ban=TTL.ban_seconds)

async def security_guard(request: Request, call_next):
    """
    Middleware:
    - Đếm metric tổng theo phút (metric:req:<minute>).
    - Nếu IP đang BAN: gửi email (1 lần/chu kỳ) & trả 403.
    - Nếu vượt rate/ghi nhận nghi vấn: chỉ tăng điểm, CHO QUA; chỉ BAN khi điểm ≥ ngưỡng.
    - Sau handler: nếu 5xx -> đếm metric 5xx.
    """

    # 1) Lấy IP client (trong Docker trực tiếp sẽ là IP client. Nếu sau reverse-proxy, nên đọc X-Forwarded-For và xác thực trusted proxies)
    is_ip, client_ip = _norm_ip(request.client.host if request.client else "-")

    # Nếu ko nhận được địa chỉ IP thì trả về lỗi
    if not is_ip:
        return JSONResponse(                                # Trả 400
            {"detail": "Không tìm thấy địa chỉ ip"},
            status_code=400
        )

    # 2) Đếm tổng request theo phút 
    # Lấy thời gian phút hiện tại
    now_min = int(time.time() // 60)

    # Đếm tổng req/min để quan sát
    redis_client.incr(k_metric_req(now_min))
    redis_client.expire(k_metric_req(now_min), TTL.metric_minute)

    # 3) Nếu IP đang bị BAN -> gửi email 1 lần/chu kỳ & trả 403 ngay (không vào handler)
    if _is_banned(client_ip):
        _notify_ban_once(
            ip=client_ip,
            reason="Thiết bị đang trong trạng thái bị chặn, nhưng vẫn cố truy cập vào hệ thống",    # Lý do: IP ban vẫn cố truy cập
            path=str(request.url.path),
            ua=request.headers.get("user-agent", "")
        )

        return JSONResponse(                                # Trả 403 (Forbidden)
            {"detail": "Truy vấn của bạn hiện tại đang bị chặn vì nghi ngờ tấn công"},
            status_code=403
        )

    # 4) Rate-limit 'global' (sliding-window): nếu vượt limit -> tăng điểm nghi vấn; nếu đạt ngưỡng -> BAN + email + 403
    ok, _ = rl_check(client_ip, "global", **RATE["global"])
    if not ok:
        sus = _mark_suspicious(client_ip)                   # Tăng điểm nghi vấn 5 phút
        if sus >= BAN_RULE["suspicious_per_5min"]:          # Nếu điểm ≥ ngưỡng -> BAN
            _ban_now(client_ip)
            _notify_ban_once(
                ip=client_ip,
                reason=f"Số lượng truy vấn vào hệ thống liên tục trong thời gian 5 phút vượt ngưỡng cho phép: {sus}",  # Lý do ban
                path=str(request.url.path),
                ua=request.headers.get("user-agent", "")
            )

            return JSONResponse({"detail": "Bạn đã truy vấn liên tục trong thời gian ngắn, hệ thống sẽ giới hạn truy cập của bạn."}, status_code=403)
        # CHƯA tới ngưỡng BAN -> CHO QUA, để handler vẫn hoạt động bình thường

    # 5) Rate-limit theo bucket nhạy cảm (ví dụ /login, /upload)
    bucket = BUCKET_BY_PATH.get(request.url.path)           # Tìm xem path thuộc bucket nào
    if bucket:
        ok2, _ = rl_check(client_ip, bucket, **RATE[bucket])
        if not ok2:
            sus = _mark_suspicious(client_ip)
            if sus >= BAN_RULE["suspicious_per_5min"]:
                _ban_now(client_ip)
                _notify_ban_once(
                    ip=client_ip,
                    reason=f"Số lượt truy vấn vào đường dẫn nhạy cảm ({bucket}) trong 5 phút vượt ngưỡng cho phép: {sus}",
                    path=str(request.url.path),
                    ua=request.headers.get("user-agent", "")
                )
                return JSONResponse({"detail": "Bạn đã truy vấn liên tục vào hệ thống trong thời gian ngắn, hệ thống sẽ giới hạn truy cập của bạn."}, status_code=403)
            # CHƯA BAN -> CHO QUA

    # 6) Heuristics đơn giản: URL có pattern xấu -> tăng điểm; nếu quá ngưỡng -> BAN
    url_lc = (request.url.path + "?" + (request.url.query or "")).lower()
    if any(p in url_lc for p in SUSPICIOUS_PATTERNS):
        sus = _mark_suspicious(client_ip)
        if sus >= BAN_RULE["suspicious_per_5min"]:
            _ban_now(client_ip)
            _notify_ban_once(
                ip=client_ip,
                reason=f"Suspicious pattern in URL (score={sus})",
                path=str(request.url.path),
                ua=request.headers.get("user-agent", "")
            )
            return JSONResponse({"detail": "Truy vấn của bạn có chứa các từ ngữ bất thường. Hệ thống sẽ giới hạn truy cập của bạn."}, status_code=403)

    # UA rỗng/ngắn -> tăng điểm; nếu quá ngưỡng -> BAN
    ua = request.headers.get("user-agent", "")
    if not ua or len(ua) < 6:                               # UA quá ngắn thường là bot/thư viện quét
        sus = _mark_suspicious(client_ip)
        if sus >= BAN_RULE["suspicious_per_5min"]:
            _ban_now(client_ip)
            _notify_ban_once(
                ip=client_ip,
                reason=f"Empty/short User-Agent (score={sus})",
                path=str(request.url.path),
                ua=ua
            )
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

    # 7) Không có lý do BAN -> Cho request đi qua hoàn toàn, không can thiệp header/status/body
    response = await call_next(request)

    # 8) Sau handler: nếu server trả 5xx -> ghi nhận metric 5xx theo phút (để quan sát)
    if 500 <= response.status_code < 600:
        redis_client.incr(k_metric_5xx(now_min))
        redis_client.expire(k_metric_5xx(now_min), TTL.metric_minute)

    return response
