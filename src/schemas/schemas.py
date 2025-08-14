from pydantic import BaseModel
from datetime import datetime

"""
Định nghĩa lược đồ từ người dùng đến API và từ API gửi đến người dùng  
Có nghĩa là các thông tin sẽ hiển thị khi gọi đến API, giới hạn một số thông tin bí mật không được phép cho người dùng xem khi gọi API
"""

class User_Login_Base(BaseModel):
    """
    Class này chứa thông tin cần được cung cấp để tạo một thông tin đăng nhập mới
    - **ID**: Mã cho mỗi người đăng nhập
    - **User_Name**: Họ tên người đăng nhập 
    - **Email**: Email của người đăng nhập
    - **Password**: Mật khẩu người đăng nhập
    - **Avatar**: Đường dẫn tới hình ảnh người đăng nhập 
    - **Privilege**: Quyền hạn  
    """
    User_Name: str
    Email: str
    Password: str

class User_Login_Display(BaseModel):
    """
    Trả về thông tin người dùng theo ý muốn, không trả về những thông tin quan trọng như password đã hash
    Lưu ý tên của các trường thông tin trả về phải giống nhau, nếu không gặp lỗi
    -  **Config**: cho phép tự động chuyển đổi dữ liệu giữa CSDL (nvarchar) và kiểu mà ta đã khai báo (str)
    """
    User_Name: str
    Email: str
    Avatar:str
    Privilege: str
    class Config():
        from_attributes  = True

class User_Login_Full_Display(BaseModel):
    """
    Trả về đầy đủ các thông tin từ người dùng
    """
    ID : str
    User_Name : str
    Email : str
    Password : str
    Avatar : str
    Privilege : str
    Activate : datetime
    OTP_Code : str
    Expiration_Time : datetime
    Status : str
    class Config():
        from_attributes = True

class User_Login_OTP_Display (BaseModel):
    """
    Trả về các thông tin khi người dùng truy vấn mã OTP
    """
    ID : str
    User_Name : str
    Email : str
    OTP_Code : str
    Expiration_Time : datetime

class UserAuth(BaseModel):
    """
    Trả về thông tin người dùng khi giải mã token
    """
    ID: str
    Name: str
    Email: str
    Avatar: str
    Privilege: str
