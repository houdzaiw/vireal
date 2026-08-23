import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentAppUser, SessionDep
from app.models import AppOrderCreate, AppOrderPublic, AppOrdersPublic

router = APIRouter(prefix="/app/orders", tags=["app orders"])


@router.post("", response_model=AppOrderPublic)
def create_order(
    *,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    order_in: AppOrderCreate,
) -> Any:
    """
    Create an App payment order before starting platform payment.
    """
    return crud.create_app_order(
        session=session,
        app_user=current_app_user,
        order_in=order_in,
    )


@router.get("", response_model=AppOrdersPublic)
def read_orders(
    session: SessionDep,
    current_app_user: CurrentAppUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve current App user's orders.
    """
    orders, count = crud.list_app_orders_for_app(
        session=session,
        app_user=current_app_user,
        skip=skip,
        limit=limit,
    )
    return AppOrdersPublic(
        data=[AppOrderPublic.model_validate(order) for order in orders],
        count=count,
    )


@router.get("/{order_id}", response_model=AppOrderPublic)
def read_order(
    session: SessionDep,
    current_app_user: CurrentAppUser,
    order_id: uuid.UUID,
) -> Any:
    """
    Get a current App user's order by ID.
    """
    order = crud.get_app_order_for_app(
        session=session,
        app_user=current_app_user,
        order_id=order_id,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
