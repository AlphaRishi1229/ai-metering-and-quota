import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import UsageLog, User
from app.providers.base import BaseProvider, GenerationResult
from app.providers import get_provider
from app.main import app


# --- helpers ---

async def create_user(client: AsyncClient, quota: int, multiplier: float) -> int:
    resp = await client.post("/users/", json={"quota": quota, "multiplier": multiplier})
    assert resp.status_code == 201
    return resp.json()["id"]


# --- scenarios ---

async def test_successful_generation_and_usage_recording(client, db):
    """Successful generation and usage recording"""
    user_id = await create_user(client, quota=10000, multiplier=1.0)
    resp = await client.post(f"/users/{user_id}/generate", json={"prompt": "hello world"})
    assert resp.status_code == 200
    body = resp.json()
    assert "text" in body
    assert body["usage"]["prompt_tokens"] > 0
    assert body["usage"]["completion_tokens"] > 0
    assert body["usage"]["actual_credits"] > 0

    # DB: UsageLog row written with status=success
    result = await db.execute(select(UsageLog).where(UsageLog.user_id == user_id))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert logs[0].actual_credits is not None


async def test_credit_calculation_using_per_user_multiplier(client, db):
    """Credit calculation using a per-user multiplier"""
    # Use multiplier=3.0; verify actual_credits = total_tokens * 3.0
    user_id = await create_user(client, quota=50000, multiplier=3.0)
    resp = await client.post(f"/users/{user_id}/generate", json={"prompt": "test prompt here"})
    assert resp.status_code == 200
    body = resp.json()
    total_tokens = body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]
    expected_credits = int(total_tokens * 3.0)
    assert body["usage"]["actual_credits"] == expected_credits

    # DB: UsageLog actual_credits matches formula
    result = await db.execute(select(UsageLog).where(UsageLog.user_id == user_id))
    log = result.scalars().first()
    assert log.actual_credits == expected_credits


async def test_different_users_receive_different_quota_or_multiplier_behavior(client, db):
    """Different users receiving different quota or multiplier behavior"""
    # User A: multiplier=1.0; User B: multiplier=5.0; same prompt → different credits debited
    prompt = "same prompt for both users"
    user_a = await create_user(client, quota=50000, multiplier=1.0)
    user_b = await create_user(client, quota=50000, multiplier=5.0)

    resp_a = await client.post(f"/users/{user_a}/generate", json={"prompt": prompt})
    resp_b = await client.post(f"/users/{user_b}/generate", json={"prompt": prompt})
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    credits_a = resp_a.json()["usage"]["actual_credits"]
    credits_b = resp_b.json()["usage"]["actual_credits"]
    # B's credits should be ~5x A's (exact ratio depends on MockProvider variance)
    assert credits_b > credits_a

    # DB: each user has exactly one log row
    result_a = await db.execute(select(UsageLog).where(UsageLog.user_id == user_a))
    result_b = await db.execute(select(UsageLog).where(UsageLog.user_id == user_b))
    assert len(result_a.scalars().all()) == 1
    assert len(result_b.scalars().all()) == 1


async def test_quota_enforcement_when_user_has_enough_remaining_credits(client, db):
    """Quota enforcement when a user has enough remaining credits"""
    # Large quota: request must succeed
    user_id = await create_user(client, quota=100000, multiplier=1.0)
    resp = await client.post(f"/users/{user_id}/generate", json={"prompt": "small prompt"})
    assert resp.status_code == 200

    # Verify used_credits > 0 after success
    usage_resp = await client.get(f"/users/{user_id}/usage")
    assert usage_resp.status_code == 200
    assert usage_resp.json()["used"] > 0
    assert usage_resp.json()["remaining"] < 100000


async def test_quota_exceeded_behavior_when_user_does_not_have_enough_remaining_credits(client, db):
    """Quota-exceeded behavior when a user does not have enough remaining credits"""
    # Tiny quota (1 credit) ensures even the smallest request exceeds it
    user_id = await create_user(client, quota=1, multiplier=1.0)
    resp = await client.post(f"/users/{user_id}/generate", json={"prompt": "any prompt"})
    assert resp.status_code == 402
    assert "quota" in resp.json()["detail"].lower() or "exceeded" in resp.json()["detail"].lower()

    # DB: UsageLog row written with status=quota_exceeded
    result = await db.execute(select(UsageLog).where(UsageLog.user_id == user_id))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].status == "quota_exceeded"


async def test_behavior_when_ai_generation_layer_fails(client, db):
    """Behavior when the AI generation layer fails"""

    class ErrorProvider(BaseProvider):
        def estimate_tokens(self, prompt: str) -> int:
            return max(1, len(prompt) // 4)

        async def generate(self, prompt: str) -> GenerationResult:
            raise RuntimeError("AI backend unavailable")

    user_id = await create_user(client, quota=100000, multiplier=1.0)

    # Record used_credits before the failing request
    usage_before = (await client.get(f"/users/{user_id}/usage")).json()["used"]

    app.dependency_overrides[get_provider] = lambda: ErrorProvider()
    try:
        resp = await client.post(f"/users/{user_id}/generate", json={"prompt": "hello"})
    finally:
        del app.dependency_overrides[get_provider]

    assert resp.status_code == 503

    # No credits debited — used_credits unchanged
    usage_after = (await client.get(f"/users/{user_id}/usage")).json()["used"]
    assert usage_after == usage_before

    # DB: UsageLog row written with status=ai_error
    result = await db.execute(select(UsageLog).where(UsageLog.user_id == user_id))
    logs = result.scalars().all()
    assert any(log.status == "ai_error" for log in logs)


async def test_retrieval_of_current_usage_and_remaining_allowance(client, db):
    """Retrieval of current usage and remaining allowance"""
    user_id = await create_user(client, quota=5000, multiplier=2.0)

    # Before any generation
    before = (await client.get(f"/users/{user_id}/usage")).json()
    assert before["quota"] == 5000
    assert before["multiplier"] == 2.0
    assert before["used"] == 0
    assert before["reserved"] == 0
    assert before["remaining"] == 5000

    # After one successful generation
    await client.post(f"/users/{user_id}/generate", json={"prompt": "some prompt text"})
    after = (await client.get(f"/users/{user_id}/usage")).json()
    assert after["used"] > 0
    assert after["remaining"] == after["quota"] - after["used"] - after["reserved"]


async def test_behavior_when_actual_usage_differs_from_estimate(client, db):
    """Behavior when actual usage differs from the pre-request estimate"""
    # MockProvider uses random.uniform(0.9, 1.1) for completion_tokens
    # so actual_credits can differ from estimated_credits.
    # Run enough requests until we find a divergence (mock variance is ±10%).
    user_id = await create_user(client, quota=500000, multiplier=1.0)

    diverged = False
    for _ in range(20):
        resp = await client.post(
            f"/users/{user_id}/generate",
            json={"prompt": "check estimate vs actual divergence"},
        )
        assert resp.status_code == 200
        body = resp.json()
        if body["usage"]["actual_credits"] != body["usage"]["estimated_credits"]:
            diverged = True
            break

    assert diverged, "Expected actual_credits != estimated_credits in at least one of 20 requests (MockProvider ±10% variance)"

    # DB: the diverged row has both estimated_credits and actual_credits set
    result = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user_id)
        .where(UsageLog.status == "success")
    )
    logs = result.scalars().all()
    assert any(
        log.estimated_credits is not None and log.actual_credits is not None
        and log.estimated_credits != log.actual_credits
        for log in logs
    ), "No log row found where estimated_credits != actual_credits"


async def test_concurrent_overflow_rejects_exactly_one(client, db):
    """Two near-simultaneous requests that cannot both fit — exactly one is rejected.

    Deterministic sizing: prompt 'hello there!!' is 13 chars → 3 estimated tokens
    → 3 × 10.0 = 30 estimated credits. With quota=50, whichever request commits its
    reservation first leaves 20 credits; the other sees 30 > 20 and gets a 402. The
    persisted reserved_credits is what carries the first request's in-flight budget
    across to the second request's quota check.

    This drives the endpoint, not the lock in isolation — the in-process ASGI harness
    serializes the two calls, so it cannot reproduce a true DB race. The row lock that
    guarantees this same outcome under real parallelism is proven directly in
    test_select_for_update_locks_the_user_row below.
    """
    user_id = await create_user(client, quota=50, multiplier=10.0)

    results = await asyncio.gather(
        client.post(f"/users/{user_id}/generate", json={"prompt": "hello there!!"}),
        client.post(f"/users/{user_id}/generate", json={"prompt": "hello there!!"}),
        return_exceptions=True,
    )
    statuses = sorted(
        "exception" if isinstance(r, Exception) else r.status_code for r in results
    )

    assert statuses == [200, 402], (
        f"Expected exactly one success and one quota rejection, got {statuses} — "
        f"SELECT FOR UPDATE failed to serialize the concurrent reservations"
    )

    # Winner settled, loser never reserved → no dangling reservation
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.reserved_credits == 0, f"dangling reservation: {user.reserved_credits}"
    assert user.used_credits > 0  # the one that passed was charged actual usage

    # Exactly one success log and one quota_exceeded log
    result = await db.execute(select(UsageLog).where(UsageLog.user_id == user_id))
    logs = result.scalars().all()
    assert sorted(log.status for log in logs) == ["quota_exceeded", "success"]


async def test_concurrent_within_budget_both_succeed(client, db):
    """Near-simultaneous requests that both fit — neither is falsely rejected.

    Guards the opposite failure: an over-eager lock or reservation must not reject a
    request the quota can actually afford. Both reservations (3 credits each) fit in
    quota=200, so both return 200 and both reservations are released to 0 at settle.
    """
    user_id = await create_user(client, quota=200, multiplier=1.0)

    results = await asyncio.gather(
        client.post(f"/users/{user_id}/generate", json={"prompt": "hello there!!"}),
        client.post(f"/users/{user_id}/generate", json={"prompt": "hello there!!"}),
    )
    assert [r.status_code for r in results] == [200, 200]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.reserved_credits == 0  # both reservations released at settle
    assert user.used_credits > 0


async def test_select_for_update_locks_the_user_row(test_engine):
    """Directly prove the row lock the whole quota design rests on.

    The endpoint concurrency tests above run through an in-process ASGI transport on a
    single event loop, which serializes the two requests — they exercise the
    reservation logic but cannot reproduce a real database race. This test races two
    independent connections: while connection A holds SELECT ... FOR UPDATE on a user
    row inside an open transaction, connection B's FOR UPDATE NOWAIT on the same row
    must fail rather than read stale state. That failure is exactly the mechanism that
    serializes concurrent reservations for the same user in production.
    """
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as setup:
        user = User(quota=100, multiplier=1.0)
        setup.add(user)
        await setup.commit()
        user_id = user.id

    async with Session() as a, Session() as b:
        async with a.begin():
            # A acquires and holds the row lock for the duration of this block.
            await a.execute(select(User).where(User.id == user_id).with_for_update())
            # B cannot lock the same row while A holds it. NOWAIT surfaces the
            # contention immediately as an error instead of blocking the test.
            with pytest.raises(DBAPIError):
                async with b.begin():
                    await b.execute(
                        select(User).where(User.id == user_id).with_for_update(nowait=True)
                    )
