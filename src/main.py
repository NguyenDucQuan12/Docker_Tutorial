from fastapi import FastAPI, Request, Response# pip install "fastapi[standard]"
import uvicorn
import os
import datetime
import json
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from db.database import engine
from db import models
from api import user_login
from auth import authentication


# Khởi tại FastAPi
app = FastAPI(
    docs_url="/myapi",  # Đặt đường dẫn Swagger UI thành "/myapi"
    redoc_url=None  # Tắt Redoc UI
)

# Thêm các endpoint ở đây
app.include_router(user_login.router)
app.include_router(authentication.router)


@app.get("/check")
def read_root():
    return {"Message": "Hello World"}

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
    uvicorn.run("__main__:app", host="0.0.0.0", port=8000)  # log_config= "logs\\logging_config.json"

    # Hoặc gõ trực tiếp lệnh `fastapi dev src/main.py` để vào chế độ developer
    # Hoặc gõ trực tiếp lệnh `fastapi run src/main.py` để vào chế độ lấy máy chạy làm server