from sqlalchemy.orm.session import Session
from fastapi import HTTPException, status
import re
from schemas.schemas import User_Login_Base
from db.models import DbUser_Login
from utils.hash import Hash
from utils.random_id import get_random_string
from utils.constants import *
from datetime import datetime
from db import db_user_login

EMAIL_REGEX = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

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

        return new_user["data"]
    
    def get_all_users(db: Session):
        """
        Lấy danh sách tất cả người dùng
        """
        # Gọi hàm để lấy danh sách người dùng từ CSDL
        list_users = db_user_login.get_all_user_login(db=db)

        if not list_users["success"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Không tìm thấy người dùng trong CSDL"
                }
            )
        
        return list_users["data"]
    
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
        
        # Tiến hành kích hoạt tài khoản người dùng
        delete_user = db_user_login.delete_user_login(db= db, email= email_user)

        message = {
            "Operator": current_user["Name"],
            "Message": delete_user["message"]
        }

        return message
        