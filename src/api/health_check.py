from fastapi import APIRouter
from fastapi.responses import JSONResponse
from db.database import engine
from dotenv import load_dotenv
from sqlalchemy import text
import os

load_dotenv()  # Tự động tìm và nạp file .env ở thư mục hiện tại

# Khai báo router với tiền tố cho các endpoint là: /user_login/xxx
router = APIRouter(
    tags= ["Health"]
)


@router.get("/healthz", summary="Liveness probe")
async def healthz():
    """
    Kiểm tra sống/chết cơ bản của tiến trình.
    """
    return {"status": "ok"}

@router.get("/readyz", summary="Readiness probe")
def readyz():
    """
    Kiểm tra sẵn sàng: DB + quyền ghi thư mục upload.
    Trả 200 nếu ok, 503 nếu có bất kỳ lỗi nào.
    """
    checks = {}

    # 1) Kiểm tra DB
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e.__class__.__name__}"

    # 2) Kiểm tra quyền ghi thư mục upload
    upload_root = os.getenv("UPLOAD_DIRECTORY") or "/app/uploads"
    try:
        os.makedirs(upload_root, exist_ok=True)
        probe_file = os.path.join(upload_root, ".readyz.tmp")
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe_file)
        checks["fs"] = "ok"
    except Exception as e:
        checks["fs"] = f"error: {e.__class__.__name__}"

    ok = all(val == "ok" for val in checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "error", "checks": checks},
    )