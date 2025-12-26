import json                                   # Serialize object -> JSON
import hashlib                                # Tạo hash từ params
import time
from typing import Any, Optional              # Type hint
from typing import Any                        # Kiểu tổng quát
from fastapi.encoders import jsonable_encoder # Biến đổi object/Pydantic -> JSON-serializable
from security.redis_client import get_redis
from log.system_log import system_logger

redis_cache = get_redis()                     # Client Redis dùng chung

# Throttle log: chỉ log tối đa 1 lần mỗi LOG_EVERY_SECONDS khi Redis đang lỗi
_LOG_EVERY_SECONDS = 1.0                      # 1 giây log tối đa 1 lần
_last_redis_log_ts = 0.0                      # Timestamp lần log gần nhất


def _log_redis_error(ex: Exception, op: str) -> None:
    """
    Log lỗi Redis có throttle để tránh spam log khi Redis down.
    - op: tên thao tác (GET/SETEX/SCAN/DEL...)
    """
    global _last_redis_log_ts
    now = time.time()
    if now - _last_redis_log_ts >= _LOG_EVERY_SECONDS:
        _last_redis_log_ts = now
        system_logger.warning("Redis cache đang gặp lỗi %s: %s", op, ex)

def make_cache_key(prefix: str, params: dict) -> str:
    """
    Tạo key cache ổn định từ prefix + hash tham số (đảm bảo không dài quá).  
    Có tác dụng cho việc truy vấn các giá trị từ cache.  
    Tham số:
    - prefix: tiền tố key (ví dụ: "users:list")  
    - params: dict các tham số (sẽ được JSON hóa và hash)  
    Trả về key dạng: cache:{prefix}:{sha1_hexdigest}  
    Ví dụ: cache:users:list:ab34f5e6...  
    """
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True).encode("utf-8")  # JSON theo thứ tự khóa
    digest = hashlib.sha1(raw).hexdigest()                                         # SHA1 cho gọn
    return f"cache:{prefix}:{digest}"

def get_cache(key: str) -> Any:
    """
    Lấy dữ liệu đã cache từ Redis theo key đã tạo.  
     - Redis OK: trả object Python
     - Redis down: trả None (coi như cache miss), đồng thời log (throttle)
    """
    try:
        b = redis_cache.get(key)                # GET bytes từ Redis
    except Exception as ex:
        _log_redis_error(ex, "GET")             # log lỗi Redis
        return None                             # fail-open: coi như cache miss

    if not b:
        return None                             # không có key -> cache miss

    try:
        # Lưu ý: b là bytes (do decode_responses=False)
        # json.loads nhận str, nên decode utf-8 trước
        return json.loads(b.decode("utf-8"))    # parse JSON -> object
    except Exception as ex:
        # Dữ liệu cache hỏng/khác format -> coi như miss
        system_logger.warning("Cache decode/loads failed for key=%s: %s", key, ex)
        return None

def set_cache(key: str, value: Any, ttl: int = 60) -> None:
    """
    Lưu object vào Redis (JSON) với TTL giây (TTL: Time To Live).  
    Mặc định TTL = 60 giây. (thời gian cache còn hiệu lực trong redis trước khi nó bị xoá)
    - Redis OK: setex thành công
    - Redis down: bỏ qua, không throw, log (throttle)
    """
    try:
        # jsonable_encoder giúp object/Pydantic => JSON serializable
        payload_obj = jsonable_encoder(value)
        data = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")  # encode -> bytes
        redis_cache.setex(key, ttl, data)            # SETEX lưu data với TTL
    except Exception as ex:
        _log_redis_error(ex, "SETEX")                # log lỗi Redis
        return

def delete_by_prefix(prefix: str) -> int:
    """
    Xóa các key cache theo tiền tố (dùng SCAN để an toàn).  
    Trả số lượng key đã xóa. Tránh lạm dụng ở dữ liệu rất lớn.  
    Dùng khi có thay đổi dữ liệu liên quan (create/update/delete), cần xóa các cache cũ.
    - Redis OK: xóa theo scan_iter
    - Redis down: trả 0, log (throttle)
    """
    count = 0                                       # đếm số key đã xoá
    pattern = f"{prefix}*".encode("utf-8")          # redis raw trả bytes, match bytes cho nhất quán

    try:
        # scan_iter là generator, Redis down có thể throw ngay khi gọi hoặc khi iterate
        for k in redis_cache.scan_iter(match=pattern, count=500):
            try:
                redis_cache.delete(k)               # xóa key
                count += 1                          # tăng count
            except Exception as ex:
                _log_redis_error(ex, "DEL")         # log lỗi delete
                # fail-open: bỏ qua key lỗi, tiếp tục
                continue
    except Exception as ex:
        _log_redis_error(ex, "SCAN")                # log lỗi scan
        return 0                                    # fail-open: coi như không xoá được gì

    return count                                    # trả số key đã xóa

def clear_all_cache() -> int:
    """
    Xoá toàn bộ cache (cẩn thận khi dùng).
    Trả về số key đã xoá.
    - Redis down: trả 0, log
    """
    count = 0                                       # số key xóa được
    pattern = "cache:*".encode("utf-8")             # match bytes

    try:
        for k in redis_cache.scan_iter(match=pattern, count=500):
            try:
                redis_cache.delete(k)
                count += 1
            except Exception as ex:
                _log_redis_error(ex, "DEL")
                continue
    except Exception as ex:
        _log_redis_error(ex, "SCAN")
        return 0

    return count