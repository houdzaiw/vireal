from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import CurrentAppUser
from app.core.config import settings
from app.models import AppUploadPublic
from app.services.storage import ImageStorageError, get_image_storage

router = APIRouter(prefix="/app/uploads", tags=["app uploads"])


@router.post("/images", response_model=AppUploadPublic)
async def upload_app_image(
    current_app_user: CurrentAppUser,
    file: UploadFile = File(...),
) -> AppUploadPublic:
    """
    Store an App image and return a public URL.
    """
    content = await file.read(settings.MAX_UPLOAD_IMAGE_BYTES + 1)
    image_storage = get_image_storage()
    try:
        stored_image = image_storage.store_app_image(
            app_user_id=current_app_user.id,
            content=content,
            uploaded_content_type=file.content_type,
        )
    except ImageStorageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    return AppUploadPublic(
        url=stored_image.url,
        content_type=stored_image.content_type,
        size=stored_image.size,
    )
