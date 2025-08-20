import os
import json
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from fastapi.responses import FileResponse
from fastapi import HTTPException, status
from dotenv import load_dotenv
from utils.constants import HIGH_PRIVILEGE_LIST

load_dotenv()

# Lấy dữ liệu từ .env, nếu ko có thì hiển thì giá trị mặc định
IP_ADDRESS_HOST = os.getenv("IP_ADDRESS_HOST", "NOT_FOUND")
PORT_HOST = os.getenv("PORT_HOST", "NOT_FOUND")

APP_UPDATE_DIR = os.getenv("APP_UPDATE_DIR", "assets/update_application")
Path(APP_UPDATE_DIR).mkdir(parents=True, exist_ok=True)

# Tên file metadata kèm mỗi version
METADATA_FILE = "release.json"

def _safe_join(*parts: str) -> Path:
    """Ghép đường dẫn an toàn và chống traversal."""
    base = Path(APP_UPDATE_DIR).resolve()
    target = base.joinpath(*parts).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail={"Message": "Đường dẫn không hợp lệ"})
    return target

def _normalize_platform(p: str) -> str:
    return p.strip().lower()

def _is_semver(ver: str) -> bool:
    # semver đơn giản: major.minor.patch (mỗi phần là số)
    import re
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", ver.strip()))

def _compare_semver(a: str, b: str) -> int:
    # trả -1 nếu a<b, 0 nếu =, 1 nếu a>b
    pa = [int(x) for x in a.split(".")]
    pb = [int(x) for x in b.split(".")]
    for x, y in zip(pa, pb):
        if x < y: return -1
        if x > y: return 1
    return 0

def _compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

class UpdateApplicationController:

    @staticmethod
    async def upload_update(
        app_name: str,
        version: str,
        platform: str,
        file,
        release_notes: str | None,
        # checksum_sha256: str | None,
        user_info
    ):
        # Yêu cầu đăng nhập
        if not user_info:
            raise HTTPException(status_code=401, detail={"message": "Yêu cầu xác thực"})

        platform = _normalize_platform(platform)
        if not _is_semver(version):
            raise HTTPException(status_code=400, detail={"message": "Version phải theo dạng semver: MAJOR.MINOR.PATCH"})

        # Thư mục đích: /APP_UPDATE_DIR/<app>/<platform>/<version>/
        target_dir = _safe_join(app_name, platform, version)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Lưu file nhị phân
        dst = target_dir / file.filename
        if dst.exists():
            # tránh ghi đè
            raise HTTPException(status_code=409, detail={"message": f"File {file.filename} đã tồn tại"})

        with dst.open("wb") as buffer:
            for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
                buffer.write(chunk)

        # Tính/kiểm checksum nếu cần
        # actual_sha256 = _compute_sha256(dst)
        # if checksum_sha256 and checksum_sha256.lower() != actual_sha256.lower():
        #     # Xoá file nếu checksum sai
        #     try: dst.unlink()
        #     except: pass
        #     raise HTTPException(status_code=400, detail={"message": "Checksum không khớp"})

        # Ghi metadata
        meta = {
            "App": app_name,
            "Platform": platform,
            "Version": version,
            "File": file.filename,
            "Size": dst.stat().st_size,
            # "Sha256": actual_sha256,
            "Release_notes": release_notes or "",
            "Uploaded_by": user_info["Name"],
            "Uploaded_at": datetime.now().isoformat()
        }
        with (target_dir / METADATA_FILE).open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return {
            "Message": "Upload thành công",
            "Metadata": meta
        }

    @staticmethod
    async def list_versions(app_name: str, platform: str | None):
        """
        Hiển thị danh sách các phiên bản đã tải lên của ứng dụng
        """
        base = _safe_join(app_name)
        if not base.exists():
            return {"App": app_name, "Platform": platform, "Versions": []}

        results = []
        platforms = [platform] if platform else [p.name for p in base.iterdir() if p.is_dir()]
        for p in platforms:
            pdir = _safe_join(app_name, _normalize_platform(p))
            if not pdir.exists(): 
                continue
            versions = []
            for v in pdir.iterdir():
                if v.is_dir() and (v / METADATA_FILE).exists() and _is_semver(v.name):
                    with (v / METADATA_FILE).open("r", encoding="utf-8") as f:
                        meta = json.load(f)
                    versions.append(meta)
            # sắp xếp theo semver giảm dần
            versions.sort(key=lambda m: [int(x) for x in m["Version"].split(".")], reverse=True)
            results.append({"Platform": _normalize_platform(p), "Versions": versions})

        return {"app": app_name, "results": results}

    @staticmethod
    async def check_update(app_name: str, current_version: str, platform: str):
        """
        Kiểm tra trên server có phiên bản mới hơn của ứng dụng không
        """
        # Kiểm tra định dạng phiên bản
        if not _is_semver(current_version):
            raise HTTPException(status_code=400, detail={"Message": "current_version định dạng là x.x.x"})

        # Kiểm tra xem có dữ liệu cho nền tảng này không
        pdir = _safe_join(app_name, _normalize_platform(platform))
        if not pdir.exists():
            return {
                "Update_available": False,
                "Reason": f"Không có dữ liệu ứng dụng cho nền tảng {platform}"}

        # Tìm phiên bản lớn nhất trong thư mục
        candidates = [d.name for d in pdir.iterdir() if d.is_dir() and _is_semver(d.name)]
        if not candidates:
            return {
                "Update_available": False,
                "Reason": f"Chưa có phiên bản nào cho ứng dụng {app_name}"}

        # Lấy phiên bản mới nhất và so sánh hai phiên bản, nếu phiên bản ở server lớn hơn thì trả về True
        latest = sorted(candidates, key=lambda s: [int(x) for x in s.split(".")], reverse=True)[0]
        cmp = _compare_semver(current_version, latest)

        # Đọc thông tin ứng dụng từ server
        with (pdir / latest / METADATA_FILE).open("r", encoding="utf-8") as f:
            meta = json.load(f)

        # URL tải về: trỏ tới endpoint download
        # client chỉ cần GET /update_application/download/<app>/<platform>/<version>/<file>
        download_url = f"http://{IP_ADDRESS_HOST}:{PORT_HOST}/update_application/download/{app_name}/{_normalize_platform(platform)}/{latest}/{meta['File']}"

        return {
            "App": app_name,
            "Platform": _normalize_platform(platform),
            "Current_version": current_version,
            "Latest_version": latest,
            "Update_available": cmp < 0,
            "Download_url": download_url,
            "Size": meta.get("Size"),
            # "Sha256": meta.get("sha256"),
            "Release_notes": meta.get("Release_notes", "")
        }

    @staticmethod
    async def download_update(app_name: str, platform: str, version: str, file_path: str):
        """
        Tải về ứng dụng từ máy chủ
        """
        # chuẩn hoá & chống traversal
        safe = file_path.replace("\\", "/").strip()
        target = _safe_join(app_name, _normalize_platform(platform), version, safe)

        if not target.is_file():
            return {"message": f"File {target} không tồn tại"}

        # Content-Type theo đuôi file
        content_type, _ = mimetypes.guess_type(target.name)
        if content_type is None:
            content_type = "application/octet-stream"

        return FileResponse(
            path=str(target),
            media_type=content_type,
            filename=target.name,
            headers={
                # 'attachment' để trình duyệt tải xuống; đổi thành 'inline' nếu muốn mở trực tiếp (pdf/ảnh)
                "Content-Disposition": f'attachment; filename="{target.name}"'
            }
        )

    @staticmethod
    async def delete_version(app_name: str, platform: str, version: str, user_info):
        """
        Xóa một phiên bản ứng dụng trên máy chủ
        """
        if not user_info:
            raise HTTPException(status_code=401, detail={"message": "Yêu cầu xác thực"})

        if user_info.get("Privilege") not in HIGH_PRIVILEGE_LIST:
            raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền xoá phiên bản"})

        vdir = _safe_join(app_name, _normalize_platform(platform), version)
        if not vdir.exists():
            return {"message": "Phiên bản không tồn tại"}

        # Xoá toàn bộ thư mục phiên bản
        import shutil
        shutil.rmtree(vdir)
        return {"Message": f"Đã xoá {app_name}/{platform}/{version}"}
