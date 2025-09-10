from typing import Tuple                 # # Kiểu trả về (bool, int)
from security.redis_client import get_redis      # # Hàm tạo client Redis

"""
Rate Limiter (dựa trên Redis + Lua script)
- Giới hạn số request trong "cửa sổ" thời gian gần nhất (sliding window). Có nghĩa là mỗi ip chỉ được gửi tối đa N request trong M giây gần nhất.
- Cách làm: dùng Redis Sorted Set (ZSET) để lưu timestamp (ms) của các request, với score = value = timestamp (ms).
- Mỗi lần có request mới:
    1. Thêm timestamp hiện tại vào ZSET.
    2. Xoá các timestamp cũ hơn (ngoài cửa sổ M giây).
    3. Đếm số phần tử còn lại trong ZSET (số request trong cửa sổ).
    4. So sánh với giới hạn N: nếu <= N thì cho phép, ngược lại từ chối.
- Để tránh ZSET quá lớn, ta set TTL tự dọn rác (gấp đôi cửa sổ).
- Viết bằng Lua script để chạy atomically trên Redis.
Redis rất nhanh, lệnh atomic khi gói vào Lua (không race giữa nhiều instance/app).
Có TTL (Time To Live: Thời gian sống) gốc (EXPIRE/PEXPIRE) để tự dọn key khi nguội. 

"""

# Lua "sliding window" dùng TIME của Redis (Để đảm bảo thời gian nhất quán) và member unique (now:seq)
SLIDING_WINDOW_LUA = r"""
-- KEYS[1] : key ZSET cho IP+bucket, ví dụ: rl:global:127.0.0.1
-- ARGV[1] : window_ms (độ dài cửa sổ M 000 ms = M s)
-- ARGV[2] : limit (số request tối đa trong cửa sổ: N request)

local key       = KEYS[1]

-- Lấy thời gian chuẩn từ Redis (tránh lệch giờ app, mỗi thiết bị lệch giờ sẽ khiến lệch theo, vì vậy tất cả lấy chung 1 nơi là redis server):
-- TIME trả { seconds, microseconds }
local t         = redis.call('TIME')
local now       = (t[1] * 1000) + math.floor(t[2] / 1000)

local window    = tonumber(ARGV[1])     
local limit     = tonumber(ARGV[2])

-- Tạo "member unique" để tránh va chạm khi có nhiều request trong cùng 1 ms:
-- Dùng counter riêng cho key, có TTL(Time To Live), để reset khi key nguội.
local seq_key   = key .. ':seq'
local seq       = redis.call('INCR', seq_key)
if seq == 1 then
  redis.call('PEXPIRE', seq_key, window * 2)
end
local member    = tostring(now) .. ':' .. tostring(seq)

-- (Bước 1) Ghi dấu request hiện tại (score = now, member = now:seq)
redis.call('ZADD', key, now, member)

-- (Bước 2) Cắt bỏ mọi dấu đã vượt ra khỏi cửa sổ [now-window, now]
-- (ở đây loại bỏ <= now - window; tức ta giữ (now-window, now])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- (Bước 3) Đếm số request còn lại trong cửa sổ
local count = redis.call('ZCARD', key)

-- (Bước 4) Đặt TTL để key tự sạch khi nguội (không hoạt động sẽ tự động xóa các key hết hạn sau thời gian TTL)
redis.call('PEXPIRE', key, window * 2)

-- (Bước 5) Kiểm tra xem số lượng requets đã vượt qua giới hạn cho phép chưa: 1=allow, 0=deny; kèm count để log/giám sát
if count <= limit then
  return {1, count}
else
  return {0, count}
end
"""

# # Biên dịch & cache script trên Redis (tăng hiệu năng)
_redis = get_redis()
SLIDING_WINDOW_SCRIPT = _redis.register_script(SLIDING_WINDOW_LUA)

# # Tạo tên key rate-limit theo IP + nhóm (bucket)
def rl_key(ip: str, bucket: str) -> str:
    """
    Tạo các key tương ứng để kiểm soát mỗi lần gọi  
    Vì mỗi router sẽ có những ngưỡng khác nhau nên cần truyền bucket để phân loại.  
    Ví dụ: các api bucket: golbal sẽ có ngưỡng giới hạn 120 request/ 1 phút  
    Các api bucket: login/upload nghiêm ngặt hơn có ngưỡng 60 request/ 1 phút
    """
    return f"rl:{bucket}:{ip}"

# # Kiểm tra rate limit: trả (allowed, current_count)
def rl_check(ip: str, bucket: str, window_ms: int, limit: int) -> Tuple[bool, int]:
    """
    Kiểm tra 1 request khi gọi api  
    - ip: địa chỉ ip gọi api  
    - bucket: phân loại api  
    - window_ms: Thời gian giới hạn 
    - limit: Số request giới hạn trong window_ms  
    Giả sử window_ms = 60_000 (60 giây), limit = 120 (tức ~2 rps trung bình).  
    Kiểm tra ip này có truy cập 1 api có bucket như trên vượt quá 120 request trong vòng 60s không

    """
    res = SLIDING_WINDOW_SCRIPT(              # # Chạy Lua atomically
        keys=[rl_key(ip, bucket)],            
        args=[window_ms, limit]
    )
    allowed = (res[0] == 1)                   # # 1 -> allowed
    count = int(res[1])                       # # số request hiện tại trong cửa sổ
    return allowed, count                     # # Trả kết quả
