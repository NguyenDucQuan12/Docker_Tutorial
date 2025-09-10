from fastapi import FastAPI# pip install "fastapi[standard]"
import uvicorn
import threading
import os
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from db.database import engine
from db import models
from log.system_log import _rotation_thread
from api import user_login, file, health_check, update_application, security_admin, ops_dashboard
from middlerware import logger
from middlerware.security_guard import security_guard  # # Middleware phòng thủ
from auth import authentication
from services.email_services import InternalEmailSender
from dotenv import load_dotenv

load_dotenv()  # Tự động tìm và nạp file .env ở thư mục hiện tại


# Khởi tạo email
email_service = InternalEmailSender()


# Đường dẫn thư mục lưu trữ file
PORT_HOST = os.getenv("PORT_HOST", "8000")
EMAIL_ADMIN = os.getenv("EMAIL_ADMIN", "nguyenducquan2001@gmail.com")
IP_ADDRESS_HOST = os.getenv("IP_ADDRESS_HOST", "nguyenducquan2001@gmail.com")

# Ép kiểu để port là số nguyên
PORT = int(PORT_HOST)

# Khởi động thread nền tạo file log cho ngày mới của log hệ thống (ko gọi trong system_log vì mỗi khi import nó lại mở 1 thread, chỉ nên gọi 1 lần ở main)
log_thread = threading.Thread(target=_rotation_thread, name="DailySystemLogRotationThread", daemon=True)
log_thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Các câu lệnh được thực hiện khi khởi động (Dùng cho việc khởi tạo các mô hình AI)
    # print("Khởi tạo Fast API server")
    # Gửi mail thông báo tới người dùng là đã khởi động FastAPI
    email_service.send_mail_on_startup(to_email= EMAIL_ADMIN, website_name= IP_ADDRESS_HOST)
    yield
    # Các câu lệnh sau yield được thực hiện khi kết thúc chương trình
    # print("Kết thúc Fast API server")
    email_service.send_mail_on_shutdown(to_email= EMAIL_ADMIN, website_name= IP_ADDRESS_HOST)

# Khởi tại FastAPi
app = FastAPI(
    docs_url="/myapi",  # Đặt đường dẫn Swagger UI thành "/myapi"
    redoc_url=None,  # Tắt Redoc UI
    # lifespan= lifespan  # Thêm câu lệnh lifespan
)

# # Đăng ký middleware bảo vệ (đặt càng sớm càng tốt)
app.middleware("http")(security_guard)

# Đưa middleware vào app FastAPI
app.add_middleware(BaseHTTPMiddleware, dispatch=logger.log_requests)

# Thêm các endpoint ở đây
app.include_router(user_login.router)
app.include_router(file.router)
app.include_router(health_check.router)
app.include_router(authentication.router)
app.include_router(update_application.router)
app.include_router(security_admin.router)
app.include_router(ops_dashboard.router)

# Tạo icon cho trang web api, nó sẽ hiển thị hình ảnh favicon ở thư mục `static/favicon.ico`
@app.get('/favicon.ico')
async def favicon():
    file_name = "favicon.ico"
    file_path = os.path.join("assets", "images", "static", file_name)
    return FileResponse(path=file_path, headers={"Content-Disposition": "attachment; filename=" + file_name})

# Tạo Bảng trong DB nếu nó chưa tồn tại
models.Base.metadata.create_all(engine)

"""
Cho phép các trang web, app, api trên cùng 1 máy tính có thể truy cập đến api này  
Mặc định các api trên cùng 1 máy không thể chia sẻ tài nguyên cho nhau  
Điều này phục vụ cho mục đích test, vì không thể lúc nào cũng có sẵn 2 máy tính khác nhau để test
"""
origins = [
    "http://localhost:3000",
    "http://172.31.99.130"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins = origins,
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"]
)

if __name__ == "__main__":
    #Thêm tham số log_config= "logs\\logging_config.json" để chuyển các log của uvicorn vào tệp
    uvicorn.run("__main__:app", host="0.0.0.0", port=PORT)  # log_config= "logs\\logging_config.json"

    # Hoặc gõ trực tiếp lệnh `fastapi dev src/main.py` để vào chế độ developer
    # Hoặc gõ trực tiếp lệnh `fastapi run src/main.py` để vào chế độ lấy máy chạy làm server