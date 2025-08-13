from fastapi import APIRouter, Depends
from sqlalchemy.orm.session import Session
from schemas.schemas import  User_Login_Base, User_Login_Display
from db.database import get_db
from db import db_user_login


router = APIRouter(
    prefix = "/user_login",
    tags= ["user"]
)


@router.post("/new_user", response_model = User_Login_Display)
def create_user(request: User_Login_Base, db: Session = Depends(get_db)):
    """
    Tạo thông tin người dùng vào CSDL
    """
    return db_user_login.create_new_user_login(db= db, request= request)

@router.get("/list-users", response_model = list[User_Login_Display])
def get_list_users(db: Session = Depends(get_db)):
   
    return db_user_login.get_all_user_login(db= db)