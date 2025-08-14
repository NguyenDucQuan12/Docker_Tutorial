from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.orm.session import Session
from db.database import get_db
from db.models import DbUser_Login
from utils.hash import Hash
from auth import oauth2


router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

# Địa chỉ này phải đúng với tokenURL trong: oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
@router.post("/login")
def login(request: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Tạo ra một token có thời gian tồn tại để có thể truy vấn đến các API được khóa  
    - **request** sẽ là dữ liệu theo dạng biểu mẫu của `OAuth2PasswordRequestForm` gồm `username` và `password`  
    Để sử dụng  hàm này ta cần cung cấp `username` và `password` đã được đăng ký trong CSDL  
    ### Ví dụ

    ```python
    import requests

    url_get_token = "http://172.31.99.42:8000/auth/login"
    data = {
        "username": "nguyenducquan2001@gmail.com",
        "password": "123456789"
    }
    response = requests.post(url=url_get_token, data= data)
    token = response.json().get("access_token")

    print(token)
    
    ```

    [FastAPI docs for Simple OAuth2 with Password and Bearer](https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/)
    """
    user = db.query(DbUser_Login).filter(DbUser_Login.Email == request.username).first()
    if not user:
        raise HTTPException(
            status_code= status.HTTP_404_NOT_FOUND,
            detail={
                "message": f"Không tìm thấy người dùng có địa chỉ email: {request.username}"
            }
        )
    
    # So sánh mật khẩu người dùng vừa cung cấp với mật khẩu trong CSDL
    if not Hash.verify(plain_password= request.password, hashed_password= user.Password):
        raise HTTPException(
            status_code= status.HTTP_404_NOT_FOUND,
            detail={
                "message": f"Mật khẩu cho tài khoản {request.username} không chính xác"
            }
        )
    
    # Kiểm tra xem người dùng có được kích hoạt hay không
    if not user.Activate:
        raise HTTPException(
            status_code= status.HTTP_403_FORBIDDEN,
            detail={
                "message": f"Người dùng {request.username} chưa được kích hoạt"
            }
        )
    
    # Tạo token với thông tin đi kèm
    # Không truyền biến chứa các giá trị datetime vào, nên sử dụng các kiểu đơn giản như str, int, bool,...
    access_token = oauth2.create_access_token(data= {
        "ID": user.ID,
        "Name": user.User_Name,
        "Email": user.Email,
        "Avatar": user.Avatar,
        "Privilege": user.Privilege
    })

    return {
        "access_token": access_token,
        "token_type": "Bearer", # token tiêu chuẩn: bearer
    }