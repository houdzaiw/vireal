from typing import Any

from fastapi import APIRouter

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.models import AppConfigValuesPublic

router = APIRouter(prefix="/app/configs", tags=["app configs"])


@router.get("", response_model=AppConfigValuesPublic)
def read_app_configs(
    session: SessionDep,
    _current_app_user: CurrentAppUser,
) -> Any:
    """
    Return enabled key-value configs for App startup.
    """
    configs = crud.list_enabled_app_configs(session=session)
    return AppConfigValuesPublic(
        data={config.key: config.value for config in configs},
        count=len(configs),
    )
