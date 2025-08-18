import os
import json
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from fastapi.responses import FileResponse
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

APP_UPDATE_DIR = os.getenv("APP_UPDATE_DIR", "/app/updates")
Path(APP_UPDATE_DIR).mkdir(parents=True, exist_ok=True)

# Tên file metadata kèm mỗi version
METADATA_FILE = "release.json"

# Tuỳ hệ thống của bạn
HIGH_PRIVILEGE_LIST = {"Admin", "SuperAdmin", "Root"}

def _safe_join(*parts: str) -> Path:
    """Ghép đường dẫn an toàn và chống traversal."""
    base = Path(APP_UPDATE_DIR).resolve()
    target = base.joinpath(*parts).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail={"message": "Đường dẫn không hợp lệ"})
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
        checksum_sha256: str | None,
        user_info
    ):
        # Yêu cầu đăng nhập
        if not user_info:
            raise HTTPException(status_code=401, detail={"message": "Yêu cầu xác thực"})

        # (tuỳ chọn) bắt buộc quyền cao khi phát hành
        if user_info.get("Privilege") not in HIGH_PRIVILEGE_LIST:
            raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền upload bản cập nhật"})

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
        actual_sha256 = _compute_sha256(dst)
        if checksum_sha256 and checksum_sha256.lower() != actual_sha256.lower():
            # Xoá file nếu checksum sai
            try: dst.unlink()
            except: pass
            raise HTTPException(status_code=400, detail={"message": "Checksum không khớp"})

        # Ghi metadata
        meta = {
            "app": app_name,
            "platform": platform,
            "version": version,
            "file": file.filename,
            "size": dst.stat().st_size,
            "sha256": actual_sha256,
            "release_notes": release_notes or "",
            "uploaded_by": user_info.get("Name"),
            "uploaded_at": datetime.utcnow().isoformat() + "Z"
        }
        with (target_dir / METADATA_FILE).open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return {
            "message": "Upload thành công",
            "metadata": meta
        }

    @staticmethod
    async def list_versions(app_name: str, platform: str | None):
        base = _safe_join(app_name)
        if not base.exists():
            return {"app": app_name, "platform": platform, "versions": []}

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
            versions.sort(key=lambda m: [int(x) for x in m["version"].split(".")], reverse=True)
            results.append({"platform": _normalize_platform(p), "versions": versions})

        return {"app": app_name, "results": results}

    @staticmethod
    async def check_update(app_name: str, current_version: str, platform: str):
        if not _is_semver(current_version):
            raise HTTPException(status_code=400, detail={"message": "current_version phải là semver"})

        pdir = _safe_join(app_name, _normalize_platform(platform))
        if not pdir.exists():
            return {"update_available": False, "reason": "Không có dữ liệu cho platform này"}

        # tìm phiên bản lớn nhất
        candidates = [d.name for d in pdir.iterdir() if d.is_dir() and _is_semver(d.name)]
        if not candidates:
            return {"update_available": False, "reason": "Chưa có phiên bản nào"}

        latest = sorted(candidates, key=lambda s: [int(x) for x in s.split(".")], reverse=True)[0]
        cmp = _compare_semver(current_version, latest)

        with (pdir / latest / METADATA_FILE).open("r", encoding="utf-8") as f:
            meta = json.load(f)

        # URL tải về: trỏ tới endpoint download
        # client chỉ cần GET /update_application/download/<app>/<platform>/<version>/<file>
        download_url = f"/update_application/download/{app_name}/{_normalize_platform(platform)}/{latest}/{meta['file']}"

        return {
            "app": app_name,
            "platform": _normalize_platform(platform),
            "current_version": current_version,
            "latest_version": latest,
            "update_available": cmp < 0,
            "download_url": download_url,
            "size": meta.get("size"),
            "sha256": meta.get("sha256"),
            "release_notes": meta.get("release_notes", "")
        }

    @staticmethod
    async def download_update(app_name: str, platform: str, version: str, file_path: str):
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
        return {"message": f"Đã xoá {app_name}/{platform}/{version}"}
