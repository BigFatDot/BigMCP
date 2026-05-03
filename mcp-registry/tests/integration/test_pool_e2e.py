"""
End-to-end smoke test of the new pool surface (`search` + `execute`).

Runs the real FastAPI app via httpx ASGITransport, creates a user, bypasses
email verification at the DB level, authenticates with an API key, and
asserts:
    - `tools/list` exposes search + execute (and not orchestrator_*)
    - `search` on an empty account yields 0 matches with helpful hint
    - `execute(goal=...)` on an empty pool returns the empty-pool error
    - Legacy `orchestrator_search_tools` dispatch still works (compat)

Designed to run as a script (`python tests/integration/test_pool_e2e.py`)
inside the backend container — bypasses the pytest-asyncio fixture mismatch
in the repo's conftest.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict


async def main() -> int:
    from sqlalchemy import update
    from httpx import AsyncClient, ASGITransport

    from app.main import app
    from app.db.database import async_session_maker
    from app.models.user import User

    failures: list[str] = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        email = "phase61e2e@example.com"
        await ac.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "SecurePass123", "name": "P61"},
        )
        async with async_session_maker() as db:
            await db.execute(
                update(User).where(User.email == email).values(email_verified=True)
            )
            await db.commit()

        login = await ac.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "SecurePass123"},
        )
        access = login.json()["access_token"]

        api = await ac.post(
            "/api/v1/api-keys",
            json={"name": "p61", "scopes": ["tools:read", "tools:execute"]},
            headers={"Authorization": f"Bearer {access}"},
        )
        secret = api.json()["secret"]
        auth = {"Authorization": f"Bearer {secret}", "Accept": "application/json"}

        init = await ac.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "p61", "version": "0"},
                },
            },
            headers=auth,
        )
        sid = init.headers.get("mcp-session-id")
        if not sid:
            failures.append("missing Mcp-Session-Id on initialize")
        sauth = dict(auth)
        if sid:
            sauth["Mcp-Session-Id"] = sid

        # ---- assertion 1: tools/list shape
        lst = await ac.post(
            "/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=sauth,
        )
        names = [t["name"] for t in lst.json().get("result", {}).get("tools", [])]
        if "search" not in names:
            failures.append("search not in tools/list")
        if "execute" not in names:
            failures.append("execute not in tools/list")
        leftover_orch = [n for n in names if n.startswith("orchestrator_")]
        if leftover_orch:
            failures.append(
                f"orchestrator_* still in tools/list (default flag): {leftover_orch}"
            )

        # ---- assertion 2: empty-account search
        s = await ac.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "search", "arguments": {"query": "anything"}},
            },
            headers=sauth,
        )
        text = s.json().get("result", {}).get("content", [{}])[0].get("text", "")
        if '"loaded_count": 0' not in text:
            failures.append(f"search empty-account did not report 0 matches: {text[:200]}")
        if "broader query" not in text:
            failures.append("search empty hint missing 'broader query' guidance")

        # ---- assertion 3: empty-pool execute returns the helpful error
        e = await ac.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "execute", "arguments": {"goal": "anything"}},
            },
            headers=sauth,
        )
        etxt = e.json().get("result", {}).get("content", [{}])[0].get("text", "")
        if "Pool is empty" not in etxt:
            failures.append(f"execute on empty pool didn't produce expected error: {etxt[:200]}")

        # ---- assertion 4: legacy orchestrator_* dispatch still works
        l = await ac.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "orchestrator_search_tools",
                    "arguments": {"query": "anything"},
                },
            },
            headers=sauth,
        )
        ltxt = l.json().get("result", {}).get("content", [{}])[0].get("text", "")
        if '"results"' not in ltxt:
            failures.append(
                f"legacy orchestrator_search_tools dispatch broken: {ltxt[:200]}"
            )

    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("E2E PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
