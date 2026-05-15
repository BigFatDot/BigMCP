# Phase B-0 — Composition executions: design doc

**Status**: ready-for-impl after two review rounds (35 points addressed)
**Prereq**: read [`project_plan_compositions_workflow_engine.md`](../../../.claude/projects/-opt-bigmcp/memory/project_plan_compositions_workflow_engine.md) for the architectural thesis. This doc operationalizes B-0 with all review feedback integrated.

---

## 0. Scope

Build the durable suspension infrastructure that turns compositions from synchronous DAG runs into resumable state machines. Expose them to MCP clients via standard primitives (`tools`, `resources/subscribe`, `notifications/resources/updated`) — no proprietary protocol.

**In scope**:
1. New tables `composition_execution`, `execution_step_event`, `pending_notification`
2. Refactor `app/orchestration/composition_executor.py` to be yield-able + resumable
3. Three execution patterns (A sync / B progress / C detached) auto-routed
4. MCP resource `composition://executions/{id}` (read + subscribe, scoped per-user)
5. Pending notification queue per MCP session for replay-on-reconnect
6. `composition_status` meta-tool as polling fallback
7. Endpoints + UI page to manage executions
8. Orphan recovery on backend restart
9. The 15 invariants below, integrated with two rounds of review fixes

**Explicit non-scope (deferred)**:
- All step types beyond `tool` and `_test_suspend` → B-1 to B-5
- Cron triggers + `composition_schedule` table → B-2
- Parallel step execution (current executor is sequential) → B-6
- Cross-user notifications → B-1
- LLM cost accounting → B-5
- Multi-instance backend deployment

A `_test_suspend` step type is added in B-0 ONLY to validate the suspension mechanism. Behind a debug flag, never exposed via tools/list.

---

## 1. The 15 invariants — concrete decisions

### #1 — Idempotence on resume (author-controlled)
**Decision**: idempotence is **author-controlled, never tool-claimed**. The MCP spec says tool annotations (`idempotentHint`) are untrusted; basing safety on them is a vulnerability.

Add `step.idempotent: bool` (default `false`) to step definition. The composition author marks a step idempotent only if they know calling it N times has the same effect as once (NOT just "harmless").

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
- `step.idempotent == true` → re-run safely
- Else → mark step `failed` with reason `"resumed_after_crash_non_idempotent"`. Apply normal failure policy (skip if `optional=true`, else fail composition).

**Edge case acknowledged**: if persist of `in_progress` succeeded but persist of `succeeded` failed AND tool call actually succeeded, we get a false-negative "non-idempotent crash" on resume. Acceptable — user retries from UI knowing the original side-effect did happen, and re-running a non-idempotent step is more dangerous than asking the user to investigate. Adding a separate `step_actually_invoked` marker is more complexity for marginal value.

### #2 — Sequential execution in B-0
**Decision**: B-0 execution is strictly sequential. The current executor is already sequential despite the `depends_on` field (verified — it iterates `composition.steps` in declaration order; depends_on is data-only). B-0 inherits this.

Step iteration: declaration order. **Validation at composition save time**: if any step references a `${step_X.path}` from a step that doesn't appear before it in the list, reject with 422. Topo-sort by depends_on is B-6 territory.

Parallel/branch/loop control flow → Phase B-6.

### #3 — Incremental serialization with hard size cap
**Decision**: persist after EVERY step. Step results stored inline in `state.step_results` (JSONB).

**Hard cap 1MB per step result, soft warn at 256KB**. Enforced in `_execute_step` after tool call, before save:

```python
result_bytes = len(json.dumps(result, default=str).encode("utf-8"))
if result_bytes > 1_048_576:
    raise StepFailed(step.step_id, "step_result_too_large",
                     details={"bytes": result_bytes, "limit": 1_048_576})
if result_bytes > 262_144:
    logger.warning(f"Large step result for {step.step_id}: {result_bytes} bytes")
```

No spillover table (Postgres TOAST handles internal compression up to ~1GB; we cap at 1MB to keep query perf reasonable). YAGNI for B-0.

### #4 — Cancel mid-flight
**Decision**: `cancel_requested` boolean column. Checked at every step boundary (entry of `_execute_step`).

In-flight tool calls run to completion. Each step has `default_timeout=60s` (already in current code) preventing infinite hang.

Opt-in `step.cancellable: bool` (default `false`) for hard-cancel via `asyncio.wait_for(..., timeout=cancel_check_interval=5s)`. Off by default for safety.

### #5 — Sub-composition durable (infrastructure only in B-0)
**Decision**: B-0 builds the COLUMNS (`parent_execution_id`, `state.depth`) and the propagation hook (when child reaches terminal, look up parent and trigger resume). **No `subcomposition` step type yet** — that arrives whenever a step type can suspend (B-1+).

Why: in B-0 the only suspending step type is `_test_suspend` (debug-only, never appears in real compositions). So the parent-side detection of "I just called a sub-composition that's now Pattern C suspended" has no real trigger in B-0. Building the column + propagation hook makes the infrastructure ready; the trigger lands later.

`MAX_SUBCOMPOSITION_DEPTH=5`. When a child execution is created (B-1+), set `child.state.depth = parent.state.depth + 1`. If `> MAX` → child created as `failed` with reason `"max_subcomposition_depth_exceeded"`.

Child's `parent_execution_id` → on child terminal transition, executor checks `WHERE parent_execution_id = ?` and:
- If parent.status == "suspended" AND parent.state.suspension.child_execution_id == this child:
  - Inject child result into `parent.state.step_results[parent.state.current_step_id]`
  - Trigger `executor.resume(parent.id, child_result)` (background)

**B-0 sub-composition is same-user only** (the executor doesn't impersonate). A child execution's `user_id` always matches its parent's. The child URI is always in the same user's scope.

Subscription propagation: when child fires `notifications/resources/updated`, recursively walk parent chain (`SELECT parent_execution_id`) and fire on each ancestor's URI too. Bounded by depth=5.

### #6 — Per-user resource scoping
**Decision**: every `resources/list`, `resources/read`, `resources/subscribe`, AND `composition_status` operation filters by `user_id == current_user.id`.

Implementation: in handlers for URI matching `composition://executions/{id}`:
```sql
SELECT * FROM composition_execution WHERE id = ? AND user_id = ?
```

If no match → empty list / 404 / `{"error": "execution_not_found"}` (no info leak about existence to other users).

Admin governance view (admin sees all org executions) is OUT OF SCOPE for B-0. If needed: separate URI scheme `composition://admin/org/{org_id}/executions` with admin role check, or via REST `GET /api/v1/compositions/{id}/executions`.

### #7 — Fallback for clients without `resources.subscribe`
**Decision**: at handshake, snapshot `client.capabilities` into `composition_execution.client_capabilities` JSONB. The routing logic adapts the response of `tools/call composition_X`.

- **Has `resources.subscribe`**: structured content `{execution_id, resource_uri, status}` — client subscribes
- **Without**: text content with explicit polling instructions + structured content pointing at `composition_status` meta-tool

The `composition_status` meta-tool (§7) is **public to all clients** — even subscribers can prefer one-shot polling.

### #8 — `notifications/resources/updated` payload
**Decision**: per spec, notification carries only the URI. Client must `resources/read` to fetch new content.

```json
{ "method": "notifications/resources/updated",
  "params": { "uri": "composition://executions/abc" } }
```

`pending_notification` queue stores `(session_id, uri, created_at)` — no payload. Saves DB and matches spec.

### #9 — Cross-user notifications (DEFERRED to B-1)
B-0 only handles same-user. Cross-user (for `approval` step type) requires `user_notification` table, banner, email opt-in — all B-1.

### #10 — Triggers unifiés (PARTIAL in B-0)
B-0: `trigger ENUM(mcp_call, manual, api)`. `cron` added in B-2, `webhook` in B-3. Enum extensible without migration.

### #11 — Quotas + queueing (always queue)
**Decision**: never reject on quota. Always accept; excess lands `status='queued'`; single in-process worker promotes FIFO as slots free.

- `MAX_CONCURRENT_EXECUTIONS_PER_USER=50` (env, configurable)
- Queue is the rows themselves
- Queue worker = single asyncio task started in lifespan
- The `tools/call` response is identical for queued vs running — just `status: "queued"` initially; client tracks transition via subscription/polling

Single-instance only (see §13).

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

Optional hint for compliance.

### #13 — Cost accounting `sample` (DEFERRED to B-5)
B-0 introduces no LLM calls. Accounting infra arrives with B-5.

### #14 — Pydantic ↔ runtime mismatch (hard fix, no aliasing)
**Decision**: fix `CompositionStep` Pydantic schema to match runtime. **Forward-compatible step types** — accept any string, validate at executor dispatch.

```python
class CompositionStep(BaseModel):
    step_id: str
    tool: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    type: str = Field(default="tool")          # any string; executor rejects unknown at dispatch
    optional: bool = False
    idempotent: bool = False                    # NEW for #1
    cancellable: bool = False                   # NEW for #4
    retry_strategy: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: Optional[int] = None
```

No dual-read aliases. Live data already canonical (`step_id`/`parameters` verified). The mismatch was an API-side bug; fail fast on legacy aliases with 422.

### #15 — `server_bindings` deprecation
**Decision**: deprecated. Field stays on `Composition` model (no migration), marked deprecated in docstring. Frontend stops sending. Executor doesn't read. Reactivate in B-1+ if a real `${binding.X}` use case emerges.

---

## 2. Schema

Three tables.

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

    trigger             VARCHAR(20) NOT NULL,  -- mcp_call | manual | api (cron/webhook B-2/B-3)
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

**FK semantics**:
- `composition_id ON DELETE RESTRICT` — can't drop composition with executions; use soft-delete (`Composition.deleted_at`) for compositions with history. Preserves audit trail.
- `user_id`, `organization_id ON DELETE CASCADE` — when user/org is hard-deleted, executions go too.
- `parent_execution_id ON DELETE SET NULL` — child survives parent deletion (becomes a root).

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
    uri             TEXT NOT NULL,
    method          VARCHAR(64) NOT NULL DEFAULT 'notifications/resources/updated',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pendnotif_session ON pending_notification(session_id, created_at);
```

Flushed at next `initialize` from that `session_id`. Cleanup: drop > 7 days old.

(Existing migrations use `gen_random_uuid()` which requires `pgcrypto` — already enabled in our DB. No additional setup needed.)

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
                              ↓ no                    │ worker picks up
                       status = running ←─────────────┘ (UPDATE WHERE
                              |                          status='queued')
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
                                              |   1. check cancel_requested
                                              |   2. mark step in_progress + persist
                                              |   3. invoke tool / handle suspend
                                              |   4. mark succeeded + persist)
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
                                       (UPDATE WHERE status='suspended')
                                              |
                                              v
                                       continues until done

Backend restart sweep (lifespan startup):
  UPDATE composition_execution
  SET status = 'failed', error = 'backend_restart_orphan', updated_at = NOW()
  WHERE status = 'running'
  RETURNING id;
  -- Suspended and queued are untouched.
  -- Suspended will resume on event; queued will be picked up by worker tick.
```

Terminal statuses: `completed | failed | expired | cancelled`. Each emits one final `notifications/resources/updated`.

---

## 4. Executor refactor

Singleton `ResumableExecutor`. State lives in DB. Methods stateless wrt instance.

### 4.1 Concurrency model — status-as-lock + conditional UPDATE

**No advisory locks.** Postgres MVCC + conditional UPDATE-RETURNING is sufficient and simpler.

Pattern:
- **Cancel** = `UPDATE ... SET cancel_requested=true WHERE id=:id` (no status check; cancel always allowed)
- **Resume** = `UPDATE ... SET status='running' WHERE id=:id AND status='suspended' RETURNING *`
  - If 0 rows → reject with `409 Conflict` (someone else got there first OR not suspended)
  - First caller wins; subsequent calls fail fast
- **Promote from queue** = `UPDATE ... SET status='running' WHERE id=:id AND status='queued' RETURNING *`
  - Same pattern. Worker won't double-promote even if its tick retries.
- **Run loop** = once status is `running`, the detached task is the single writer. No other task touches `state` until the loop hits a terminal/suspended transition.

This eliminates the entire advisory-lock complexity while still preventing all the race conditions identified in review.

### 4.2 Pseudo-code

```python
@dataclass
class Suspend:
    reason: Literal["subcomposition", "_test_suspend"]  # B-0; B-1+ adds others
    payload: dict
    ttl_seconds: int

class StepResultTooLarge(Exception):
    pass

class ResumableExecutor:
    """Singleton. Stateless wrt instance. State in DB."""

    async def run(self, execution_id: UUID) -> str:
        """Run from current state until terminal/suspended.
        Returns final status."""
        async with async_session_maker() as db:
            execution = await self._load(db, execution_id)
            if execution.status not in ("running", "queued"):
                return execution.status  # nothing to do

            if execution.status == "queued":
                # Atomic transition queued → running
                rows = await db.execute(text("""
                    UPDATE composition_execution
                    SET status='running', updated_at=NOW()
                    WHERE id=:id AND status='queued'
                    RETURNING id
                """), {"id": str(execution_id)})
                await db.commit()
                if rows.scalar_one_or_none() is None:
                    return "queued"  # someone else promoted

            state = ExecutionState.from_jsonb(execution.state)
            return await self._run_loop(db, execution, state)

    async def resume(self, execution_id: UUID, response: Any) -> str:
        """Inject response into the suspended step and continue."""
        async with async_session_maker() as db:
            # Atomic transition suspended → running with response injection
            rows = await db.execute(text("""
                UPDATE composition_execution
                SET status='running',
                    state = jsonb_set(
                        jsonb_set(state, '{step_results,' || (state->>'current_step_id') || '}',
                                  :response::jsonb),
                        '{suspension}',
                        'null'::jsonb
                    ),
                    updated_at=NOW()
                WHERE id=:id AND status='suspended'
                RETURNING *
            """), {"id": str(execution_id),
                   "response": json.dumps(response, default=str)})
            row = rows.first()
            await db.commit()
            if row is None:
                raise BadRequest("execution not in suspended state")

            execution = await self._load(db, execution_id)
            state = ExecutionState.from_jsonb(execution.state)
            return await self._run_loop(db, execution, state)

    async def _run_loop(self, db, execution, state) -> str:
        try:
            while True:
                # Cancel boundary check
                cancelled = await db.execute(text(
                    "SELECT cancel_requested FROM composition_execution WHERE id=:id"
                ), {"id": str(execution.id)})
                if cancelled.scalar() is True:
                    return await self._mark_terminal(db, execution, "cancelled")

                step = self._next_step(state, execution.composition.steps)
                if step is None:
                    return await self._mark_terminal(
                        db, execution, "completed",
                        result=self._extract_result(state),
                    )

                outcome = await self._execute_step(step, state, execution, db)

                if isinstance(outcome, Suspend):
                    return await self._mark_suspended(db, execution, state, outcome)

                state.step_results[step.step_id] = outcome
                state.step_status[step.step_id] = "succeeded"
                state.current_step_id = None
                await self._save(db, execution, state)
        except StepResultTooLarge as e:
            logger.warning(f"Step result too large for {execution.id}: {e}")
            return await self._mark_terminal(db, execution, "failed", error=str(e))
        except Exception as e:
            logger.exception(f"Execution {execution.id} failed unexpectedly")
            return await self._mark_terminal(db, execution, "failed", error=str(e))

    async def _execute_step(self, step, state, execution, db) -> Any | Suspend:
        # Idempotence guard (#1 — author-controlled)
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

        # Dispatch by step type
        try:
            if step.type == "tool":
                if step.cancellable:
                    result = await asyncio.wait_for(
                        self._call_tool(step, state, execution),
                        timeout=step.timeout_seconds or self.default_timeout
                    )
                else:
                    result = await self._call_tool(step, state, execution)
            elif step.type == "_test_suspend":  # B-0 only, debug
                return Suspend(reason="_test_suspend", payload={}, ttl_seconds=300)
            else:
                # B-1+ types not implemented yet → fail explicitly
                raise NotImplementedError(
                    f"Step type {step.type!r} not implemented in this version. "
                    f"Available: tool, _test_suspend."
                )

            # Size enforcement (#3)
            result_bytes = len(json.dumps(result, default=str).encode("utf-8"))
            if result_bytes > 1_048_576:
                raise StepResultTooLarge(
                    f"Step {step.step_id} returned {result_bytes} bytes (max 1MB)"
                )
            if result_bytes > 262_144:
                logger.warning(
                    f"Large step result for {step.step_id}: {result_bytes} bytes"
                )
            return result

        except Exception:
            state.step_status[step.step_id] = "failed"
            await self._save(db, execution, state)
            raise

    @staticmethod
    async def run_detached(execution_id: UUID) -> None:
        """Wrapper for asyncio.create_task. Handles fire-and-forget exceptions."""
        try:
            executor = get_executor()
            await executor.run(execution_id)
        except Exception:
            logger.exception(f"Detached execution {execution_id} crashed")
            # Belt-and-suspenders: mark failed if not already terminal
            try:
                async with async_session_maker() as db:
                    await db.execute(text("""
                        UPDATE composition_execution
                        SET status='failed', error='detached_crash', updated_at=NOW()
                        WHERE id=:id AND status IN ('running', 'queued')
                    """), {"id": str(execution_id)})
                    await db.commit()
            except Exception:
                logger.exception("Could not mark crashed execution as failed")
```

### 4.3 Orphan recovery on backend restart

In `app/main.py:_startup_impl`, after DB init, before serving:

```python
async with async_session_maker() as db:
    result = await db.execute(text(
        "UPDATE composition_execution SET "
        "status='failed', error='backend_restart_orphan', updated_at=NOW() "
        "WHERE status='running' "
        "RETURNING id"
    ))
    orphans = list(result.scalars().all())
    await db.commit()
    if orphans:
        logger.warning(f"Marked {len(orphans)} orphan executions as failed")
```

`suspended` and `queued` are untouched. Suspended resumes on external event; queued is picked up by the worker on next tick.

### 4.4 Background queue worker

Singleton task started in lifespan startup. Guarded against double-start.

```python
_queue_worker_task: asyncio.Task | None = None

async def start_queue_worker():
    global _queue_worker_task
    if _queue_worker_task and not _queue_worker_task.done():
        return  # already running
    _queue_worker_task = asyncio.create_task(_queue_promotion_loop())

async def _queue_promotion_loop():
    while True:
        try:
            promoted = await _promote_queued_batch()
            for execution_id in promoted:
                asyncio.create_task(ResumableExecutor.run_detached(execution_id))
        except Exception:
            logger.exception("Queue promotion loop iteration failed")
        await asyncio.sleep(QUEUE_TICK_SECONDS)  # default 5

async def _promote_queued_batch() -> list[UUID]:
    """One pass: count running per user, promote queued FIFO up to per-user limit."""
    async with async_session_maker() as db:
        running = await db.execute(text("""
            SELECT user_id, COUNT(*) FROM composition_execution
            WHERE status='running' GROUP BY user_id
        """))
        per_user = {r[0]: r[1] for r in running.all()}

        queued = await db.execute(text("""
            SELECT id, user_id FROM composition_execution
            WHERE status='queued'
            ORDER BY started_at ASC
            LIMIT 200
        """))
        rows = queued.all()

        to_promote = []
        for execution_id, user_id in rows:
            cur = per_user.get(user_id, 0)
            if cur < MAX_CONCURRENT_PER_USER:
                # Conditional UPDATE — only one worker can promote
                upd = await db.execute(text("""
                    UPDATE composition_execution
                    SET status='running', updated_at=NOW()
                    WHERE id=:id AND status='queued'
                    RETURNING id
                """), {"id": str(execution_id)})
                if upd.scalar_one_or_none() is not None:
                    to_promote.append(execution_id)
                    per_user[user_id] = cur + 1

        await db.commit()
        return to_promote
```

Single-instance assumption (#13 disclaimer). For multi-instance, the conditional UPDATE pattern still works (one worker wins per row), but pinning the workers is simpler.

---

## 5. Routing in `tools/call composition_X`

Static analysis decides Pattern A/B/C at call time. No flag needed (though `extra_metadata.requires_async: true` can force C).

```python
async def call_tool_composition(name: str, arguments: dict, ctx) -> dict:
    composition = await load_composition_by_tool_name(name, ctx.user_id)

    suspending = any(
        s.get("type") in {"_test_suspend"}  # B-1+: elicit, wait_callback, etc.
        for s in composition.steps
    )
    forced_async = composition.extra_metadata.get("requires_async") is True
    cron_triggered = ctx.trigger == "cron"
    use_pattern_c = suspending or forced_async or cron_triggered

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
        executor = get_executor()
        await executor.run(execution.id)
        execution = await reload(execution.id)
        if execution.status == "completed":
            return wrap_as_mcp_tool_result(execution.result)
        return wrap_as_mcp_error(execution.error)

    # Pattern C: detached background
    asyncio.create_task(ResumableExecutor.run_detached(execution.id))

    if ctx.client_capabilities.get("resources", {}).get("subscribe"):
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"Composition started (id={execution.id}). "
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

**Default filter**: only non-terminal statuses (`running`, `suspended`, `queued`). Completed/failed/expired/cancelled are accessible via `resources/read` (and listed in UI/REST), but pollute `resources/list` if all returned.

**Pagination**: `cursor` param per spec. Page size 50. Cursor = base64-encoded `(updated_at, id)` tuple.

### 6.2 `resources/read`
For URI `composition://executions/{id}`:
1. Parse UUID; reject malformed
2. Query `WHERE id = ? AND user_id = current_user.id`
3. If no row → return empty list / 404 (no info leak)
4. Return:
```json
{
  "uri": "composition://executions/abc",
  "mimeType": "application/json",
  "text": "<json string of payload below>"
}
```

Payload shape:
```json
{
  "execution_id": "abc",
  "status": "suspended",
  "current_step_id": "3",
  "step_results": {...},
  "step_status": {...},
  "suspension": {
    "type": "subcomposition",
    "child_uri": "composition://executions/def"
  },
  "started_at": "...",
  "updated_at": "...",
  "expires_at": "...",
  "result": null,
  "error": null
}
```

For `suspended` with `subcomposition`: `child_uri` is always in the same user's scope (B-0 sub-compo doesn't impersonate).

### 6.3 `resources/subscribe` and `resources/unsubscribe`
Track `(session_id, uri)` pairs in-memory `Dict[str, Set[str]]`.

On state transition of a subscribed execution:
1. If session is connected → push `notifications/resources/updated` immediately
2. Else → `INSERT INTO pending_notification`

**Sub-composition propagation** (#5/7): when child fires, walk parent chain via `SELECT parent_execution_id` (max 5 hops) and fire on each ancestor's URI too.

### 6.4 Notification flush on `initialize`
When a session sends `initialize`:
1. `SELECT uri FROM pending_notification WHERE session_id = ? ORDER BY created_at`
2. Push each as `notifications/resources/updated` after the initialize response
3. `DELETE` the rows

---

## 7. The `composition_status` meta-tool

Added to `pool/definitions.py` alongside `search`, `execute`, `describe_tool`. **Public to all clients**, **per-user scoped** internally.

Returns SUMMARY only (status, current step, suspension reason, error, dates) — not full step results. Full state via `resources/read` or REST endpoint.

```python
{
    "name": "composition_status",
    "title": "Check status of a composition execution",
    "description": (
        "Return summary status of a composition execution. Returns status, "
        "current step, error if any. For full step results, read the resource "
        "composition://executions/{id} or fetch GET /api/v1/compositions/executions/{id}."
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
                "enum": ["queued","running","suspended","completed","failed","expired","cancelled","not_found"]
            },
            "current_step_id": {"type": ["string","null"]},
            "suspension_reason": {"type": ["string","null"]},
            "error": {"type": ["string","null"]},
            "expires_at": {"type": ["string","null"]},
            "started_at": {"type": ["string","null"]},
            "updated_at": {"type": ["string","null"]},
            "result_uri": {
                "type": ["string","null"],
                "description": "When completed, points to the full result resource"
            }
        },
        "required": ["execution_id", "status"]
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

Handler: per-user scoping enforced.
```python
async def handle_composition_status(arguments, user_id, organization_id):
    execution_id = arguments.get("execution_id")
    async with async_session_maker() as db:
        row = await db.execute(text("""
            SELECT id, status, state->>'current_step_id' AS current_step_id,
                   state->'suspension'->>'reason' AS suspension_reason,
                   error, expires_at, started_at, updated_at
            FROM composition_execution
            WHERE id = :id AND user_id = :uid
        """), {"id": execution_id, "uid": user_id})
        r = row.first()
    if r is None:
        return {"execution_id": execution_id, "status": "not_found"}
    return {
        "execution_id": str(r.id),
        "status": r.status,
        "current_step_id": r.current_step_id,
        "suspension_reason": r.suspension_reason,
        "error": r.error,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "started_at": r.started_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "result_uri": (
            f"composition://executions/{r.id}" if r.status == "completed" else None
        ),
    }
```

---

## 8. Endpoints

```
GET    /api/v1/compositions/executions
       Query: ?status=running,suspended  ?limit=50  ?offset=0  ?include_terminal=false
       Returns: list of execution summaries for current user

GET    /api/v1/compositions/executions/{id}
       Auth: JWT user MUST own the execution
       Returns: full detail (state, recent events, result/error)

POST   /api/v1/compositions/executions/{id}/cancel
       Auth: JWT user MUST own the execution
       Sets cancel_requested=true via UPDATE
       Returns: 202 Accepted (cancel will land at next step boundary)

POST   /api/v1/compositions/executions/{id}/resume
       Auth: B-0 ONLY accepts JWT user owner.
       (B-3 will add HMAC webhook token alternative on the SAME endpoint
        via Authorization scheme branching.)
       Body shape (B-0, free-form for _test_suspend):
         { "response": <any-json> }
       Returns:
         200 with new status if accepted
         409 Conflict if execution not in suspended state

GET    /api/v1/compositions/{composition_id}/executions
       Auth: JWT user MUST be ADMIN/OWNER of the composition's org
       Admin governance view: all executions of a composition (audit)
```

---

## 9. UI

### Page `/app/compositions/executions`
- List per user, default filter `status IN (running, suspended, queued)`
- Toggle "show terminal" extends to completed/failed/etc.
- Columns: composition name, status badge, started_at, last_update, current step, actions (cancel | view)
- Auto-refresh polling every 5s for non-terminal statuses (B-0 ships polling; SSE polish later)

### Page `/app/compositions/executions/{id}`
- Header: composition name + status + cancel button (if running/suspended)
- Timeline of `execution_step_event` rows
- Current step highlighted if running/suspended
- For `suspended` with `_test_suspend`: button "Provide test response" → POST `/resume`
- Final result (if completed) or error (if failed) at bottom

### Banner global (in MainLayout)
- Counts `suspended` executions for current user (cheap query each page load)
- Click → executions page filtered by suspended

---

## 10. Tests (14 must-pass before merge)

```python
# tests/test_composition_executions_b0.py

# Core lifecycle (4)
async def test_sync_composition_unchanged():
    """Pattern A: existing sync compo runs end-to-end identically (regression)."""

async def test_test_suspend_round_trip():
    """B-0 mechanism: _test_suspend yields, manual resume continues."""

async def test_pattern_c_resource_flow():
    """tools/call → immediate return + subscribe + notif on complete."""

async def test_capability_negotiation_no_subscribe():
    """Client without resources.subscribe gets text fallback + polling tool hint."""

# Safety / robustness (5)
async def test_idempotence_after_crash_default_safe():
    """Step in_progress on resume + step.idempotent=false → fails with reason, not re-fire."""

async def test_idempotence_after_crash_marked_idempotent():
    """Step in_progress on resume + step.idempotent=true → re-runs cleanly."""

async def test_orphan_recovery_on_restart():
    """Running execution + simulated restart → marked failed (backend_restart_orphan)."""

async def test_concurrent_resume_only_one_succeeds():
    """Two parallel resumes → first wins (status update), second gets 409."""

async def test_cancel_during_running():
    """Cancel mid-flight → in-flight step finishes, execution marked cancelled."""

# Sub-composition infra (2)
async def test_subcomposition_propagation():
    """Direct DB setup: parent suspended pointing at child;
       transition child → parent automatically resumes."""

async def test_subcomposition_depth_limit():
    """Direct DB setup: parent.state.depth=5; create child → child fails pre-flight."""

# Quotas (1)
async def test_quota_promotes_via_queue():
    """User with 50 running + new request → queued, promoted as slot frees."""

# Resource isolation + notifications (2)
async def test_per_user_resource_isolation():
    """User A cannot read composition://executions/{id_of_user_B} (404)."""

async def test_pending_notification_flush_on_reconnect():
    """Disconnected session, state changes, reconnect → notif replayed once, then deleted."""
```

Each test runs in isolation, uses SQLite in-memory + asyncio task fixtures + time mock for time-sensitive tests.

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

Emitted from `_mark_terminal`, `_mark_suspended`, `resume`, queue promotion, cancel endpoint. All carry `resource_type='composition_execution'`, `resource_id=<execution_id>`.

---

## 13. Multi-instance disclaimer

**B-0 assumes single backend instance.** All in-memory structures (subscription map, queue worker) live in one process.

The status-as-lock pattern (#4.1) is multi-instance-safe by design — multiple workers can race on `UPDATE WHERE status=...`, only one succeeds. So the heaviest path already scales. Remaining work for multi-instance:
- Replace in-memory subscription map with Redis pub/sub
- Pin MCP SSE sessions to one instance (sticky sessions in nginx) OR fan out notifications cross-instance
- Postgres advisory locks already work cross-instance (per-database scope)

When prod scales beyond one backend, this becomes an explicit phase. Not in B-0 scope.

---

## 14. Decisions (post-review, no longer "open questions")

1. `composition_status` is **public to all clients**, internally **per-user scoped**.
2. **TTL per Suspend payload** — set by the step type that suspends (`_test_suspend`=300s in B-0).
3. Subscriptions on **completed executions** fire one final notification on transition, then no further events (read-only-stable).
4. UI auto-refresh = **polling 5s in B-0**. SSE upgrade is polish, future phase.
5. **No spillover table** for large step results. 1MB hard cap with explicit StepResultTooLarge, 256KB soft warn, inline JSONB.
6. **No dual-read Pydantic** aliases. Hard fix the schema, fail fast on legacy `id`/`params`.
7. **B-0 is sequential only**. Parallel = B-6.
8. **Single-instance assumption** explicit (#16 review).
9. **Idempotence is author-controlled**, never tool-claimed.
10. **Always queue**, never reject on quota.
11. **No advisory locks** — status-as-lock + conditional UPDATE-RETURNING pattern.
12. **Sub-composition infra in B-0** (column + propagation hook), no `subcomposition` step type yet — first step type that can suspend triggers it (B-1+).
13. **Step type validation = late-bound**. Accept any string in Pydantic, reject unknown at executor dispatch with explicit error.

---

## 15. Out of scope for B-0

- All step types beyond `tool` and `_test_suspend` → B-1 to B-5
- Cron triggers → B-2
- Cross-user notifications (`user_notification` table) → B-1
- LLM cost accounting → B-5
- Branch / parallel / loop control flow → B-6
- `${binding.X}` resolver → only if needed in B-1+
- Email out-of-band notifications → optional in B-2
- Multi-instance backend deployment → future phase
- Admin governance resource scheme → future phase
- SSE-pushed UI updates → polish

---

## 16. Estimation (post second review)

| Sub-task | Days |
|---|---|
| Migration + 3 tables + indexes + FKs | 2 |
| Models (SQLAlchemy) + Pydantic schemas + audit actions | 1 |
| Executor refactor (state machine, persistence, idempotence, status-as-lock) | 4 |
| Sub-composition column + propagation hook (no step type yet) | 1 |
| Background queue worker + orphan recovery on startup | 1 |
| Pattern routing (A/B/C) in `call_tool_composition` | 1 |
| MCP resource handler (list + read + subscribe + scope + propagation) | 2 |
| `composition_status` meta-tool + pool/definitions wiring + per-user check | 1 |
| Pending notification queue + flush on reconnect | 1 |
| REST endpoints (list/get/cancel/resume) + auth | 1 |
| UI page list + detail + banner | 3 |
| Tests E2E (14 must-pass) | 4 |
| Pydantic mismatch fix (#14) + `server_bindings` deprecation (#15) | 1 |
| Buffer for surprises | 2 |

**Total: ~25 days realistic**, ~20 days minimum.

(-1 vs previous estimate: dropping advisory locks simplified the executor refactor.)

---

## 17. Review iterations (traceability)

### Round 1 — initial review (20 points)
Mapping in §17 of previous version (now superseded by Round 2 below). Critical fixes integrated: idempotence author-controlled, sequential B-0, orphan recovery, advisory locks (later replaced), parent-child subscription propagation, ON DELETE RESTRICT, always queue, summary-only `composition_status`, `resources/list` filtering, JWT-only `/resume` in B-0, closed open questions, audit events enumerated, multi-instance disclaimer, executor singleton clarified, tests 8→14, no spillover table, no dual-read Pydantic.

### Round 2 — second review (15 refinements)
1. **§1#1** — added edge-case footnote (false-negative on partial persist is acceptable)
2. **§1#3** — explicit 1MB enforcement code in `_execute_step` + StepResultTooLarge exception
3. **§1#5** — clarified B-0 builds infra only, sub-composition step type comes later
4. **§1#11** — simpler queue worker (Python iteration with conditional UPDATE per row)
5. **§1#14** — `step.type` is `str` not `Literal`; unknown types rejected at dispatch
6. **§4.1** — dropped advisory locks; status-as-lock + conditional UPDATE-RETURNING is sufficient and simpler
7. **§4.2** — simplified pseudo-code (no lock helper); `resume()` does atomic state injection via `jsonb_set` in single UPDATE
8. **§4.4** — Python iteration queue worker (clearer than complex SQL CTE)
9. **§5** — dropped `__wrapped__` hack; routing uses normal `executor.run` for sync path
10. **§6.2** — explicit note that sub-compo child URI is same-user always
11. **§7** — explicit per-user scope check + handler implementation shown
12. **§8** — `/resume` body schema specified for B-0 (`{response: any}` for `_test_suspend`)
13. **§10** — renamed `test_advisory_lock` → `test_concurrent_resume_only_one_succeeds`
14. **§14** — added 3 new decisions (status-as-lock, sub-compo infra-only, late-bound type validation)
15. **§16** — estimate down 1 day (no advisory lock complexity)

Each design change traced. Doc is internally consistent and ready for code.
