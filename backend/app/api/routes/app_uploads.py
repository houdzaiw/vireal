import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentAppUser, SessionDep
from app.core.config import settings
from app.models import AppUpload, AppUploadPublic
from app.services.storage import (
    ImageStorageError,
    build_r2_app_image_url,
    get_image_storage,
)

router = APIRouter(prefix="/app/uploads", tags=["app uploads"])


@router.post("/images", response_model=AppUploadPublic)
async def upload_app_image(
    session: SessionDep,
    current_app_user: CurrentAppUser,
    file: UploadFile = File(...),
) -> AppUploadPublic:
    """
    Store an App image and return a stable application URL.
    """
    content = await file.read(settings.MAX_UPLOAD_IMAGE_BYTES + 1)
    image_storage = get_image_storage()
    try:
        stored_image = await run_in_threadpool(
            image_storage.store_app_image,
            app_user_id=current_app_user.id,
            content=content,
            uploaded_content_type=file.content_type,
        )
    except ImageStorageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    expires_at = datetime.now(UTC) + timedelta(hours=settings.APP_MEDIA_RETENTION_HOURS)
    upload = AppUpload(
        app_user_id=current_app_user.id,
        url=stored_image.url,
        object_key=stored_image.object_key,
        content_type=stored_image.content_type,
        size=stored_image.size,
        expires_at=expires_at,
    )
    try:
        session.add(upload)
        session.commit()
        session.refresh(upload)
    except SQLAlchemyError:
        session.rollback()
        await run_in_threadpool(image_storage.delete_object, stored_image.object_key)
        raise HTTPException(status_code=500, detail="Unable to record image upload")
    return AppUploadPublic.model_validate(upload)


def _get_active_upload(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    url: str,
) -> AppUpload:
    upload = session.exec(
        select(AppUpload).where(
            AppUpload.app_user_id == current_app_user.id,
            AppUpload.url == url,
            AppUpload.status == "active",
            AppUpload.expires_at > datetime.now(UTC),
        )
    ).first()
    if upload is None:
        raise HTTPException(status_code=404, detail="Image upload not found")
    return upload


@router.get("/images/{app_user_id}/{filename}", include_in_schema=False)
def read_app_image(
    session: SessionDep,
    app_user_id: uuid.UUID,
    filename: str,
    current_app_user: CurrentAppUser,
) -> RedirectResponse:
    """Authorize an App user and redirect to a short-lived private image URL."""
    image_url = build_r2_app_image_url(
        app_user_id=app_user_id,
        filename=filename,
    )
    upload = _get_active_upload(
        session=session,
        current_app_user=current_app_user,
        url=image_url,
    )
    try:
        signed_url = get_image_storage().create_object_read_url(
            upload.object_key,
            expires_in=settings.R2_DOWNLOAD_URL_EXPIRE_SECONDS,
        )
    except ImageStorageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    return RedirectResponse(
        signed_url,
        status_code=307,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/images/{app_user_id}/{filename}/content", include_in_schema=False)
def read_app_image_content(
    session: SessionDep,
    app_user_id: uuid.UUID,
    filename: str,
    current_app_user: CurrentAppUser,
) -> Response:
    """Read a private image through the API to avoid browser-to-R2 CORS issues."""
    image_url = (
        build_r2_app_image_url(app_user_id=app_user_id, filename=filename)
        if settings.APP_IMAGE_STORAGE_BACKEND == "r2"
        else f"/uploads/images/{app_user_id}/{filename}"
    )
    _get_active_upload(
        session=session,
        current_app_user=current_app_user,
        url=image_url,
    )
    try:
        image = get_image_storage().read_app_image(image_url)
    except ImageStorageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    return Response(
        content=image.content,
        media_type=image.content_type,
        headers={"Cache-Control": "private, no-store"},
    )
