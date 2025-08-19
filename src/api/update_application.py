from fastapi import APIRouter, File, UploadFile, Query, Depends
from schemas.schemas import UserAuth
from auth.oauth2 import required_token_user
from controllers.update_application_controller import UpdateApplicationController

router = APIRouter(
    prefix="/update_application",
    tags=["Update Application"]
)

@router.post(
    "/upload/{app_name}/{version}", summary="Tải lên gói cập nhật", description="Tải lên gói cài đặt (zip/exe/dmg/deb/rpm...) cho ứng dụng.")
async def upload_update(
    app_name: str,
    version: str,
    file: UploadFile = File(...),
    platform: str = Query(..., description="vd: win, mac, linux"),
    release_notes: str | None = Query(None, description="Ghi chú phát hành"),
    # checksum_sha256: str | None = Query(None, description="Checksum SHA-256 của file"),
    user_info: UserAuth = Depends(required_token_user)
):
    return await UpdateApplicationController.upload_update(
        app_name=app_name,
        version=version,
        platform=platform,
        file=file,
        release_notes=release_notes,
        # checksum_sha256=checksum_sha256,
        user_info=user_info
    )

@router.get(
    "/check/{app_name}",
    summary="Client kiểm tra có bản cập nhật mới chưa"
)
async def check_update(
    app_name: str,
    current_version: str = Query(...),
    platform: str = Query(..., description="vd: win, mac, linux")
):
    return await UpdateApplicationController.check_update(
        app_name=app_name,
        current_version=current_version,
        platform=platform
    )

@router.get(
    "/versions/{app_name}",
    summary="Liệt kê các phiên bản đã upload"
)
async def list_versions(
    app_name: str,
    platform: str | None = Query(None)
):
    return await UpdateApplicationController.list_versions(
        app_name=app_name,
        platform=platform
    )

@router.get(
    "/download/{app_name}/{platform}/{version}/{file_path:path}",
    summary="Tải gói cập nhật",
)
async def download_update(
    app_name: str,
    platform: str,
    version: str,
    file_path: str
):
    return await UpdateApplicationController.download_update(
        app_name=app_name,
        platform=platform,
        version=version,
        file_path=file_path
    )

@router.delete(
    "/version/{app_name}/{platform}/{version}",
    summary="Xoá một phiên bản (yêu cầu quyền cao)"
)
async def delete_version(
    app_name: str,
    platform: str,
    version: str,
    user_info: UserAuth = Depends(required_token_user)
):
    return await UpdateApplicationController.delete_version(
        app_name=app_name,
        platform=platform,
        version=version,
        user_info=user_info
    )
