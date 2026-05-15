# Phase B-0 — Composition executions: design doc

**Status**: ready-for-impl after first-round review (20 points addressed)
**Prereq**: read [`project_plan_compositions_workflow_engine.md`](../../../.claude/projects/-opt-bigmcp/memory/project_plan_compositions_workflow_engine.md) (memo) for the architectural thesis. This doc operationalizes B-0 with all review feedback integrated.

---

## 0. Scope

Build the durable suspension infrastructure that turns compositions from synchronous DAG runs into resumable state machines. Expose them to MCP clients via standard primitives (`tools`, `resources/subscribe`, `notifications/resources/updated`) — no proprietary protocol.

**In scope**:
1. New tables `composition_execution`, `execution_step_event`, `pending_notification`
2. Refactor `app/orchestration/composition_executor.py` to be yield-able + resumable
3. Three execution patterns (A sync / B progress / C detached) auto-routed
4. MCP resource `composition://executions/{id}` (read + subscribe, scoped per-user)
5. Pending notification queue per MCP session for replay-on-reconnect
6. `composition_status` meta-tool as polling fallback for older clients
7. Endpoints + UI page to manage executions
8. Orphan recovery on backend restart
9. The 15 invariants below, integrated with first-round review fixes

**Explicit non-scope (deferred)**:
- All step types beyond `tool` and `_test_suspend` → B-1 to B-5
- Cron triggers + `composition_schedule` table → B-2
- Parallel step execution (current executor is sequential, B-0 stays sequential) → B-6
- Cross-user notifications → B-1
- LLM cost accounting → B-5
- Multi-instance backend deployment (assumes single backend instance)

A `_test_suspend` step type is added in B-0 ONLY to validate the suspension mechanism end-to-end. Behind a debug flag, never exposed via tools/list.

---

## 1. The 15 invariants — concrete decisions (post-review)

### #1 — Idempotence on resume (revised)
**Decision**: idempotence is **author-controlled, never tool-claimed**. The MCP spec explicitly says tool annotations (`idempotentHint`) are untrusted. Basing safety decisions on them is a vulnerability.

Add `step.idempotent: bool` (default `false`) to step definition. The composition author marks a step idempotent if they know the underlying tool is. Default-safe.

```python
state.step_status[step_id] = "in_progress"
state.step_started_at[step_id] = now()
await persist_state(execution_id, state)

try:
    result = await invoke_tool(...)
except Exception as e:
    state.step_status[step_id] = "failed"
    state.step_results[step_id] = {"error": str(e)}
    await persist_state(execution_id, state)
    raise

state.step_status[step_id] = "succeeded"
state.step_results[step_id] = result
await persist_state(execution_id, state)
```

On resume, if `step_status[step_id] == "in_progress"`:
- If `step.idempotent == true` → re-run safely
- Else → mark step `failed` with reason `"resumed_after_crash_non_idempotent"`. Apply normal failure policy (skip if `optional=true`, else fail composition). User can retry from UI.

### #2 — Sequential execution in B-0 (simplified)
**Decision**: B-0 execution is **strictly sequential**. The current executor (`composition_executor.py`) is already sequential despite the `depends_on` field. We do not introduce parallelism in B-0.

Consequence: invariants around "parallel siblings + suspension" disappear. No race during step execution.

Parallel/branch/loop control flow → Phase B-6.

### #3 — Incremental state serialization
**Decision**: persist after EVERY step, not just at suspension. Enables crash recovery anywhere.

Step results are stored inline in `state.step_results` (JSONB). **No spillover table.** Hard limit 1MB per step result (soft warning at 256KB logged). Postgres TOAST handles up to ~1GB row size internally; we cap well below to keep query perf reasonable. If we ever see > 1MB results in prod, revisit (YAGNI for B-0).

### #4 — Cancel mid-flight
**Decision**: `cancel_requested` flag on the row, checked at every step boundary (entry of `_execute_step`).

In-flight tool calls run to completion — their effects are committed upstream anyway, and Postgres COMMIT is the boundary that matters. Each step has a hard `default_timeout=60s` (already in current code) so a hung tool can't block cancel forever.

For users wanting hard-cancel of in-flight calls (e.g., abort an LLM stream), add `step.cancellable: true` opt-in (default `false`). When true, executor uses `asyncio.wait_for(...)` with timeout matching `cancel_check_interval=5s`. Default off for safety.

### #5 — Sub-composition durable
**Decision**: `parent_execution_id` FK on `composition_execution` + bidirectional resume chain.

Parent suspended on a step that called a sub-composition:
```
parent.state.suspension = {
  "type": "subcomposition",
  "child_execution_id": "abc",
  "child_uri": "composition://executions/abc"
}
parent.state.current_step_id = "<the step that called the child>"
```

Child execution carries `parent_execution_id`. When child reaches a terminal state (completed/failed/expired/cancelled):
1. Update child row
2. Look up parent via `parent_execution_id`
3. If parent.status == "suspended" AND parent.state.suspension.child_execution_id == this child:
   - Inject child result into `parent.state.step_results[parent.state.current_step_id]`
   - Trigger `executor.resume(parent.id, child_result)` (background)

Recursion: `state.depth` tracks nesting. Default max `MAX_SUBCOMPOSITION_DEPTH=5`. Incremented at child creation, checked before invoking. On exceed → child execution starts as `failed` with reason `"max_subcomposition_depth_exceeded"`.

Subscription propagation: when child fires `notifications/resources/updated`, the executor ALSO fires the same notification on the parent's URI. The parent's resource content reflects the child indirectly (via `child_uri` pointer in its `suspension` payload), so any client subscribed to the parent learns "something changed in my subtree" and can fetch.

### #6 — Per-user resource scoping
**Decision**: every `resources/list`, `resources/read`, `resources/subscribe` operation on `composition://executions/*` filters by `user_id == current_user.id`.

Implementation: in `mcp_unified.py:list_resources` and `read_resource`, when URI matches `composition://executions/{id}`, query:
```sql
SELECT * FROM composition_execution WHERE id = ? AND user_id = ?
```

If no match → return empty list (for `list`) or 404 (for `read`). No info leak about existence to other users.

Admin governance view (an admin sees all executions in their org) is OUT OF SCOPE for B-0. If needed later: separate URI scheme `composition://admin/org/{org_id}/executions` gated by admin role check. For now, admin uses `GET /api/v1/compositions/{id}/executions` REST endpoint with role check.

### #7 — Fallback for clients without `resources.subscribe` capability
**Decision**: detect at handshake whether the client declared `resources.subscribe` capability. Adapt the response of `tools/call composition_X` accordingly.

- **Has `resources.subscribe`**: structured content `{execution_id, resource_uri, status: "running"}` — client subscribes to track progress.
- **No `resources.subscribe`**: text content with explicit polling instructions, plus structured content pointing at the `composition_status` meta-tool (which we expose universally — see §7).

The `composition_status` meta-tool is added to `pool/definitions.py` alongside `search`, `execute`, `describe_tool`. **Public to all clients**, not just non-subscribers — even clients with subscribe support might prefer one-shot polling for some flows.

### #8 — `notifications/resources/updated` payload
**Decision**: per spec, the notification carries only the URI. Client must call `resources/read` to fetch new content. Saves DB and matches the spec literally.

```json
{ "method": "notifications/resources/updated",
  "params": { "uri": "composition://executions/abc" } }
```

The `pending_notification` queue stores `(session_id, uri, created_at)` tuples — no content payload.

### #9 — Cross-user notifications (DEFERRED to B-1)
B-0 only handles same-user notifications (the user who triggered the execution = the user who gets notified). Approval steps and admin notifications are B-1's concern via a new `user_notification` table. Mentioned here for completeness; do not build in B-0.

### #10 — Triggers unifiés (PARTIAL in B-0)
B-0 implements `trigger ENUM(mcp_call, manual, api)` on the row. `cron` added in B-2, `webhook` added in B-3. The enum is extensible without schema migration.

Table `composition_trigger(composition_id, type, config jsonb, enabled)` arrives in B-2 where it earns its keep.

### #11 — Quotas + queueing (revised: always queue)
**Decision**: never reject. Always accept the request. Excess executions land in `status='queued'` and a single in-process worker promotes them to `running` as slots free up.

- Hard limit `MAX_CONCURRENT_EXECUTIONS_PER_USER=50` (env, configurable)
- Queue is the `composition_execution` rows themselves (`WHERE status='queued' ORDER BY started_at ASC`)
- Worker = a single asyncio task started in lifespan, does FIFO promote when a slot frees
- The `tools/call` response for queued executions is identical to running — same Pattern C structured content, just `status: "queued"` initially

Single-instance only (see §13). For multi-instance, add a Redis-backed queue.

### #12 — Capability declaration audit
**Already declared correctly** in `mcp_unified.py:485-496`:
- `tools.listChanged: true` ✅
- `resources.subscribe: true` ✅
- `resources.listChanged: true` ✅

**Add in B-0**:
```json
"experimental": {
  "compositions": {
    "version": "1.0",
    "asyncExecution": true,
    "resourceScheme": "composition://executions/{id}",
    "statusTool": "composition_status"
  }
}
```

Hint informatif, optional for compliance.

### #13 — Cost accounting `sample` (DEFERRED to B-5)
B-0 introduces no LLM calls. Accounting infrastructure lands with B-5.

### #14 — Pydantic ↔ runtime mismatch (revised: hard fix)
**Decision**: NO dual-read. Fix the Pydantic schema to match runtime conventions. Reject API requests using legacy `id`/`params` aliases with a clear 422.

```python
class CompositionStep(BaseModel):
    step_id: str
    tool: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    type: Literal["tool", "_test_suspend"] = "tool"  # B-0 types only
    optional: bool = False
    idempotent: bool = False             # NEW for #1
    cancellable: bool = False            # NEW for #4
    retry_strategy: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: Optional[int] = None
```

Why no dual-read: live data already uses `step_id`/`parameters` (verified by audit). The Pydantic schema mismatch was an API-side bug, not a data-side issue. Dual-read would just postpone the cleanup. Fail fast.

### #15 — `server_bindings` deprecation
**Decision**: deprecated in B-0. The field stays on the `Composition` model (no migration), but:
- Marked deprecated in the model docstring
- Frontend stops sending it on POST/PUT
- Executor no longer reads it (already unused in current code)
- Add `${binding.X}` resolver in B-1+ ONLY if a real use case emerges

Verified empty in all live compositions. Carrying dead infra as deprecated > silent removal.

---

## 2. Schema

Three tables (down from four — no spillover after #19 review).

### 2.1 `composition_execution`

```sql
CREATE TABLE composition_execution (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_id      UUID NOT NULL REFERENCES compositions(id) ON DELETE RESTRICT,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    parent_execution_id UUID REFERENCES composition_execution(id) ON DELETE SET NULL,

    status              VARCHAR(20) NOT NULL,
                        -- queued | running | suspended | completed | failed | expired | cancelled

    state               JSONB NOT NULL DEFAULT '{}'::jsonb,
                        -- { step_results, step_status, step_started_at,
                        --   current_step_id, suspension, depth }

    trigger             VARCHAR(20) NOT NULL,  -- mcp_call | manual | api (cron/webhook in B-2/B-3)
    mcp_session_id      TEXT,                  -- to route notifs to the right MCP client
    client_capabilities JSONB,                 -- snapshot at start, used for adaptive negotiation

    cancel_requested    BOOLEAN NOT NULL DEFAULT FALSE,

    started_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMP,             -- TTL based on suspension reason

    result              JSONB,                 -- final result (when completed)
    error               TEXT                   -- failure reason
);

CREATE INDEX idx_compexec_user_status ON composition_execution(user_id, status);
CREATE INDEX idx_compexec_org_status ON composition_execution(organization_id, status);
CREATE INDEX idx_compexec_expiry ON composition_execution(expires_at)
    WHERE status IN ('suspended', 'queued');
CREATE INDEX idx_compexec_parent ON composition_execution(parent_execution_id)
    WHERE parent_execution_id IS NOT NULL;
CREATE INDEX idx_compexec_session ON composition_execution(mcp_session_id)
    WHERE mcp_session_id IS NOT NULL;
```

**FK semantics** (post-review #8):
- `composition_id ON DELETE RESTRICT` — can't drop a composition with executions. Use soft-delete (`Composition.deleted_at`) for compositions with history. Preserves audit.
- `user_id`, `organization_id ON DELETE CASCADE` — when a user/org is hard-deleted, their executions go too.
- `parent_execution_id ON DELETE SET NULL` — child survives parent deletion (orphans become root).

### 2.2 `execution_step_event` (timeline)

```sql
CREATE TABLE execution_step_event (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL REFERENCES composition_execution(id) ON DELETE CASCADE,
    step_id         VARCHAR(64) NOT NULL,
    event_type      VARCHAR(32) NOT NULL,  -- started | succeeded | failed | suspended | skipped | retry
    payload         JSONB,                 -- duration_ms, error, retry_count, ...
    timestamp       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stepev_exec_time ON execution_step_event(execution_id, timestamp);
```

Cleanup job: drop events older than 90 days (background tick). Partitioning deferred until volume warrants.

### 2.3 `pending_notification`

```sql
CREATE TABLE pending_notification (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT NOT NULL,
    uri             TEXT NOT NULL,         -- composition://executions/{id}
    method          VARCHAR(64) NOT NULL DEFAULT 'notifications/resources/updated',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pendnotif_session ON pending_notification(session_id, created_at);
```

Flushed at next `initialize` from that `session_id`. Cleanup: drop > 7 days old.

---

## 3. State machine

```
                  [tools/call composition_X]
                              |
                              v
                       create execution
                              |
              quota >50 concurrent? ──yes──→ status = queued
                              |                       │
                              ↓ no                    │ worker promotes
                       status = running ←─────────────┘
                              |
              ┌───────────────┴──────────────┐
              v                              v
     pure tool steps?                 has suspending step?
              |                              |
              v                              v
        Pattern A/B                  Pattern C: return immediately
        (sync return)                {execution_id, resource_uri}
                                              |
                                              v
                              executor runs steps in background
                                              |
                                              | (each step:
                                              |   1. acquire advisory lock
                                              |   2. mark step in_progress + persist
                                              |   3. invoke tool
                                              |   4. mark succeeded + persist
                                              |   5. release lock)
                                              |
                                  ┌───────────┼────────────┐
                                  v           v            v
                              completed   suspended       failed
                                              |
                                              v
                                   wait for resume signal
                                   (elicit response, callback, time...)
                                              |
                                              v
                                       executor.resume()
                                              |
                                              v
                                       continues until done

Backend restart sweep (lifespan startup):
  UPDATE composition_execution
  SET status = 'failed', error = 'backend_restart_orphan'
  WHERE status = 'running';
  -- suspended and queued are untouched (will resume via event or worker tick)
```

Terminal statuses: `completed | failed | expired | cancelled`. Each emits `notifications/resources/updated` (one final).

---

## 4. Executor refactor

Singleton `ResumableExecutor`, methods stateless (state lives in DB). Background queue worker = one asyncio task started in lifespan that promotes `queued → running` when slots free.

### 4.1 Concurrency model

Sequential within an execution (no parallel steps in B-0).

Cross-execution races (e.g., callback POST vs cancel) handled via Postgres advisory locks:

```python
async def _with_execution_lock(execution_id: UUID, fn):
    async with get_async_session() as db:
        # Lock per execution_id, held for the transaction
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:eid))"),
            {"eid": str(execution_id)}
        )
        return await fn(db)
```

Both `run()` and `resume()` wrap their critical section in `_with_execution_lock`. Other mutators (cancel) too.

### 4.2 Pseudo-code

```python
@dataclass
class Suspend:
    reason: Literal["subcomposition", "_test_suspend"]  # B-0 set; B-1+ adds others
    payload: dict
    ttl_seconds: int

class ResumableExecutor:
    """Singleton. State lives in DB. Methods are stateless wrt instance."""

    async def run(self, execution_id: UUID) -> str:
        """Run from current state until terminal or suspended.
        Returns final status: completed | suspended | failed | cancelled."""
        return await _with_execution_lock(execution_id, self._run_locked)

    async def resume(self, execution_id: UUID, response: Any) -> str:
        """Inject response into the suspended step and continue."""
        async def _resume_locked(db):
            execution = await self._load(db, execution_id)
            if execution.status != "suspended":
                raise BadRequest("not suspended")
            state = ExecutionState.from_jsonb(execution.state)
            state.step_results[state.current_step_id] = response
            state.step_status[state.current_step_id] = "succeeded"
            state.suspension = None
            execution.status = "running"
            await self._save(db, execution, state)
            return await self._run_loop(db, execution, state)
        return await _with_execution_lock(execution_id, _resume_locked)

    async def _run_locked(self, db):
        # Load, then loop
        execution = await self._load(db, ...)
        if execution.status not in ("running", "queued"):
            return execution.status
        if execution.status == "queued":
            execution.status = "running"
            await self._save(db, execution, ...)
        state = ExecutionState.from_jsonb(execution.state)
        return await self._run_loop(db, execution, state)

    async def _run_loop(self, db, execution, state):
        try:
            while True:
                # Cancel boundary check
                if await self._check_cancel(db, execution.id):
                    return await self._mark_terminal(db, execution, "cancelled")

                step = self._next_step(state, execution.composition.steps)
                if step is None:
                    return await self._mark_terminal(db, execution, "completed",
                                                    result=self._extract_result(state))

                outcome = await self._execute_step(step, state, execution, db)

                if isinstance(outcome, Suspend):
                    return await self._mark_suspended(db, execution, state, outcome)

                state.step_results[step.step_id] = outcome
                state.step_status[step.step_id] = "succeeded"
                state.current_step_id = None
                await self._save(db, execution, state)
        except Exception as e:
            logger.exception(f"Execution {execution.id} failed")
            return await self._mark_terminal(db, execution, "failed", error=str(e))

    async def _execute_step(self, step, state, execution, db) -> Any | Suspend:
        # Idempotence guard (#1, revised — author-controlled)
        prior = state.step_status.get(step.step_id)
        if prior == "succeeded":
            return state.step_results[step.step_id]
        if prior == "in_progress":
            if step.idempotent:
                pass  # safe to re-run
            else:
                state.step_status[step.step_id] = "failed"
                state.step_results[step.step_id] = {
                    "error": "resumed_after_crash_non_idempotent"
                }
                await self._save(db, execution, state)
                if step.optional:
                    return None
                raise StepFailed(step.step_id, "non-idempotent step crashed mid-flight")

        # Mark in-progress and persist BEFORE the call (#1)
        state.step_status[step.step_id] = "in_progress"
        state.current_step_id = step.step_id
        state.step_started_at[step.step_id] = now().isoformat()
        await self._save(db, execution, state)
        await self._emit_event(db, execution.id, step.step_id, "started")

        # Dispatch by step type (B-0 only knows 2)
        try:
            if step.type == "tool":
                # Optional hard-cancellable wrapper
                if step.cancellable:
                    return await asyncio.wait_for(
                        self._call_tool(step, state, execution),
                        timeout=step.timeout_seconds or self.default_timeout
                    )
                return await self._call_tool(step, state, execution)
            elif step.type == "_test_suspend":  # B-0 only, debug
                return Suspend(reason="_test_suspend", payload={}, ttl_seconds=300)
            else:
                raise NotImplementedError(f"step type {step.type} not implemented in B-0")
        except Exception:
            state.step_status[step.step_id] = "failed"
            await self._save(db, execution, state)
            raise

    @staticmethod
    async def run_detached(execution_id: UUID):
        """Wrapper for asyncio.create_task. Handles fire-and-forget exceptions."""
        try:
            executor = get_executor()
            await executor.run(execution_id)
        except Exception:
            logger.exception(f"Detached execution {execution_id} crashed")
            # Best-effort mark failed (the inner _run_loop should already have)
            try:
                async with get_async_session() as db:
                    await db.execute(
                        text("UPDATE composition_execution SET status='failed', "
                             "error='detached_crash', updated_at=NOW() "
                             "WHERE id=:eid AND status='running'"),
                        {"eid": str(execution_id)}
                    )
                    await db.commit()
            except Exception:
                logger.exception("Could not mark crashed execution as failed")
```

### 4.3 Orphan recovery on backend restart

In `app/main.py:_startup_impl`, after DB init, before serving requests:

```python
async with async_session_maker() as db:
    result = await db.execute(text(
        "UPDATE composition_execution SET "
        "status='failed', "
        "error='backend_restart_orphan', "
        "updated_at=NOW() "
        "WHERE status='running' "
        "RETURNING id"
    ))
    orphans = result.scalars().all()
    if orphans:
        logger.warning(f"Marked {len(orphans)} orphan executions as failed")
    await db.commit()
```

Suspended and queued executions are untouched. Suspended will resume on event; queued will be picked up by the worker on the next tick.

### 4.4 Background queue worker

Started in lifespan startup, single asyncio task:

```python
async def _queue_promotion_loop():
    while True:
        try:
            async with async_session_maker() as db:
                # For each user with queued executions, promote up to slot
                # capacity. Does ONE pass per tick.
                rows = await db.execute(text("""
                    WITH user_running AS (
                        SELECT user_id, COUNT(*) AS cnt
                        FROM composition_execution
                        WHERE status = 'running'
                        GROUP BY user_id
                    ), promotable AS (
                        SELECT e.id, e.user_id,
                               ROW_NUMBER() OVER (PARTITION BY e.user_id
                                                  ORDER BY e.started_at ASC) AS rn
                        FROM composition_execution e
                        LEFT JOIN user_running u ON u.user_id = e.user_id
                        WHERE e.status = 'queued'
                          AND COALESCE(u.cnt, 0) + ROW_NUMBER()
                              OVER (PARTITION BY e.user_id ORDER BY e.started_at)
                              <= :max_concurrent
                    )
                    UPDATE composition_execution
                    SET status='running'
                    WHERE id IN (SELECT id FROM promotable)
                    RETURNING id;
                """), {"max_concurrent": MAX_CONCURRENT_PER_USER})
                promoted = rows.scalars().all()
                await db.commit()

            for execution_id in promoted:
                asyncio.create_task(ResumableExecutor.run_detached(execution_id))

        except Exception:
            logger.exception("Queue promotion loop iteration failed")

        await asyncio.sleep(QUEUE_TICK_SECONDS)  # default 5s
```

---

## 5. Routing in `tools/call composition_X`

Static analysis decides Pattern A/B/C at call time. No flag on the composition needed (though `extra_metadata.requires_async: true` can force C).

```python
async def call_tool_composition(name: str, arguments: dict, ctx) -> dict:
    composition = await load_composition_by_tool_name(name, ctx.user_id)

    # Static analysis
    suspending = any(
        s.get("type") in {"_test_suspend"}  # B-1+: elicit, wait_callback, etc.
        for s in composition.steps
    )
    forced_async = composition.extra_metadata.get("requires_async") is True
    cron_triggered = ctx.trigger == "cron"
    use_pattern_c = suspending or forced_async or cron_triggered

    # Always create the execution row (queued or running depending on quota)
    execution = await create_execution(
        composition=composition,
        user=ctx.user,
        org=ctx.org,
        trigger=ctx.trigger,
        client_capabilities=ctx.client_capabilities,
        mcp_session_id=ctx.session_id,
        inputs=arguments,
    )

    if not use_pattern_c:
        # Pattern A: sync wait inline
        await ResumableExecutor.run_detached.__wrapped__(execution.id)  # awaitable
        execution = await reload(execution.id)
        return wrap_as_mcp_tool_result(execution.result)

    # Pattern C: detached background
    asyncio.create_task(ResumableExecutor.run_detached(execution.id))

    if ctx.client_capabilities.get("resources", {}).get("subscribe"):
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"Composition started. "
                    f"Subscribe to composition://executions/{execution.id} for updates "
                    f"or call composition_status to poll."
                )
            }],
            "structuredContent": {
                "execution_id": str(execution.id),
                "resource_uri": f"composition://executions/{execution.id}",
                "status": execution.status  # 'running' or 'queued'
            },
            "isError": False
        }

    # Fallback: client without subscribe
    return {
        "content": [{
            "type": "text",
            "text": (
                f"Composition started. Your client doesn't support resource subscriptions, "
                f"so use either:\n"
                f"  - composition_status(execution_id=\"{execution.id}\") to poll\n"
                f"  - https://bigmcp.cloud/app/compositions/executions/{execution.id} (web UI)"
            )
        }],
        "structuredContent": {
            "execution_id": str(execution.id),
            "status": execution.status,
            "polling_tool": "composition_status",
            "webapp_url": f"https://bigmcp.cloud/app/compositions/executions/{execution.id}"
        },
        "isError": False
    }
```

---

## 6. MCP resource handler

### 6.1 `resources/list`
Returns `composition://executions/{id}` for executions of the current user.

**Default filter**: only non-terminal statuses (`running`, `suspended`, `queued`). Completed/failed/expired/cancelled are accessible via `resources/read` (they show up in UI + REST API), but pollute `resources/list` if all returned. Configurable via params if a future use case demands.

**Pagination**: per spec, supports `cursor` param. Page size 50.

### 6.2 `resources/read`
For URI `composition://executions/{id}`:
1. Parse UUID from URI; reject malformed
2. Query `WHERE id = ? AND user_id = current_user.id`
3. If no row → 404 (no info leak)
4. Return:
```json
{
  "uri": "composition://executions/abc",
  "mimeType": "application/json",
  "text": "{\"status\":\"suspended\",\"current_step_id\":\"3\",\"suspension\":{\"type\":\"subcomposition\",\"child_uri\":\"composition://executions/def\"},\"step_results\":{...},\"started_at\":\"...\"}"
}
```

For `suspended` with `subcomposition` reason: include `child_uri` so client can recursively subscribe if it wants.

### 6.3 `resources/subscribe` and `resources/unsubscribe`
Track `(session_id, uri)` pairs in-memory `Dict[str, Set[str]]`. On state transition of a subscribed execution:
1. If the session is connected → push `notifications/resources/updated` immediately
2. Else → `INSERT INTO pending_notification`

For sub-composition propagation (#5/7): when child changes, also fire on parent's URI if parent is suspended on this child. Recursively up the chain.

### 6.4 Notification flush on `initialize`
When a session sends `initialize` (could be reconnecting):
1. `SELECT uri FROM pending_notification WHERE session_id = ? ORDER BY created_at`
2. Push each as `notifications/resources/updated`
3. `DELETE` the rows

---

## 7. The `composition_status` meta-tool

Added to `pool/definitions.py` alongside `search`, `execute`, `describe_tool`. **Public to all clients** — both subscribers and non-subscribers can use it.

Returns SUMMARY only (not full step results) to keep polls cheap. Full state via `resources/read` or REST endpoint.

```python
{
    "name": "composition_status",
    "title": "Check the status of a composition execution",
    "description": (
        "Return summary status of a composition execution started via `composition_X` "
        "or scheduled. Returns status, current step, error if any. "
        "For full step-by-step results, read the resource composition://executions/{id} "
        "or fetch GET /api/v1/compositions/executions/{id}."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "execution_id": {"type": "string", "description": "UUID returned by composition tool call"}
        },
        "required": ["execution_id"]
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "execution_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["queued","running","suspended","completed","failed","expired","cancelled"]
            },
            "current_step_id": {"type": ["string","null"]},
            "suspension_reason": {"type": ["string","null"]},
            "error": {"type": ["string","null"]},
            "expires_at": {"type": ["string","null"]},
            "started_at": {"type": "string"},
            "updated_at": {"type": "string"},
            "result_uri": {
                "type": ["string","null"],
                "description": "When completed, points to the full result resource"
            }
        },
        "required": ["execution_id", "status", "started_at", "updated_at"]
    },
    "annotations": {
        "title": "Composition status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
}
```

---

## 8. Endpoints

```
GET    /api/v1/compositions/executions
       Query: ?status=running,suspended  ?limit=50  ?offset=0
       Returns: list of execution summaries for current user

GET    /api/v1/compositions/executions/{id}
       Auth: JWT user MUST own the execution
       Returns: full detail (state, events, result/error)

POST   /api/v1/compositions/executions/{id}/cancel
       Auth: JWT user MUST own the execution
       Sets cancel_requested=true
       Returns: 202 Accepted

POST   /api/v1/compositions/executions/{id}/resume
       Auth: B-0 ONLY accepts JWT user owner
       (B-3 will add HMAC webhook token alternative on the SAME endpoint
        via Authorization scheme branching)
       Body: { response: <step-type-specific> }
       In B-0: only accepts response for `_test_suspend` (debug)

GET    /api/v1/compositions/{composition_id}/executions
       Auth: JWT user MUST be ADMIN/OWNER of the composition's org
       Admin governance view: all executions of a composition (audit)
```

---

## 9. UI

### Page `/app/compositions/executions`
- List per user, default filter `status IN (running, suspended, queued)`
- Toggle to also show terminal statuses
- Columns: composition name, status badge, started_at, last_update, current step, actions (cancel | view)
- Auto-refresh polling every 5s for non-terminal statuses (B-0 ships polling; SSE polish later)
- Empty state: "No executions yet."

### Page `/app/compositions/executions/{id}`
- Header: composition name + status + cancel button (if running/suspended)
- Timeline of `execution_step_event` rows
- Current step highlighted if `running` or `suspended`
- For `suspended` with `_test_suspend`: a button "Provide test response" that POSTs to `/resume`
- Final result (if `completed`) or error (if `failed`) at the bottom

### Banner global (in MainLayout)
- Counts `suspended` executions for current user (cheap query, every page load)
- Click → navigates to executions page filtered by suspended

---

## 10. Tests (14 must-pass before merge)

```python
# tests/test_composition_executions_b0.py

# Core lifecycle
async def test_sync_composition_unchanged():
    """Pattern A: existing sync compo runs end-to-end identically (regression)."""

async def test_test_suspend_round_trip():
    """B-0 mechanism: _test_suspend yields, manual resume continues."""

async def test_pattern_c_resource_flow():
    """tools/call → immediate return + resource subscribe + notif on complete."""

async def test_capability_negotiation_no_subscribe():
    """Client without resources.subscribe gets the text fallback + polling tool hint."""

# Safety / robustness
async def test_idempotence_after_crash_default_safe():
    """Step in_progress on resume + step.idempotent=false → fails with reason, not re-fire."""

async def test_idempotence_after_crash_marked_idempotent():
    """Step in_progress on resume + step.idempotent=true → re-runs cleanly."""

async def test_orphan_recovery_on_restart():
    """Running execution + simulated restart → marked failed with reason backend_restart_orphan."""

async def test_advisory_lock_serializes_mutations():
    """Concurrent cancel + resume on same execution → no data race, deterministic outcome."""

async def test_cancel_during_running():
    """Cancel mid-flight → in-flight step finishes, execution marked cancelled."""

# Sub-composition
async def test_subcomposition_durable():
    """Compo A calls compo B; B suspends; A status = suspended; resume B → A continues."""

async def test_subcomposition_depth_limit():
    """Nesting > 5 → child execution starts as failed with depth error."""

# Quotas
async def test_quota_promotes_via_queue():
    """User with 50 running + 1 new request → queued, promoted as a slot frees."""

# Resource isolation + notifications
async def test_per_user_resource_isolation():
    """User A cannot read composition://executions/{id_of_user_B} (404, no info leak)."""

async def test_pending_notification_flush_on_reconnect():
    """Disconnected session, state changes, reconnect → notification replayed once, then deleted."""
```

Each test runs in isolation, uses SQLite in-memory + asyncio task fixtures + time mock for the cancel/orphan tests.

---

## 11. Migration

Single Alembic migration `add_composition_executions`. Down-revision: `add_composition_share_request` (latest).

Creates the 3 tables + indexes + FK constraints. Reversible via standard `downgrade()`.

No backfill needed (no in-flight executions exist today since the executor is sync).

---

## 12. Audit log events

Add to `app/models/audit_log.py:AuditAction`:

```python
COMPOSITION_EXECUTION_CREATED   = "composition.execution_created"
COMPOSITION_EXECUTION_STARTED   = "composition.execution_started"   # queued → running
COMPOSITION_EXECUTION_SUSPENDED = "composition.execution_suspended"
COMPOSITION_EXECUTION_RESUMED   = "composition.execution_resumed"
COMPOSITION_EXECUTION_COMPLETED = "composition.execution_completed"
COMPOSITION_EXECUTION_FAILED    = "composition.execution_failed"
COMPOSITION_EXECUTION_CANCELLED = "composition.execution_cancelled"
COMPOSITION_EXECUTION_EXPIRED   = "composition.execution_expired"
```

Emitted from `_mark_terminal`, `_mark_suspended`, `resume`, queue promotion. All carry `resource_type='composition_execution'` and `resource_id=<execution_id>`.

---

## 13. Multi-instance disclaimer

**B-0 assumes single backend instance.** All in-memory structures (subscription map, queue worker) live in one process.

Path to multi-instance (out of B-0 scope but documented):
- Replace in-memory subscription map with Redis pub/sub
- Replace asyncio queue worker with a row-level lease pattern (`SELECT ... FOR UPDATE SKIP LOCKED`)
- Pin MCP SSE sessions to one instance (sticky sessions in nginx) OR fan out notifications cross-instance
- Postgres advisory locks already work across instances (per-database scope)

When prod scales beyond one backend, this becomes an explicit phase (B-7?). Not now.

---

## 14. Decisions (post-review, no longer "open questions")

1. `composition_status` is **public to all clients**, not just non-subscribers (saved 1 conditional, single tool definition).
2. **TTL per Suspend payload** — set by the step type that suspends (`_test_suspend`=300s in B-0; B-1+ types set their own).
3. Subscriptions on **completed executions fire one final notification** on transition, then implicit unsubscribe (the resource is now read-only-and-stable).
4. UI auto-refresh = **polling 5s in B-0**. SSE upgrade is polish, future phase.
5. **No spillover table** for large step results (#19 review). 1MB hard cap, 256KB soft warn, inline JSONB.
6. **No dual-read Pydantic** (#20 review). Hard fix the schema, fail fast on legacy aliases.
7. **B-0 is sequential only** (#2 review). Parallel = B-6.
8. **Single-instance assumption** explicit (#16 review).
9. **Idempotence is author-controlled**, never tool-claimed (#1 review).
10. **Always queue, never reject** when over quota (#9 review).

---

## 15. Out of scope for B-0

- All step types beyond `tool` and `_test_suspend` → B-1 to B-5
- Cron triggers → B-2
- Cross-user notifications (`user_notification` table, banner targeting other user) → B-1
- LLM cost accounting → B-5
- Branch / parallel / loop control flow → B-6
- `${binding.X}` resolver → only if needed in B-1+
- Email out-of-band notifications → optional in B-2
- Multi-instance backend deployment → future phase
- Admin governance resource scheme → future phase
- SSE-pushed UI updates → polish

---

## 16. Estimation (post-review)

| Sub-task | Days |
|---|---|
| Migration + 3 tables + indexes + FKs | 2 |
| Models (SQLAlchemy) + Pydantic schemas + audit actions | 1 |
| Executor refactor (state machine, persistence, idempotence, advisory lock) | 4 |
| Sub-composition support + propagation | 2 |
| Background queue worker + orphan recovery on startup | 1 |
| Pattern routing (A/B/C) in `call_tool_composition` | 1 |
| MCP resource handler (list + read + subscribe + scope) | 2 |
| `composition_status` meta-tool + pool/definitions wiring | 1 |
| Pending notification queue + flush on reconnect | 1 |
| REST endpoints (list/get/cancel/resume) + auth | 1 |
| UI page list + detail + banner | 3 |
| Tests E2E (14 must-pass) | 4 |
| Pydantic mismatch fix (#14) + `server_bindings` deprecation (#15) | 1 |
| Buffer for surprises | 2 |

**Total: ~26 days realistic**, ~20 days minimum.

The +4 vs original 22 covers: orphan recovery + advisory lock + background queue worker + 6 extra tests.

---

## 17. How review feedback was integrated

For traceability, mapping of review points to design changes:

| Review # | Change |
|---|---|
| 1 | §1#1 — author-controlled `step.idempotent`, never trust hints |
| 2 | §1#2 — sequential B-0 explicit, parallel deferred to B-6 |
| 3 | §1#5 — `state.depth` enforcement spelled out |
| 4 | §3, §4.3 — orphan recovery sweep at startup |
| 5 | §4.1 — Postgres advisory lock per execution_id |
| 6 | §4.2 — `run_detached` wrapper handles task exceptions |
| 7 | §1#5, §6.3 — parent-child subscription propagation |
| 8 | §2.1 — FK semantics (RESTRICT for composition, soft-delete) |
| 9 | §1#11 — always queue, never 429 |
| 10 | §7 — `composition_status` returns summary only |
| 11 | §6.1 — `resources/list` filters non-terminal by default + paginated |
| 12 | §8 — `/resume` JWT-only in B-0, webhook auth deferred |
| 13 | §1#3 — JSONB monolithic accepted, optimize-when-bites |
| 14 | §14 — open questions closed |
| 15 | §12 — explicit AuditAction enumeration |
| 16 | §13 — multi-instance disclaimer |
| 17 | §4 — singleton + lifespan-started worker clarified |
| 18 | §10 — tests extended from 8 to 14 |
| 19 | §1#3, §2 — no spillover table, 1MB inline cap |
| 20 | §1#14 — no dual-read Pydantic, hard fix |
