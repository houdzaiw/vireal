from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.api.main import api_router
from app.core.config import settings
from app.services.storage import get_local_upload_root

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.FASTAPI_ENV != "development":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=(
        f"{settings.API_V1_STR}/openapi.json"
        if settings.FASTAPI_ENV == "development" or settings.PUBLIC_API_DOCS_ENABLED
        else None
    ),
    docs_url=(
        "/docs"
        if settings.FASTAPI_ENV == "development" or settings.PUBLIC_API_DOCS_ENABLED
        else None
    ),
    redoc_url=(
        "/redoc"
        if settings.FASTAPI_ENV == "development" or settings.PUBLIC_API_DOCS_ENABLED
        else None
    ),
    generate_unique_id_function=custom_generate_unique_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(
        dict.fromkeys(
            [
                settings.FRONTEND_HOST.rstrip("/"),
                *(str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS),
            ]
        )
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
if settings.APP_IMAGE_STORAGE_BACKEND == "local":
    uploads_dir = get_local_upload_root()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")
if FRONTEND_DIR.exists():
    app.frontend("/", directory=FRONTEND_DIR)
elif settings.FASTAPI_ENV != "development":
    raise RuntimeError(
        f"Frontend directory '{FRONTEND_DIR}' does not exist. "
        "Run `bun run build` before starting the production backend."
    )
