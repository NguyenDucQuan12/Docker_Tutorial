from sqlalchemy.orm.session import Session
from fastapi import HTTPException, status
from sqlalchemy import exc
from schemas.schemas import User_Login_Base
from db.models import DbUser_Login
from utils.hash import Hash
from utils.random_id import get_random_string
from utils.constants import *


"""
Các câu lệnh truy vấn tới CSDL User_Login
"""

def create_new_user_login(db: Session, request: User_Login_Base):

    """
    Tạo thông tin người đăng nhập mới và mã hóa mật khẩu trước khi lưu vào CSDL  
    - `request`: Thông tin mà người dùng cần cung cấp  

    Kết quả trả về:  
    200:  
    - `new_user_login`: Thông tin người dùng mới  
    500:  
    - `"message": "Lỗi khi thêm người dùng mới"`
    """
    # Tạo id cho một người
    new_user_id = get_random_string(32)
    
    # Khai báo các thông tin cho người dùng mới
    new_user_login =  DbUser_Login(
        ID = new_user_id, 
        User_Name = request.User_Name,
        Email = request.Email ,
        Password = Hash.bcrypt(request.Password), # mã hóa mật khẩu
        Avatar = DEFAULT_AVATAR,
        Privilege = DEFAULT_PRIVILEGE
    )

    # Tiến hành ghi dữ liệu
    try:
        db.add(new_user_login)
        db.commit()
        # refresh giúp nhận được giá trị ID của người dùng, vì nó là giá trị tự tăng
        db.refresh(new_user_login)

    except exc.SQLAlchemyError as e:   
        # Trong quá trình insert lỗi thì giá trị id (cột IDENTITY) vẫn tự tăng, đây là hành vi mặc định của SQL Server
        # Rollback lại giao dịch
        db.rollback()
        # Trả về lỗi
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Lỗi khi thêm người dùng {request.User_Name}: {str(e)}"
            }
        )
    
    return new_user_login 

def get_all_user_login (db:Session):
    """
    Truy vấn tất cả thông tin người dùng
    """
    try:
        list_user = db.query(DbUser_Login).all()

        if not list_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail= {
                    "message": f"Không tìm thấy người dùng trong CSDL"
                }
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail= {
                "message": f"Xảy ra lỗi trong quá trình truy vấn danh sách người đăng nhập: {str(e)}"
            }
        )
    
    return list_user

def get_user_login_by_email(db: Session, email: str):
    """
    Truy vấn thông tin người dùng với `email` được cung cấp  
    
    """
    user_login = db.query(DbUser_Login).filter(DbUser_Login.Email == email).first()
    if not user_login:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail= {
                "message": f"Không tìm thấy người dùng có địa chỉ email:{email}"
            }
        )
    
    return user_login

def update_user_login(db: Session, user_id: str, request: User_Login_Base):
    """
    Cập nhật thông tin người dùng với `user_id` được cung cấp
    - `request`: Thông tin cập nhật người dùng
    """
    user_login = db.query(DbUser_Login).filter(DbUser_Login.ID == user_id).first()
    
    if not user_login:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail= {
                "message": f"Không tìm thấy người dùng với ID: {user_id}"
            }
        )
    
    # Cập nhật thông tin người dùng
    user_login.User_Name = request.User_Name
    user_login.Email = request.Email
    if request.Password:
        user_login.Password = Hash.bcrypt(request.Password)  # Nếu có mật khẩu mới thì mã hóa lại mật khẩu
    user_login.Avatar = request.Avatar if request.Avatar else user_login.Avatar
    user_login.Privilege = request.Privilege if request.Privilege else user_login.Privilege
    
    try:
        db.commit()
        db.refresh(user_login)
    except exc.SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Lỗi khi cập nhật người dùng {user_id}: {str(e)}"
            }
        )

    return user_login

def delete_user_login(db: Session, user_id: str):
    """
    Xóa người dùng với `user_id` được cung cấp
    """
    user_login = db.query(DbUser_Login).filter(DbUser_Login.ID == user_id).first()
    
    if not user_login:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail= {
                "message": f"Không tìm thấy người dùng với ID: {user_id}"
            }
        )
    
    try:
        db.delete(user_login)
        db.commit()
    except exc.SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Lỗi khi xóa người dùng {user_id}: {str(e)}"
            }
        )

    return {"message": f"Người dùng với ID: {user_id} đã được xóa thành công."}