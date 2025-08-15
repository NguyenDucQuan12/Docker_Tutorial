from fastapi import HTTPException, status
import shutil
from fastapi.responses import FileResponse
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

from utils.constants import *

load_dotenv()  # Tự động tìm và nạp file .env ở thư mục hiện tại


# Đường dẫn thư mục lưu trữ file
UPLOAD_DIRECTORY = os.getenv("UPLOAD_DIRECTORY")

# Tạo thư mục nếu chưa có
Path(UPLOAD_DIRECTORY).mkdir(parents=True, exist_ok=True)


class File_Controller :
    """
    Controller xử lý các api liên quan đến tệp tin
    """
    async def upload_file(file, user_info):
        """
        Tải file từ người dùng lên thư mục được lưu trữ trên máy chủ  .
        """
        try:
            # Xác định tên thư mục lưu file
            if user_info:
                folder_name = user_info["Name"]
            else:
                folder_name = "Guest"

            # Thư mục lưu
            folder_upload = os.path.join(UPLOAD_DIRECTORY, folder_name)
            # Tạo nó nếu chưa tồn tại
            Path(folder_upload).mkdir(parents=True, exist_ok=True)

            # Đường dẫn tới tệp tin
            file_location = os.path.join(folder_upload, file.filename)

            # Kiểm tra tệp tin đã tồn tại trên thư mục máy chủ chưa
            if os.path.exists(file_location):
                return {
                    "File_Name": file.filename,
                    "Message": f"Tệp tin {file.filename} đã tồn tại trên máy chủ"
                }

            # Mở file để lưu
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Trả về thông tin khi thành công
            return {
                "File_Name": file.filename,
                "Message": "Tải tệp tin thành công"}

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": f"Không thể tải lên tệp tin {file.filename}: {str(e)}"
                }
            )
        
    async def list_file():
        """
        Liệt kê các file tồn tại trong từng thư mục con của thư mục gốc
        """
        try:
            # Liệt kê tất cả các thư mục và file trong thư mục gốc
            directories = [d for d in os.listdir(UPLOAD_DIRECTORY) if os.path.isdir(os.path.join(UPLOAD_DIRECTORY, d))]
            if not directories:
                return {"message": "Không có thư mục nào trong thư mục gốc"}

            # Lưu trữ kết quả danh sách file theo từng thư mục
            result = {}
            
            for directory in directories:
                folder_path = os.path.join(UPLOAD_DIRECTORY, directory)
                # Liệt kê tất cả các file trong thư mục con
                files_in_directory = os.listdir(folder_path)
                if files_in_directory:
                    result[directory] = files_in_directory
                else:
                    result[directory] = "Không có file nào"

            # Trả về kết quả
            return {"Folder": result}

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={
                    "message": f"Lỗi khi liệt kê file: {str(e)}"
                })
        
    async def download_file(file_name: str):
        """
        Tải tệp tin từ máy chủ về local
        """
        file_path = os.path.join(UPLOAD_DIRECTORY, file_name)
    
        # Kiểm tra nếu file tồn tại
        if not os.path.isfile(file_path):
            return {
                "File_Name": file_name,
                "Message": f"Tệp tin {file_name} không tồn tại trên máy chủ"
            }

        # Sử dụng FileResponse để gửi file cho client
        return FileResponse(path=file_path, filename=file_name)
    
    async def delete_file(file_name, user_info):
        """
        Xóa file khỏi thư mục lưu trữ
        """
        # Kiểm tra xem có quyền thao tác không
        if not user_info:
            return {
                "message": "Vui lòng xác thực người dùng trước khi thao tác"
            }
        
        if user_info["Privilege"] not in HIGH_PRIVILEGE_LIST:
            return {
                "message": "Bạn không có quyền xóa tệp tin trên máy chủ"
            }
        
        # Nối chuỗi lại thành đường dẫn đến tệp tin
        file_path = os.path.join(UPLOAD_DIRECTORY, file_name)

        # Kiểm tra tệp tin có tồn tại trên server không
        if not os.path.isfile(file_path):
            return {
                "message": f"Tệp tin {file_name} không tồn tại trên máy chủ"
            }
        
        # Tiến hành xóa tệp tin
        try:
            os.remove(file_path)
            return {
                "operator": user_info["Name"],
                "message": f"Đã xóa tệp tin {file_name} thành công"
            }
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={
                    "message": f"Xảy ra lỗi khi xóa tệp tin {file_name}: {str(e)}"
                })

    async def rename_file(old_name: str, new_name: str):
        """
        Đổi tên file trong thư mục lưu trữ
        """
        old_path = os.path.join(UPLOAD_DIRECTORY, old_name)
        new_path = os.path.join(UPLOAD_DIRECTORY, new_name)

        # Kiểm tra tệp gốc có tồn tại không
        if not os.path.isfile(old_path):
            return{
                "message": f"Tệp tin {old_name} không tồn tại"
            }
        
        if os.path.exists(new_path):
            return {
                "message": f"Tên mới đã được sử dụng cho tệp tin khác, hãy chọn lại tên khác."
            }
        
        try:
            os.rename(old_path, new_path)
            return {
                    "message": f"Đã đổi tên file {old_name} thành {new_name} thành công"
                }
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": f"Lỗi khi đổi tên file: {str(e)}"
                })

    async def file_info(file_name: str):
        """
        Lấy thông tin chi tiết của file (kích thước, ngày tạo, ngày sửa)
        """
        file_path = os.path.join(UPLOAD_DIRECTORY, file_name)
        # Kiểm tra tệp tin có tồn tại hay không
        if not os.path.isfile(file_path):
            return{
                "message": f"Tệp tin {file_name} không tồn tại"
            }
        
        try:
            stat = os.stat(file_path)

            # Chuyển đổi thời gian từ timestamp sang định dạng 'hh:mm:ss dd/mm/yyyy'
            created_time = datetime.fromtimestamp(stat.st_ctime).strftime('%H:%M:%S %d/%m/%Y')
            accessed_time = datetime.fromtimestamp(stat.st_atime).strftime('%H:%M:%S %d/%m/%Y')
            modified_time = datetime.fromtimestamp(stat.st_mtime).strftime('%H:%M:%S %d/%m/%Y')

            info = {
                "File_Name": file_name,
                "Size": stat.st_size,
                "Create_At": created_time,
                "Accessed": accessed_time,
                "Modified": modified_time
            }

            return info
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={
                    "message": f"Lỗi khi lấy thông tin file: {str(e)}"
                })