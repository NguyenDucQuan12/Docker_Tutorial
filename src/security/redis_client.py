

import os                 # Đọc biến môi trường để lấy REDIS_URL
import redis              # Thư viện redis-py (pip install redis)
"""
Đầu tiên cần chạy Redis server (có thể chạy local hoặc Docker).  
Với Docker: `docker run -p 6379:6379 -it redis:latest`

Hoặc chi tiết hơn: `docker run -d --name my-redis -p 6379:6379 -v ./redis-data:/data -e TZ=Asia/Ho_Chi_Minh redis:latest --appendonly yes`
Cách chạy thứ 2 này sẽ lưu dữ liệu Redis ra thư mục redis-data trên host, tránh mất dữ liệu khi container dừng. (nhớ tao thư mục redis-data trước khi chạy lệnh)

Sau đó, cài thư viện redis-py: `pip install redis`
Xem thêm tài liệu: https://pypi.org/project/redis/
Lưu ý: redis-py mặc định trả về bytes, bạn có thể decode thành str (decode_responses=True) nhưng sẽ chậm hơn.
Ở đây ta để decode_responses=False để nhận bytes, nhanh hơn, và tự decode khi cần.
Việc kết nối Redis nên dùng connection pool để tái sử dụng kết nối TCP, giúp hiệu năng ổn định trong môi trường nhiều request.

Hàm get_redis() trả về đối tượng redis.Redis đã được cấu hình connection pool.

"""

# # Hàm trả về đối tượng Redis dùng connection pool (tái sử dụng TCP)
def get_redis():
    """
    Tạo client Redis từ REDIS_URL (ví dụ: redis://redis:6379/0).
    Dùng connection pool để hiệu năng ổn định ở môi trường nhiều request.
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")  # REDIS_URL chuẩn trong Docker: redis://redis:6379/0

    pool = redis.ConnectionPool.from_url(                     # # Tạo pool kết nối từ URL
        url,
        socket_keepalive=True,                                # # Giữ kết nối lâu dài (keepalive)
        socket_timeout=2.0,                                   # # Timeout thao tác (giây)
        socket_connect_timeout=2.0,                           # # Timeout kết nối (giây)
        max_connections=200,                                  # # Giới hạn số kết nối đồng thời từ app
        health_check_interval=30,                             # # Ping định kỳ phát hiện kết nối chết
        decode_responses=False                                # # Trả về bytes (nhanh, ít decode)
    )
    return redis.Redis(connection_pool=pool)                  # # Tạo client trỏ vào pool và trả về
