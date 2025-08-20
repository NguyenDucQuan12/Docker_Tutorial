import logging
import shutil
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

from utils.constants import *

load_dotenv()  # Tự động tìm và nạp file .env ở thư mục hiện tại


# Đường dẫn thư mục lưu trữ file log
SYSTEM_LOG_DIRECTORY = os.getenv("SYSTEM_LOG_DIRECTORY", "log/system_log")

Path(SYSTEM_LOG_DIRECTORY).mkdir(parents=True, exist_ok=True)

# Hàm xóa các thư mục log cũ hơn 30 ngày
def _remove_old_logs(logs_root=SYSTEM_LOG_DIRECTORY, max_days=30):
    """
    Xoá các thư mục log cũ hơn max_days ngày.
    """
    try:
        if not os.path.exists(logs_root):
            return
        
        now = datetime.now()
        # Duyệt các thư mục trong đường dẫn chứa các thư mục log theo ngày
        for entry in os.listdir(logs_root):
            entry_path = os.path.join(logs_root, entry)
            if not os.path.isdir(entry_path):
                continue
            try:
                folder_date = datetime.strptime(entry, "%d-%m-%y")  # Đọc tên thư mục theo định dạng ngày (DD-MM-YY)
            except ValueError:
                # Không phải thư mục ngày -> bỏ qua (vd: 'fallback')
                continue

            # Kiểm tra thời gian đã tạo thư mục
            age_days = (now - folder_date).days
            if age_days > max_days:
                shutil.rmtree(entry_path)  # Xoá thư mục log cũ
                system_logger.info(f"Đã xóa thư mục chứa log hệ thống: {entry_path}")
    except Exception as e:
        system_logger.error(f"Gặp lỗi trong quá trình xóa thư mục chứa log hệ thống: {e}")

# Formatter: Định dạng log với đầy đủ các thông tin
_formatter = logging.Formatter(
    '%(asctime)s %(levelname)s:\t %(filename)s - Line: %(lineno)d message: %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S %p'
)

# Tạo đường dẫn tệp log theo ngày
def _log_file_path():
    """
    Tạo thư mục chứa log cho ngày mới
    """
    day_str = datetime.now().strftime("%d-%m-%y")
    log_dir = os.path.join(SYSTEM_LOG_DIRECTORY, day_str)
    os.makedirs(log_dir, exist_ok=True)

    # Xóa các thư mục log nếu quá thời gian quy định
    _remove_old_logs()
    return os.path.join(log_dir, "system_log.log")

# Cấu hình TimedRotatingFileHandler để xoay file log mỗi ngày vào lúc midnight
log_handler = TimedRotatingFileHandler(
    _log_file_path(), when="midnight", interval=1, backupCount=30, encoding="utf-8"
)
log_handler.setFormatter(_formatter)

# Logger mới cho system_log.log
system_logger = logging.getLogger("system_logger")
system_logger.setLevel(logging.INFO)
system_logger.addHandler(log_handler)

# Ghi log mẫu
system_logger.info("System started")
