# utils/cache.py
# -*- coding: utf-8 -*-

import json                                   # Serialize object -> JSON
import hashlib                                # Tạo hash từ params
from typing import Any                        # Kiểu tổng quát
from fastapi.encoders import jsonable_encoder # Biến đổi object/Pydantic -> JSON-serializable
from security.redis_client import get_redis

redis_cache = get_redis()                              # Client Redis dùng chung

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
    Trả về object Python (đã json.loads), None nếu miss.
    """
    b = redis_cache.get(key)                     # GET bytes từ Redis
    if not b:
        return None                     # miss
    try:
        return json.loads(b)            # parse JSON -> object
    except Exception:
        return None

def set_cache(key: str, value: Any, ttl: int = 60) -> None:
    """
    Lưu object vào Redis (JSON) với TTL giây (TTL: Time To Live).  
    Mặc định TTL = 60 giây. (thời gian cache còn hiệu lực trong redis trước khi nó bị xoá)
    """
    try:
        data = json.dumps(jsonable_encoder(value), ensure_ascii=False).encode("utf-8")  # Bảo đảm serializable
        redis_cache.setex(key, ttl, data)        # SETEX (value, TTL)
    except Exception:
        pass

def delete_by_prefix(prefix: str) -> int:
    """
    Xóa các key cache theo tiền tố (dùng SCAN để an toàn).  
    Trả số lượng key đã xóa. Tránh lạm dụng ở dữ liệu rất lớn.  
    Dùng khi có thay đổi dữ liệu liên quan (create/update/delete), cần xóa các cache cũ.
    """
    count = 0
    pattern = f"{prefix}*".encode("utf-8")
    # scan_iter chạy incremental, không khóa Redis lâu
    for k in redis_cache.scan_iter(match=pattern, count=500):
        redis_cache.delete(k)
        count += 1
    return count

def clear_all_cache() -> int:
    """
    Xoá toàn bộ cache (cẩn thận khi dùng).
    Trả về số key đã xoá.
    """
    count = 0
    pattern = "cache:*".encode("utf-8")
    for k in redis_cache.scan_iter(match=pattern, count=500):
        redis_cache.delete(k)
        count += 1
    return count