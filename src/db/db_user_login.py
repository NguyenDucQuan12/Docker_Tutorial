from sqlalchemy.orm.session import Session
from sqlalchemy import exc
from db.models import DbUser_Login
from utils.constants import *
from datetime import datetime


"""
Các câu lệnh truy vấn tới CSDL User_Login
"""

def create_new_user_login(db: Session, new_user_login: DbUser_Login):

    """
    Tạo người dùng mới vào CSDL
    - `new_user_login`: Thông tin người dùng mới cần thêm vào CSDL  
    """
    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    # Tiến hành ghi dữ liệu
    try:
        db.add(new_user_login)
        db.commit()
        # refresh giúp nhận được giá trị ID của người dùng, vì nó là giá trị tự tăng
        db.refresh(new_user_login)

        # Trả về kết quả thành công
        response["message"] = "Thêm người dùng mới thành công"
        response["success"] = True
        response["data"] = new_user_login

    except exc.IntegrityError as e:  # Bắt lỗi vi phạm ràng buộc (ví dụ: khóa chính, khóa ngoại)
        db.rollback()
        response["message"] = f"Lỗi khi thêm người dùng mới: Vi phạm ràng buộc dữ liệu ({str(e)})"
    
    except exc.DataError as e:  # Bắt lỗi kiểu dữ liệu không hợp lệ (ví dụ: vượt quá độ dài chuỗi, kiểu dữ liệu sai)
        db.rollback()
        response["message"] = f"Lỗi khi thêm người dùng mới: Lỗi dữ liệu ({str(e)})"
    
    except exc.SQLAlchemyError as e:  # Bắt tất cả các lỗi khác từ SQLAlchemy
        db.rollback()
        response["message"] = f"Lỗi khi thêm người dùng mới: {str(e)}"
    
    except Exception as e:  # Bắt tất cả các lỗi ngoài SQLAlchemy
        db.rollback()
        response["message"] = f"Lỗi không xác định: {str(e)}"        
    
    return response 

def get_all_user_login (db:Session):
    """
    Truy vấn tất cả thông tin người dùng
    """

    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    try:
        # Truy vấn dữ liệu
        list_user = db.query(DbUser_Login).limit(1000).all()

        # Nếu không tìm thấy dữ liệu
        if not list_user:
            response["message"] = "Chưa có dữ liệu cho tài khoản đăng nhập"
        else:
            response["success"] = True
            response["message"] = "Tìm thấy dữ liệu tài khoản đăng nhập"
            response["data"] = list_user

    except Exception as e:

        response["message"] =  f"Xảy ra lỗi trong quá trình truy vấn danh sách người đăng nhập: {str(e)}"
    
    return response

def get_user_login_by_email(db: Session, email: str):
    """
    Truy vấn thông tin người dùng với `email` được cung cấp  
    """
    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    try:

        user_login = db.query(DbUser_Login).filter(DbUser_Login.Email == email).first()

        # Kiểm tra xem tồn tại người dùng không
        if user_login:
            response["success"] = True
            response["data"] = user_login
            response["message"] = f"Tìm thấy người dùng có email: {email}"

        else:
            response["success"] = None
            response["message"] = f"Không tìm thấy người dùng có email: {email}"

    except Exception as e:
        response["message"] = f"Lỗi khi truy vấn thông tin người dùng {email}: {str(e)}"
    
    return response 

def activate_user_login(db: Session, email: str, activate: bool):
    """
    Kích hoạt/hủy kích hoạt tài khoản với `user_id` được cung cấp.  
    Chỉ `Admin` mới có thể thực hiện hành động này.  
    """
    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    # Truy vấn người dùng theo ID
    user_login = db.query(DbUser_Login).filter(DbUser_Login.Email == email).first()
    
    if not user_login:
        response["message"] = f"Không tìm thấy người dùng có địa chỉ email: {email}"
        return response
    
    # Lấy thời gian kích hoạt là thời gian hiện tại
    user_login.Activate = datetime.now() if activate else None

    try:
        db.commit()
        db.refresh(user_login)

        # Tạo cú pháp trả về
        response["success"] = True
        response["message"] = f"Kích hoạt thành công tài khoản người dùng {email} vào thời gian: {user_login.Activate}"

    except exc.SQLAlchemyError as e:
        db.rollback()
         # Tạo cú pháp trả về
        response["success"] = False
        response["message"] = f"Không thể kích hoạt tài khoản người dùng {email}: {str(e)}"

    return response

def change_privilege_user(db: Session, email: str, privilege: str):
    """
    Thay đổi quyền hạn của người dùng trong nhwungx quyền hạn được cho phép  
    Chỉ `Admin` mới có thể thực hiện hành động này.  
    """
    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    # Truy vấn người dùng theo Email
    user_login = db.query(DbUser_Login).filter(DbUser_Login.Email == email).first()
    
    if not user_login:
        response["message"] = f"Không tìm thấy người dùng có địa chỉ email: {email}"
        return response
    
    # Lấy thời gian kích hoạt là thời gian hiện tại
    user_login.Privilege = privilege if privilege else DEFAULT_PRIVILEGE

    try:
        db.commit()
        db.refresh(user_login)

        # Tạo cú pháp trả về
        response["success"] = True
        response["message"] = f"Quyền hạn của người dùng {email} đã được chuyển thành: {user_login.Privilege}"

    except exc.SQLAlchemyError as e:
        db.rollback()
         # Tạo cú pháp trả về
        response["success"] = False
        response["message"] = f"Không thể thay đổi quyền hạn tài khoản người dùng {email}: {str(e)}"

    return response

def delete_user_login(db: Session, email: str):
    """
    Xóa người dùng với `email` được cung cấp
    """

    # Cú pháp trả về khi gọi CSDL
    response = {
        "success": False,
        "data": None,
        "message": "Lỗi khi thêm người dùng mới"
    }

    user_login = db.query(DbUser_Login).filter(DbUser_Login.Email == email).first()
    
    if not user_login:
        response["message"] = f"Không tìm thấy người dùng có địa chỉ email: {email}"
        return response
    
    # Tiến hành xóa người dùng
    try:
        db.delete(user_login)
        db.commit()

        response["success"] = True
        response["message"] = f"Xóa thành công tài khoản người dùng có địa chỉ email: {email}"

    except exc.SQLAlchemyError as e:
        db.rollback()
        
        response["message"]= f"Xảy ra lỗi khi xóa người dùng có email {email}: {str(e)}"

    return response