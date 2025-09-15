from ipaddress import ip_address
from typing import Optional

def _norm_ip(ip_raw: Optional[str]) -> str:
    """
    Chuẩn hoá chuỗi IP về dạng hợp lệ; nếu lỗi, trả '-'
    """
    # Kiểm tra giá trị truyền vào tồn tại hay không và có phải là chuỗi string hay không
    if not ip_raw or not isinstance(ip_raw, str):
        return False, None
    
    try:
        ip_address(ip_raw)  # Parse IPv4/IPv6; sai sẽ ném ValueError

        return True, str(ip_address(ip_raw))
    except Exception:
        # Nếu không parse được, trả nguyên để không crash
        return False, ip_raw