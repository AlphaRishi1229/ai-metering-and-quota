import asyncio

from httpx import AsyncClient
from sqlalchemy import select

from app.models import UsageLog, User
from app.providers.base import BaseProvider, GenerationResult
from app.providers.claude import get_provider
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


async def test_behavior_for_near_simultaneous_requests_from_same_user(client, db):
    """Behavior for near-simultaneous requests from the same user"""
    # quota=50, multiplier=1.0; prompt of ~40 chars → ~10 tokens → ~10 credits each
    # Two concurrent requests: combined cost ~20 credits ≤ 50, both may succeed
    # OR quota small enough one 402s — key invariant: used_credits never > quota after settlement
    user_id = await create_user(client, quota=50, multiplier=1.0)

    results = await asyncio.gather(
        client.post(f"/users/{user_id}/generate", json={"prompt": "concurrent request one"}),
        client.post(f"/users/{user_id}/generate", json={"prompt": "concurrent request two"}),
        return_exceptions=True,
    )

    statuses = []
    for r in results:
        if isinstance(r, Exception):
            statuses.append("exception")
        else:
            statuses.append(r.status_code)

    # At least one must succeed or one may 402 — neither should crash (5xx)
    assert all(s in (200, 402, "exception") for s in statuses), f"Unexpected statuses: {statuses}"

    # Core invariant: used_credits must not exceed quota after both settle
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.used_credits <= user.quota, (
        f"used_credits={user.used_credits} exceeded quota={user.quota} — SELECT FOR UPDATE failed"
    )
