from sqlalchemy.orm.session import Session
from fastapi import HTTPException, status
import re
from typing import List                                       # Kiểu danh sách
from schemas.schemas import User_Login_Base
from db.models import DbUser_Login
from utils.hash import Hash
from utils.random_id import get_random_string
from utils.constants import *
from utils.cache import make_cache_key, get_cache, set_cache, delete_by_prefix  # Tiện ích cache
from datetime import datetime
from db import db_user_login
from services.email_services import InternalEmailSender
from log.system_log import system_logger

EMAIL_REGEX = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
# Khai báo "prefix" chung cho cache danh sách user (để dễ xoá theo prefix khi invalidation)
CACHE_LIST_USERS_PREFIX = "cache:users:list"

def invalidate_list_users_cache() -> int:
    """
    Xoá mọi cache danh sách user.
    Gọi hàm này ngay sau khi CREATE/UPDATE/DELETE user để tránh lấy dữ liệu cũ khi truy vấn.
    """
    deleted = delete_by_prefix(CACHE_LIST_USERS_PREFIX)
    return deleted

# Khai báo dịch vụ mail
email_services = InternalEmailSender()

class User_Login_Controller:
    """
    Controller để xử lý các yêu cầu liên quan đến người dùng đăng nhập
    """
    
    def create_user(request: User_Login_Base, db: Session):
        """
        Tạo thông tin người dùng mới
        """
        # Tạo id ngẫu nhiên cho một người
        new_user_id = get_random_string(32)

        # Validate các thông tin người dùng mới
        if not request.User_Name or not request.Email or not request.Password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Tên người dùng, email và mật khẩu là bắt buộc"
                }
            )
        
        # Kiểm tra email là hợp lệ
        if not re.match(EMAIL_REGEX, request.Email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": f"Email {request.Email} không hợp lệ"
                }
            )
        
        # Ép các giá trị sang kiểu chuỗi
        user_name = str(request.User_Name)
        email = str (request.Email)
        password = str(request.Password)

        # Kiểm tra email đã tồn tại trên CSDL chưa
        existing_user = db_user_login.get_user_login_by_email(db= db, email= email)

        if existing_user["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": f"Email {request.Email} đã được sử dụng. Hãy lựa chọn tài khoản khác."
                }
            )
        elif existing_user["success"] is False:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": f"Xảy ra lỗi trong quá trình tạo người dùng {request.Email}: {existing_user['message']}"
                }
            )
        else:
            # Khai báo các thông tin cho người dùng mới
            new_user_login =  DbUser_Login(
                ID = new_user_id, 
                User_Name = user_name,
                Email = email,
                Password = Hash.bcrypt(password), # mã hóa mật khẩu
                Avatar = DEFAULT_AVATAR,
                Privilege = DEFAULT_PRIVILEGE
            )

            # Gọi hàm để thêm người dùng mới vào CSDL
            new_user = db_user_login.create_new_user_login(db=db, new_user_login=new_user_login)  

            # Kiểm tra kết quả trả về từ hàm tạo người dùng mới
            if not new_user["success"]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "message": new_user["message"]
                    }
                )
            
            # Xoá cache danh sách user (nếu có) để tránh lấy dữ liệu cũ
            invalidate_list_users_cache()
            
            # Nếu tạo người dùng thành công, gửi mail tới họ
            email_services.send_email_for_new_account(
                    to_email= email,
                    name= user_name,
                    website_name= "Hệ thống API"
                )

        return new_user["data"]
    
    def get_all_users(db: Session):
        """
        Lấy danh sách tất cả người dùng, có cache Redis.
        - TTL mặc định 60 giây (trong thời gian này, các lần gọi tiếp theo sẽ lấy cache nếu có)
        - Khi có thay đổi user (create/update/delete) -> nên xoá cache prefix.
        """
        # 1) Tạo key cache. Vì API này không có tham số lọc, ta dùng key tĩnh.
        #    Nếu sau này có tham số (page, dept, ...) thì đưa vào dict để tạo hash khác nhau.
        key = make_cache_key("users:list", {"v": 1})  # "v": 1 là version nhỏ để bạn chủ động bust cache khi đổi format

        # 2) Thử lấy cache
        cached = get_cache(key)
        if cached is not None:
            # Cache hit → trả luôn. FastAPI sẽ ép về response_model cho bạn.
            system_logger.info(f"Cache hit cho danh sách người dùng: {key}- {len(cached) if isinstance(cached, list) else '?'} items")
            return cached
    
        #  3) Cache miss → truy vấn DB thực
        list_users = db_user_login.get_all_user_login(db=db)

        if not list_users["success"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Không tìm thấy người dùng trong CSDL"
                }
            )
        
        data = list_users["data"]  # Danh sách user (list[User_Login_Display] hoặc dict tương thích)

        # (Tuỳ chọn) Giới hạn 1000 người ở đây
        # if isinstance(data, list) and len(data) > 1000:
        #     data = data[:1000]

        # 4) Lưu cache với TTL 60 giây
        set_cache(key, data, ttl=60)

        # 5) Trả kết quả
        return data
    
    def activate_user (db: Session, email_user: str, activate: bool, current_user):
        """
        Kích hoạt tài khoản người dùng  
        Chỉ có Admin mới có quyền thao tác  
        """
        # Kiểm tra token người dùng có hợp lệ không
        if not email_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Email người dùng không được để trống"
                }
            )
        
        # Kiểm tra xem có quyền thao tác không
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Vui lòng xác thực người dùng trước khi thao tác"
                }
            )
        
        if current_user["Privilege"] not in HIGH_PRIVILEGE_LIST:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Bạn không có quyền kích hoạt tài khoản người dùng"
                }
            )
        
        # Tiến hành kích hoạt tài khoản người dùng
        activate_user = db_user_login.activate_user_login(db= db, email= email_user, activate= activate)

        message = {
            "Operator": current_user["Name"],
            "Message": activate_user["message"]
        }

        return message
    
    def change_privilege_user (db: Session, email_user: str, privilege:str, current_user):
        """
        Thay đổi quyền hạn cho người dùng
        Chỉ có `Admin` mới có quyền thao tác  
        """
        # Kiểm tra token người dùng có hợp lệ không
        if not email_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Email người dùng không được để trống"
                }
            )
        
        # Kiểm tra xem có quyền thao tác không
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Vui lòng xác thực người dùng trước khi thao tác"
                }
            )
        
        if current_user["Privilege"] not in HIGH_PRIVILEGE_LIST:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Bạn không có quyền kích hoạt tài khoản người dùng"
                }
            )
        
        # Kiểm tra quyền hạn có hợp lệ không
        if privilege not in FULL_PRIVILEGE_LIST:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": f"Quyền hạn người dùng không hợp lệ. Hãy thay đổi một trong các quyền sau: {PRIVILEGE_LIST}"
                }
            )
        
        # Tiến hành thay đổi quyền hạn cho người dùng
        privilege_user = db_user_login.change_privilege_user(db= db, email= email_user, privilege = privilege)

        message = {
            "Operator": current_user["Name"],
            "Message": privilege_user["message"]
        }

        return message
    
    def delete_user (db: Session, email_user: str, current_user):
        """
        Xóa tài khoản người dùng  
        Chỉ có `Admin` mới có quyền thao tác  
        """
        # Kiểm tra token người dùng có hợp lệ không
        if not email_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Email người dùng không được để trống"
                }
            )
        
        # Kiểm tra xem có quyền thao tác không
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Vui lòng xác thực người dùng trước khi thao tác"
                }
            )
        
        if current_user["Privilege"] not in HIGH_PRIVILEGE_LIST:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Bạn không có quyền xóa tài khoản người dùng"
                }
            )
        
        # Tiến hành xóa tài khoản người dùng
        delete_user = db_user_login.delete_user_login(db= db, email= email_user)

        message = {
            "Operator": current_user["Name"],
            "Message": delete_user["message"]
        }

        return message
        