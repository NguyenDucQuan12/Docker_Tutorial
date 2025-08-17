from fastapi import APIRouter, Depends
from sqlalchemy.orm.session import Session
from schemas.schemas import  User_Login_Base, User_Login_Display, UserAuth
from db.database import get_db
from controllers.user_login_controller import User_Login_Controller
from auth.oauth2 import required_token_user

# Khai báo router với tiền tố cho các endpoint là: /user_login/xxx
router = APIRouter(
    prefix = "/user_login",
    tags= ["User Login"]
)


@router.get("/list_users", response_model = list[User_Login_Display])
def get_list_users(db: Session = Depends(get_db)):
    """
    Truy vấn danh sách người dùng hiện có  
    `Giới hạn 1000 người`
    """
    return User_Login_Controller.get_all_users(db= db)

@router.post("/new_user", response_model = User_Login_Display)
def create_user(request: User_Login_Base, db: Session = Depends(get_db)):
    """
    Tạo thông tin người dùng vào CSDL
    """
    return User_Login_Controller.create_user(db= db, request= request)

@router.put("/activate_user/{email_user}")
def activate_user(email_user: str, activate: bool, db: Session = Depends(get_db), current_user : UserAuth = Depends(required_token_user)):
    """
    Kích hoạt hoặc hủy kích hoạt người dùng
    - `email_user`: Email của người dùng cần kích hoạt hoặc hủy kích hoạt
    - `activate`: True để kích hoạt, False để hủy kích hoạt
    """    
    return User_Login_Controller.activate_user(db= db, email_user= email_user, activate= activate, current_user = current_user)

@router.put("/change_privilege_user/{email_user}")
def change_privilege_user(email_user: str, privilege: str,  db: Session = Depends(get_db), current_user : UserAuth = Depends(required_token_user)):
    """
    Thay đổi quyền hạn cho người dùng
    """
    return User_Login_Controller.change_privilege_user(db= db, email_user= email_user, privilege= privilege, current_user = current_user)

@router.delete("/delete_user/{email_user}")
def delete_user(email_user: str, db: Session = Depends(get_db), current_user : UserAuth = Depends(required_token_user)):
    """
    Xóa tài khoản người dùng
    - `email_user`: Email của người dùng cần kích hoạt hoặc hủy kích hoạt
    """    
    return User_Login_Controller.delete_user(db= db, email_user= email_user, current_user = current_user)