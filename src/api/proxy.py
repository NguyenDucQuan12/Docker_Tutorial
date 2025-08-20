# vendor_proxy.py
import os
from fastapi import APIRouter, Request, Response
import httpx

router = APIRouter(prefix="/vendor", tags=["Vendor"])

BASE_URL = os.getenv("VENDOR_BASE_URL", "https://10.239.4.40")
API_KEY = os.getenv("VENDOR_API_KEY", "")
TLS_VERIFY = os.getenv("VENDOR_TLS_VERIFY", "false").lower() == "true"
TIMEOUT = httpx.Timeout(60.0)  # POST có thể lâu hơn GET

def _pick_passthrough_headers(req: Request) -> dict:
    """
    Chỉ forward những header cần thiết cho upstream.
    KHÔNG forward Host/Content-Length/Accept-Encoding...
    """
    h = {}
    ct = req.headers.get("content-type")
    if ct:
        h["content-type"] = ct
    # Nếu bạn cần forward Authorization từ client (hiếm khi cần với proxy kiểu này), bật dòng sau:
    # if "authorization" in req.headers: h["authorization"] = req.headers["authorization"]
    return h

def _build_resp_headers(upstream: httpx.Response) -> dict:
    out = {}
    for k in ("content-type", "content-disposition", "etag", "last-modified", "cache-control"):
        v = upstream.headers.get(k)
        if v:
            out[k.title()] = v  # giữ đúng kiểu chữ chuẩn
    return out

async def _forward(method: str, path: str, request: Request) -> Response:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    params = dict(request.query_params)

    # Chuẩn bị headers cho upstream: x-api-key + các header cần thiết từ client
    headers = {"x-api-key": API_KEY, **_pick_passthrough_headers(request)}

    # Đọc raw body để giữ nguyên cho mọi loại content (JSON / form / multipart / binary)
    body = await request.body()

    async with httpx.AsyncClient(verify=TLS_VERIFY, timeout=TIMEOUT, trust_env=False) as client:
        upstream = await client.request(method, url, params=params, headers=headers, content=body)

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_build_resp_headers(upstream),
        media_type=upstream.headers.get("content-type"),
    )

# ====== GET ======
@router.get("/epl.get-data")
async def epl_get_data(request: Request):
    return await _forward("GET", "epl.get-data", request)

@router.get("/{path:path}")
async def vendor_get_any_get(path: str, request: Request):
    return await _forward("GET", path, request)

# ====== POST ======
@router.post("/epl/data")
async def epl_post_data(request: Request):
    return await _forward("POST", "epl/data", request)

@router.post("/{path:path}")
async def vendor_post_any(path: str, request: Request):
    return await _forward("POST", path, request)


# // Gọi CÙNG origin của bạn, ví dụ: https://your-frontend.com/vendor/epl.get-data?foo=bar
# const res = await fetch('/vendor/epl.get-data?foo=bar', {
#   method: 'GET',
#   // KHÔNG gửi x-api-key ở client!
# });
# const data = await res.json(); // hoặc res.text() tùy content-type

# const res = await fetch('/vendor/epl/data?product=14&number=1544564564', {
#   method: 'POST',
#   headers: { 'Content-Type': 'application/json' },
#   body: JSON.stringify({ foo: 'bar' }),
# });
# const data = await res.json();