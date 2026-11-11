from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.services.media_grants import resolve_read_token
from app.services.resource_limits import delivery_reads, enabled
from app.services.storage import ImageStorageError, R2ImageStorage, get_image_storage

router = APIRouter(prefix="/app/media", tags=["app media"])


@router.get("/read", response_class=StreamingResponse, include_in_schema=False)
def read_media(
    request: Request, token: str = Query(max_length=1024)
) -> StreamingResponse:
    if not enabled():
        raise HTTPException(404, "Media not found")
    key, delivery = resolve_read_token(token)
    storage = get_image_storage()
    if not isinstance(storage, R2ImageStorage):
        raise HTTPException(404, "Media not found")
    try:
        with delivery_reads(delivery):
            stream, content_type, content_range = storage.open_metered_object(
                key, request.headers.get("range")
            )
    except ImageStorageError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    range_headers = (
        {"Content-Range": content_range} if content_range is not None else {}
    )
    return StreamingResponse(
        stream.chunks,
        status_code=206 if content_range else 200,
        media_type=content_type,
        headers={
            "Content-Length": str(stream.size),
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Accept-Ranges": "bytes",
            **range_headers,
        },
        background=BackgroundTask(stream.close),
    )
