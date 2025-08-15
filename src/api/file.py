from fastapi import APIRouter, File, UploadFile, Query, Depends
from controllers.file_controller import File_Controller
from auth.oauth2 import get_info_user_via_token, required_token_user
from schemas.schemas import UserAuth


router = APIRouter(
    prefix="/file",
    tags=["File"]
)


@router.post("/upload/", summary="Tải tệp tin lên máy chủ")
async def upload_file(file: UploadFile = File(...), user_info: UserAuth = Depends(get_info_user_via_token)):
    """
    Người dùng tải tệp tin lên máy chủ
    """
    return await File_Controller.upload_file(file, user_info= user_info)

@router.get("/list_file_in_folder/", summary="Lấy danh sách các tệp tin trong thư mục")
async def list_files():
    """
    Liệt kê các file trong thư mục file
    """
    return await File_Controller.list_file()

@router.get("/download/{file_name}")
async def download_file(file_name: str):
    """
    Tải tệp tin từ máy chủ về  
    - **file_name**: Đường dẫn đến tệp tin  
    Sử dụng api `list_file` để xem đường dẫn tệp tin, lưu ý sử dụng `\\\` để ngăn cách giữa các đường dẫn
    """
    return await File_Controller.download_file(file_name)
   
@router.delete("/delete/{file_name}", summary="Xóa file")
async def delete_file(file_name: str, user_info: UserAuth = Depends(required_token_user)):
    """
    Xóa tệp tin trên server  
    Sử dụng dấu ngăn cách giữa các đường dẫn là `\\\`  
    """
    return await File_Controller.delete_file(file_name, user_info)

@router.put("/rename", summary="Đổi tên file")
async def rename_file( old_name: str = Query(..., description="Tên file cũ"), new_name: str = Query(..., description="Tên file mới")):
    """
    Đổi tên file
    """
    return await File_Controller.rename_file(old_name, new_name)

@router.get("/info/{file_name}", summary="Lấy thông tin file")
async def file_info(file_name: str):
    """
    Truy vấn thông tin chi tiết của tệp tin
    """
    return await File_Controller.file_info(file_name)