# app/routers/security_admin.py
# -*- coding: utf-8 -*-

"""
Router quản trị bảo mật:
- /security/admin/ban_now            : Ban ngay 1 IP (ttl tùy chọn)
- /security/admin/unban              : Gỡ ban 1 IP
- /security/admin/unban_bulk         : Gỡ ban nhiều IP
- /security/admin/ban_ttl            : Xem TTL còn lại của 1 IP đang bị ban
- /security/admin/top_suspicious     : Top-N IP nghi vấn (5 phút gần)
- /security/admin/current_bans       : Liệt kê IP đang bị BAN + TTL
Bảo vệ:
- Dùng required_token_user (JWT hệ của bạn) + kiểm tra Privilege Admin/Boss
"""

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body, Query
from fastapi.responses import JSONResponse

from auth.oauth2 import required_token_user                     # <-- auth của bạn
from security.redis_client import get_redis                     # Redis
from security.config import TTL, BAN_RULE                       # TTL & luật ban
from security.keyspace import (                                 # Hàm sinh key
    k_ban_ip, k_ban_notify, k_suspicious
)

router = APIRouter(prefix="/security/admin", tags=["Security Admin"])
_r = get_redis()

# ===== Quyền hạn: chỉ Admin/Boss =====

def require_admin(user: Any = Depends(required_token_user)) -> Any:
    """
    Chỉ cho phép người có Privilege 'Admin' hoặc 'Boss' truy cập router này.
    - required_token_user: decode JWT và trả thông tin user (ID, Email, Privilege, ...)
    """
    priv = getattr(user, "Privilege", None) if not isinstance(user, dict) else user.get("Privilege")
    if priv not in {"Admin", "Boss"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privilege")
    return user

# ===== Helper =====

def _ban_set(ip: str, ttl: Optional[int] = None) -> None:
    """
    Đặt cờ BAN cho IP với TTL (giây).
    - Nếu ttl=None -> dùng TTL mặc định từ cấu hình (TTL.ban_seconds).
    - Xoá khoá notify để nếu ban mới -> email cảnh báo ở middleware có thể gửi lại (tuỳ logic bạn muốn).
    """
    _r.setex(k_ban_ip(ip), int(ttl or TTL.ban_seconds), b"1")
    # Xoá khoá notify để middleware gửi lại email nếu bạn muốn (tùy nhu cầu):
    _r.delete(k_ban_notify(ip))

def _ban_ttl(ip: str) -> int:
    """Lấy TTL (giây) còn lại của IP đang bị BAN; -2 không có key; -1 không có TTL."""
    return _r.ttl(k_ban_ip(ip))

def _unban(ip: str) -> int:
    """Gỡ ban IP. Trả 1 nếu xoá được, 0 nếu không tồn tại."""
    return _r.delete(k_ban_ip(ip))

# ===== Endpoints =====

@router.post("/ban_now", summary="Ban ngay 1 IP (tuỳ chọn TTL)", response_model=dict)
def ban_now(ip: str = Body(..., embed=True, description="IPv4/IPv6 cần BAN"),
            ttl: Optional[int] = Body(None, embed=True, description="TTL giây; bỏ trống = mặc định"),
            _: Any = Depends(require_admin)):
    """
    Đặt BAN ngay 1 IP:
    - ip: chuỗi IPv4/IPv6
    - ttl: số giây; nếu None dùng TTL.ban_seconds
    """
    _ban_set(ip, ttl)
    return {"ip": ip, "ttl_seconds": ttl or TTL.ban_seconds, "status": "banned"}

@router.post("/unban", summary="Gỡ ban 1 IP", response_model=dict)
def unban(ip: str = Body(..., embed=True, description="IPv4/IPv6 cần gỡ"),
          _: Any = Depends(require_admin)):
    """
    Gỡ ban 1 IP:
    - Trả deleted=1 nếu xoá được key ban:ip:<ip>, 0 nếu không tồn tại
    """
    deleted = _unban(ip)
    return {"ip": ip, "deleted": int(deleted)}

@router.post("/unban_bulk", summary="Gỡ ban nhiều IP", response_model=dict)
def unban_bulk(ips: List[str] = Body(..., embed=True, description="Danh sách IP"),
               _: Any = Depends(require_admin)):
    """
    Gỡ ban nhiều IP một lần (đơn giản lặp _unban).
    - Trả về {done: n, total: m, details:[...]}
    """
    details = []
    done = 0
    for ip in ips:
        deleted = _unban(ip)
        details.append({"ip": ip, "deleted": int(deleted)})
        done += int(deleted)
    return {"done": done, "total": len(ips), "details": details}

@router.get("/ban_ttl", summary="Xem TTL còn lại của IP bị BAN", response_model=dict)
def ban_ttl(ip: str = Query(..., description="IPv4/IPv6"),
            _: Any = Depends(require_admin)):
    """
    Lấy TTL còn lại (giây) của IP đang bị BAN.
    - Nếu trả về -2: không có key
    - Nếu -1: có key nhưng không có TTL (không nên xảy ra vì ta luôn set TTL)
    """
    ttl = _ban_ttl(ip)
    return {"ip": ip, "ttl_seconds": ttl}

@router.get("/top_suspicious", summary="Top-N IP nghi vấn (5 phút gần nhất)", response_model=dict)
def top_suspicious(limit: int = Query(50, ge=1, le=1000),
                   _: Any = Depends(require_admin)):
    """
    Duyệt các khoá sus:ip:*:5min còn TTL, sắp theo score giảm dần, cắt top-N.
    Đây là điểm “nghi vấn” tích luỹ trong 5 phút (middleware tăng khi vượt rate/pattern xấu/UA rỗng).
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
        ttl = _r.ttl(k)
        items.append({"ip": ip, "score": score, "ttl_seconds": (ttl if ttl and ttl > 0 else None)})
    items.sort(key=lambda x: (x["score"], x["ttl_seconds"] or 0), reverse=True)
    return {"count": min(limit, len(items)), "items": items[:limit]}

@router.get("/current_bans", summary="Danh sách IP đang bị BAN + TTL", response_model=dict)
def current_bans(_: Any = Depends(require_admin)):
    """
    Liệt kê IP đang bị BAN (TTL > 0).
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
    out.sort(key=lambda x: x["ttl_seconds"])
    return {"items": out}
