import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UsageLog
from app.schemas import GenerateRequest, GenerateResponse, UsageDetail
from app.providers.base import BaseProvider
from app.providers.claude import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["generate"])


@router.post("/{user_id}/generate", response_model=GenerateResponse, status_code=200)
async def generate(
    user_id: int,
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    provider: BaseProvider = Depends(get_provider),
):
    # --- estimate (sync, outside any TX) ---
    estimated_tokens = provider.estimate_tokens(body.prompt)

    # --- RESERVE TX: SELECT FOR UPDATE, quota check, increment reserved_credits ---
    quota_exceeded = False
    async with db.begin():
        result = await db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        estimated_credits = int(estimated_tokens * user.multiplier)

        remaining = user.quota - user.used_credits - user.reserved_credits
        if estimated_credits > remaining:
            quota_exceeded = True
        else:
            user.reserved_credits += estimated_credits
        # TX commits here (end of async with block) — lock released

    # Write quota_exceeded log OUTSIDE the reserve TX so it is not rolled back (D-22)
    # ponytail: separate TX for log write ensures it commits even when quota check fails
    if quota_exceeded:
        try:
            async with db.begin():
                db.add(UsageLog(
                    user_id=user_id,
                    prompt_tokens=estimated_tokens,
                    completion_tokens=0,
                    estimated_credits=None,
                    actual_credits=None,
                    status="quota_exceeded",
                ))
        except Exception:
            logger.error("Failed to write quota_exceeded UsageLog for user_id=%s", user_id)
        raise HTTPException(status_code=402, detail="Quota exceeded")

    reserved = True
    settled = False
    generation_result = None
    # multiplier captured here — won't change mid-request
    multiplier = user.multiplier

    try:
        # --- AI GENERATION (outside any TX) ---
        generation_result = await provider.generate(body.prompt)

        # --- SETTLE TX: SELECT FOR UPDATE, debit actual, release reservation ---
        actual_credits = int(
            (generation_result.prompt_tokens + generation_result.completion_tokens)
            * multiplier
        )
        async with db.begin():
            result = await db.execute(
                select(User).where(User.id == user_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            # user must exist here (we just checked above); skip None guard
            user.reserved_credits -= estimated_credits
            user.used_credits += actual_credits

            db.add(UsageLog(
                user_id=user_id,
                prompt_tokens=generation_result.prompt_tokens,
                completion_tokens=generation_result.completion_tokens,
                estimated_credits=estimated_credits,
                actual_credits=actual_credits,
                status="success",
            ))
            # TX commits here

        settled = True

    except HTTPException:
        raise  # propagate 404 etc. unchanged

    except Exception as exc:
        # AI error OR settle TX error — log and return 503
        logger.error(
            "generate failed for user_id=%s: %s",
            user_id,
            exc,
            exc_info=True,
        )
        # Write ai_error log (D-22: before returning error response)
        try:
            async with db.begin():
                db.add(UsageLog(
                    user_id=user_id,
                    prompt_tokens=estimated_tokens,
                    completion_tokens=0,
                    estimated_credits=None,
                    actual_credits=None,
                    status="ai_error",
                ))
        except Exception:
            logger.error("Failed to write ai_error UsageLog for user_id=%s", user_id)

        raise HTTPException(status_code=503, detail="AI generation failed")

    finally:
        if reserved and not settled:
            # Release reservation — undo the reserved_credits increment (D-16)
            try:
                async with db.begin():
                    result = await db.execute(
                        select(User).where(User.id == user_id).with_for_update()
                    )
                    u = result.scalar_one_or_none()
                    if u is not None:
                        u.reserved_credits -= estimated_credits
            except Exception:
                logger.error(
                    "Failed to release reservation for user_id=%s estimated_credits=%s",
                    user_id,
                    estimated_credits,
                )

    return GenerateResponse(
        text=generation_result.text,
        usage=UsageDetail(
            prompt_tokens=generation_result.prompt_tokens,
            completion_tokens=generation_result.completion_tokens,
            estimated_credits=estimated_credits,
            actual_credits=actual_credits,
        ),
    )
