import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UsageLog
from app.schemas import UsageResponse, UsageLogEntry

router = APIRouter(prefix="/users", tags=["inspection"])


@router.get("/{user_id}/usage", response_model=UsageResponse)
async def get_usage(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    remaining = user.quota - user.used_credits - user.reserved_credits
    return UsageResponse(
        quota=user.quota,
        multiplier=user.multiplier,
        used=user.used_credits,
        reserved=user.reserved_credits,
        remaining=remaining,
    )


@router.get("/{user_id}/usage/history", response_model=list[UsageLogEntry])
async def get_usage_history(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User.id).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    result = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user_id)
        .order_by(desc(UsageLog.created_at))
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return rows
