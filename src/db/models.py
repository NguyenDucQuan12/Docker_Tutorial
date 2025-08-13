from db.database import Base
from sqlalchemy import Column, Integer, String, DateTime, Unicode

"""
Định nghĩa tất cả các bảng trong SQL Server
"""

class DbUser_Login(Base):
    """
    Định nghĩa bảng thông tin đăng nhập   
    Mật khẩu đã được mã hóa trước khi lưu vào CSDL
    """
    __tablename__ = "Users_Login"
    ID = Column(Unicode(200), primary_key=True)
    User_Name = Column(Unicode(500)) # Sử dụng kiểu Nvarchar: NVARCHAR
    Email = Column(Unicode(200), unique=True) # Không được trùng nhau
    Password = Column(Unicode(200))
    Avatar = Column(Unicode(400))
    Privilege = Column(Unicode(100))
    Activate = Column(DateTime)
    OTP_Code = Column(Unicode(100))
    Expiration_Time = Column(DateTime)
    Status = Column(Unicode(500))
