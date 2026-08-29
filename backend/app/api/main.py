from fastapi import APIRouter

from app.api.routes import (
    admin_app,
    app_auth,
    app_configs,
    app_contents,
    app_generations,
    app_orders,
    app_uploads,
    app_users,
    items,
    login,
    payment_webhooks,
    private,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(app_auth.router)
api_router.include_router(app_users.router)
api_router.include_router(app_uploads.router)
api_router.include_router(app_contents.router)
api_router.include_router(app_generations.router)
api_router.include_router(app_configs.router)
api_router.include_router(app_orders.router)
api_router.include_router(admin_app.router)
api_router.include_router(payment_webhooks.router)


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private.router)
