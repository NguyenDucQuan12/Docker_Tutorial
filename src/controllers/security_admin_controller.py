from typing import Any, List, Optional
from fastapi import HTTPException, status
from schemas.schemas import UserAuth
import os
import time

from log.system_log import system_logger
from security.redis_client import get_redis                     
from security.config import TTL                       
from security.keyspace import (                                 
    k_ban_ip, k_ban_notify, k_suspicious
)
from utils.utils import _norm_ip
from utils.constants import *

# ------------ Lấy giá trị cấu hình từ biến môi trường ------------
REDIS_SCAN_COUNT  = int(os.getenv("REDIS_SCAN_COUNT", 2000))   # Số key/scan_iter vòng lặp
REDIS_BATCH_SIZE  = int(os.getenv("REDIS_BATCH_SIZE", 500))    # Số lệnh trong 1 batch pipeline
REDIS_RETRY       = int(os.getenv("REDIS_RETRY", 2))           # Số lần retry khi pipeline lỗi
REDIS_RETRY_SLEEP = float(os.getenv("REDIS_RETRY_SLEEP", 0.05))# Ngủ giữa hai lần retry (giây)


# Tạo client Redis dùng chung
redis_client = get_redis()



def _exec_with_retry(pipe):
    """
    Thực thi pipeline Redis với retry ngắn (đối phó timeouts/disconnect tạm thời).
    - Thành công: trả list kết quả.
    - Thất bại sau retry: ném HTTP 500 để thấy rõ hệ thống có sự cố.
    """
    for attempt in range(REDIS_RETRY + 1):
        try:
            return pipe.execute()
        except Exception as e:
            system_logger.warning("Truy vấn thông tin với Redis thất bại (Thử lại %s/%s)", attempt + 1, REDIS_RETRY + 1)
            if attempt < REDIS_RETRY:
                time.sleep(REDIS_RETRY_SLEEP)
            else:
                system_logger.exception("Không thể thao tác truy vấn dữ liệu với Redis, hệ thống xuất hiện lỗi: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                            "Message": f"Không thể thao tác Redis (pipeline failed): {e}"
                        },
                )

# ===== Helper =====

def _ban_set(ip: str, ttl: Optional[int] = None) -> None:
    """
    Đặt cờ BAN cho IP với TTL (giây).
    - Nếu ttl=None -> dùng TTL mặc định từ cấu hình (TTL.ban_seconds).
    - Xoá khoá notify để nếu ban mới -> email cảnh báo ở middleware có thể gửi lại (tuỳ logic bạn muốn).
    """
    try:
        t = int(ttl or TTL.ban_seconds)         # TTL đầu vào; nếu None dùng mặc định
        if t <= 0:
            raise ValueError("Thời gian sống của cache phải là số dương") # TTL âm/0 là không hợp lệ

        # Pipeline đảm bảo atomic nhóm lệnh + giảm round-trip
        with redis_client.pipeline(transaction=True) as p:
            p.setex(k_ban_ip(ip), t, b"1")      # Ghi cờ BAN với TTL (value=1)
            p.delete(k_ban_notify(ip))          # Xoá notify để lần BAN sau có thể gửi cảnh báo lại
            _exec_with_retry(p)                 # Thực thi với retry ngắn

    except HTTPException:
        # Giữ nguyên nếu _exec_with_retry đã ném HTTPException phù hợp
        raise
    except Exception as e:
        system_logger.exception("BAN thất bại địa chỉ %s với lý do: %s", ip, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                    "Message": f"Không thể ghi trạng thái BAN vào Redis: {str(e)}"
                },
        )

def _ban_ttl(ip: str) -> int:
    """
    Lấy TTL còn lại (giây) của IP đang BAN.
    - Trả về -2 nếu không có key; -1 nếu có key nhưng không TTL (không kỳ vọng vì ta luôn set TTL).
    - Bọc lỗi Redis → HTTP 500.
    """
    try:
        return int(redis_client.ttl(k_ban_ip(ip)))
    except Exception as e:
        system_logger.exception("Truy vấn thời gian BAN của địa chỉ %s thất bại: %s", ip, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                    "Message": f"Không thể truy vấn TTL từ Redis: {str(e)}"
                }
        )

def _unban(ip: str) -> int:
    """
    Gỡ BAN (xoá key ban:ip:<ip>).
    - Redis trả 1 nếu xoá được, 0 nếu không tồn tại.
    - Bọc lỗi Redis → HTTP 500.
    """
    try:
        return int(redis_client.delete(k_ban_ip(ip)))
    except Exception as e:
        system_logger.exception("Không thể gỡ ban địa chỉ %s: %s", ip, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                    "Message": f"Không thể xoá trạng thái BAN từ Redis: {str(e)}"
                }
        )

class Security_Admin_Controller:
    """
    Controller để xử lý các vấn đê liên quan đến quản trị bảo mật (Security Admin)
    """

    def ban_now(user_info: UserAuth, ip: str, ttl: Optional[int] = None) -> None:
        """
        Đặt BAN ngay 1 IP:
        - ip: chuỗi IPv4/IPv6
        - ttl: số giây; nếu None dùng TTL.ban_seconds
        """
        # Kiểm tra định dạng IP đơn giản
        is_ip, norm_ip = _norm_ip(ip_raw = ip)

        if (not is_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "Message": f"Địa chỉ IP không hợp lệ: {ip}",
                })
        
        # Kiểm tra quyền hạn (bắt buộc phải là Admin/Boss)
        if not (user_info["Privilege"] in HIGH_PRIVILEGE_LIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "Message": f"Bạn không có quyền thực hiện thao tác này",
                }
            )
        
        # Đặt ban
        _ban_set(norm_ip, ttl)

        return {"IP": ip, "Thời gian chặn": int(ttl or TTL.ban_seconds), "Trạng thái": "banned"}
    
    def unban(user_info: UserAuth, ip: str) -> int:
        """
        Gỡ ban 1 IP:
        - Trả deleted=1 nếu xoá được key ban:ip:<ip>, 0 nếu không tồn tại
        """
        # Kiểm tra định dạng IP đơn giản
        is_ip, norm_ip = _norm_ip(ip_raw = ip)

        if (not is_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "Message": f"Địa chỉ IP không hợp lệ: {ip}",
                })
        
        # Kiểm tra quyền hạn (bắt buộc phải là Admin/Boss)
        if not (user_info["Privilege"] in HIGH_PRIVILEGE_LIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "Message": f"Bạn không có quyền thực hiện thao tác này",
                }
            )
        
        deleted = _unban(norm_ip)
        return {"ip": ip, "deleted": int(deleted)}

    def unban_list(user_info: UserAuth, ips: List[str]):
        """
        Gỡ BAN cho nhiều IP.
        - Bỏ qua IP không hợp lệ (ghi 'error': 'invalid_ip' trong details)
        - Dùng pipeline theo lô + retry để tối ưu
        - Trả {"done": n, "total": m, "details":[...]}
        """
        # Kiểm tra quyền hạn (bắt buộc phải là Admin/Boss)
        if not (user_info["Privilege"] in HIGH_PRIVILEGE_LIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "Message": f"Bạn không có quyền thực hiện thao tác này",
                }
            )
        
        details: List[dict] = []
        done = 0

        # Gom IP hợp lệ vào danh sách để pipeline theo lô
        valid_ips: List[str] = []

        for ip in ips:
            # Kiểm tra định dạng IP đơn giản
            is_ip, norm_ip = _norm_ip(ip_raw = ip)

            if is_ip:
                valid_ips.append(norm_ip)

        # Chia lô theo REDIS_BATCH_SIZE để tránh pipeline quá dài
        idx = 0
        while idx < len(valid_ips):
            batch = valid_ips[idx: idx + REDIS_BATCH_SIZE]
            idx += REDIS_BATCH_SIZE

            # Pipeline xoá theo lô
            with redis_client.pipeline(transaction=True) as p:
                for ip in batch:
                    p.delete(k_ban_ip(ip))
                results = _exec_with_retry(p)   # 500 nếu Redis sự cố

            # Ghép kết quả xoá cho từng IP trong batch
            for ip, r in zip(batch, results):
                d = int(r)
                details.append({"ip": ip, "deleted": d})
                done += d


        return {"done": done, "total": len(ips), "details": details}
    
    def get_ban_ttl (user_info: UserAuth, ip: str):
        """
        Trả về thời gian đang bị ban còn lại của ip
        """
        # Kiểm tra định dạng IP đơn giản
        is_ip, norm_ip = _norm_ip(ip_raw = ip)

        if (not is_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "Message": f"Địa chỉ IP không hợp lệ: {ip}",
                })
        
        # Kiểm tra quyền hạn (bắt buộc phải là Admin/Boss)
        if not (user_info["Privilege"] in HIGH_PRIVILEGE_LIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "Message": f"Bạn không có quyền thực hiện thao tác này",
                }
            )

        # Truy vấn thời gian còn lại
        ttl = _ban_ttl(norm_ip)
        return {"ip": ip, "ttl_seconds": ttl}
    
    def get_top_suspicious(user_info: UserAuth, limit:int):
        """
        Liệt kê top-N IP nghi vấn (cửa sổ 5 phút — key 'sus:ip:*:5min').
        - Quyền 403 nếu thiếu
        - Dùng SCAN + pipeline GET/TTL để tăng tốc
        - Sắp theo score giảm dần, rồi TTL (có → ưu tiên)
        - Trả {"count": ..., "items":[{"ip","score","ttl_seconds"}]}
        """

        # Kiểm tra quyền hạn (bắt buộc phải là Admin/Boss)
        if not (user_info["Privilege"] in HIGH_PRIVILEGE_LIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "Message": f"Bạn không có quyền thực hiện thao tác này",
                }
            )
        
        items: List[dict] = []
        keys: List[Any] = []
        
        try:
            # Thu thập key theo lô qua SCAN (không block như KEYS)
            for k in redis_client.scan_iter(match="sus:ip:*:5min", count=REDIS_SCAN_COUNT):
                keys.append(k)

            if not keys:
                return {"count": 0, "items": []}

            # Pipeline GET + TTL cho toàn bộ keys để giảm round-trip
            with redis_client.pipeline(transaction=False) as p:
                for k in keys:
                    p.get(k)
                    p.ttl(k)
                raw = _exec_with_retry(p)   # [GET(k1), TTL(k1), GET(k2), TTL(k2), ...]

            # Parse kết quả theo cặp (GET, TTL)
            it = iter(raw)
            for k in keys:
                try:
                    score_raw = next(it)
                    ttl_raw   = next(it)
                except StopIteration:
                    break

                # k có thể là bytes hoặc str tuỳ cấu hình decode_responses → chuẩn hoá sang str
                k_str = k.decode("utf-8", "ignore") if isinstance(k, (bytes, bytearray)) else str(k)
                prefix, suffix = "sus:ip:", ":5min"
                if not (k_str.startswith(prefix) and k_str.endswith(suffix)):
                    continue  # bảo vệ an toàn khi có key rác

                ip_str = k_str[len(prefix):-len(suffix)]
                try:
                    score = int(score_raw or 0)
                except Exception:
                    score = 0

                ttl_val = int(ttl_raw) if (ttl_raw is not None) else -2
                items.append({
                    "ip": ip_str,
                    "score": score,
                    "ttl_seconds": (ttl_val if ttl_val > 0 else None)
                })

            # Sắp xếp: score giảm dần, TTL có giá trị ưu tiên hơn (None coi như 0)
            items.sort(key=lambda x: (x["score"], x["ttl_seconds"] or 0), reverse=True)
            return {"count": min(limit, len(items)), "items": items[:limit]}

        except HTTPException:
            raise  # giữ nguyên HTTP 500 do _exec_with_retry ném ra
        except Exception as e:
            system_logger.exception(f"Không thể truy vấn danh sách nghi vấn: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"Message": f"Không thể truy vấn danh sách nghi vấn: {str(e)}"},
            )
    
    def get_current_ban(user_info: UserAuth):
        """
        Lấy danh sách các ip đang bị ban
        """
        # Kiểm tra quyền hạn (bắt buộc phải là Admin/Boss)
        if not (user_info["Privilege"] in HIGH_PRIVILEGE_LIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "Message": f"Bạn không có quyền thực hiện thao tác này",
                }
            )
        
        out: List[dict] = []
        keys: List[Any] = []

        try:
            for k in redis_client.scan_iter(match="ban:ip:*", count=REDIS_SCAN_COUNT):
                keys.append(k)

            if not keys:
                return {"items": []}

            # Hỏi TTL hàng loạt bằng pipeline (giảm round-trip)
            with redis_client.pipeline(transaction=False) as p:
                for k in keys:
                    p.ttl(k)
                ttls = _exec_with_retry(p)  # [TTL(k1), TTL(k2), ...]

            for k, ttl in zip(keys, ttls):
                # Chuẩn hoá key về str
                k_str = k.decode("utf-8", "ignore") if isinstance(k, (bytes, bytearray)) else str(k)
                prefix = "ban:ip:"
                if not k_str.startswith(prefix):
                    continue

                ip_str = k_str[len(prefix):]
                try:
                    ttl_val = int(ttl)
                except Exception:
                    continue

                if ttl_val > 0:
                    out.append({"ip": ip_str, "ttl_seconds": ttl_val})

            out.sort(key=lambda x: x["ttl_seconds"])  # TTL nhỏ (sắp hết) đứng trước
            return {"items": out}

        except HTTPException:
            raise
        except Exception as e:
            system_logger.exception(f"Không thể liệt kê IP đang bị BAN: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"Message": f"Không thể liệt kê IP đang bị BAN: {str(e)}"},
            )
    