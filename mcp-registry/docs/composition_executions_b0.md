# Phase B-0 — Composition executions: design doc

**Status**: draft for review
**Prereq**: read [`project_plan_compositions_workflow_engine.md`](../../../.claude/projects/-opt-bigmcp/memory/project_plan_compositions_workflow_engine.md) (memo) for the architectural thesis. This doc operationalizes B-0.

---

## 0. Scope

Build the durable suspension infrastructure that turns compositions from synchronous DAG runs into resumable state machines. Expose them to MCP clients via standard primitives (`tools`, `resources/subscribe`, `notifications/resources/updated`) — no proprietary protocol.

**In scope**:
1. New table `composition_execution` (Postgres, durable)
2. Refactor `app/orchestration/composition_executor.py` to be yield-able + resumable
3. Three execution patterns (A sync / B progress / C detached) auto-routed
4. MCP resource `composition://executions/{id}` (read + subscribe)
5. Pending notification queue per MCP session for replay-on-reconnect
6. Endpoints + UI page to manage executions
7. Address the 15 invariants below

**Out of scope** (delegated to B-1+):
- Step types `elicit`, `wait_callback`, `wait_until`, `sample`, `approval`
- Cron triggers
- Cross-user notifications (needed by `approval` in B-1)

A `_test_suspend` step type is added in B-0 ONLY to validate the suspension mechanism (gated behind a debug flag, not exposed publicly).

---

## 1. The 15 invariants — concrete decisions

### #1 — Idempotence on resume
**Decision**: `state.step_status[step_id] = "in_progress" | "succeeded" | "failed"` persisted before AND after each step.

```python
# Before tool call
state.step_status[step_id] = "in_progress"
state.step_started_at[step_id] = now()
await persist_state(execution_id, state)

# Call upstream
try:
    result = await invoke_tool(...)
except Exception as e:
    state.step_status[step_id] = "failed"
    state.step_results[step_id] = {"error": str(e)}
    await persist_state(execution_id, state)
    raise

# After
state.step_status[step_id] = "succeeded"
state.step_results[step_id] = result
await persist_state(execution_id, state)
```

On resume, if `step_status[step_id] == "in_progress"`:
- If tool annotation says `idempotentHint=true` → re-run safely
- Else → mark step `failed` with reason `"resumed_after_crash_non_idempotent"` and apply fallback (skip if `optional=true`, else fail composition)

This is conservative on purpose: a `send_email` re-firing is worse than an explicit composition failure the user can rerun manually.

### #2 — Parallel steps + suspension
**Decision**: when ANY parallel sibling suspends, executor waits for ALL siblings currently in-flight to finish (no cancel mid-call), then persists state and yields `Suspend`. Resume picks back up where the slowest sibling left off.

**Why**: cancelling in-flight HTTP calls leaves orphan side-effects upstream we can't undo. Cleaner to let them finish.

Trade-off: a slow sibling delays the suspension by its own latency. Acceptable — suspending compositions are not latency-sensitive by definition.

### #3 — Incremental state serialization
**Decision**: persist after EVERY step (not just at suspension). Enables crash recovery anywhere.

Postgres row size: `state` JSONB will grow with `step_results`. Cap each step result at 256KB (configurable `MAX_STEP_RESULT_BYTES`). Step results above the cap are stored in a separate table `execution_step_payload(execution_id, step_id, payload, created_at)` and the `state.step_results[step_id]` becomes a pointer `{"$ref": "<step_payload_id>"}`.

The 256KB cap covers 99% of tool outputs. The pointer pattern keeps the hot row small for queries.

### #4 — Cancel mid-flight
**Decision**: `cancel_requested` flag on the row, checked at every step boundary.

```python
async def run(execution_id):
    while not done:
        if check_cancel(execution_id):
            mark_cancelled()
            return Cancelled()
        step = next_step(state)
        result = await execute_step(step)  # in-flight call NOT interrupted
        ...
```

In-flight tool calls run to completion (their effects are committed upstream anyway). The execution becomes `cancelled` at the next boundary.

For users who want hard-cancel (e.g. abort an LLM token stream), `step.cancellable=true` opt-in allows the executor to use `asyncio.wait_for(...)` with cancellation. Default `false` for safety.

### #5 — Sub-composition durable
**Decision**: `parent_execution_id` on `composition_execution` + bidirectional resume chain.

```
parent execution suspended on step "call_child":
  state.suspension = {
    "type": "subcomposition",
    "child_execution_id": "abc"
  }

child execution suspended on step "elicit":
  state.suspension = {
    "type": "elicit",
    "elicit_payload": {...}
  }
  parent_execution_id = "<parent_id>"

When child completes/fails:
  → update child row
  → fetch parent_execution_id
  → if parent.status == "suspended" and parent.state.suspension.child_execution_id == this child:
       trigger run(parent) which picks up child result and continues
```

Resource subscription propagates: subscribers of the parent get notified when child changes too (server-side fanout).

Recursion: enforced max nesting via `state.depth` (default 5). On exceed → `failed` with reason `"max_subcomposition_depth_exceeded"`.

### #6 — Per-user resource scoping
**Decision**: every `resources/list`, `resources/read`, `resources/subscribe` call goes through an authorization check that filters by `user_id == current_user.id` for the `composition://executions/*` URI scheme.

Implementation: in `mcp_unified.py:list_resources` and `read_resource`, when the URI matches `composition://executions/{id}`, query `composition_execution WHERE id = ? AND user_id = ?`. If no match → return empty list / 404 (no information leak about existence to other users).

### #7 — Fallback for clients without `resources.subscribe`
**Decision**: when starting a Pattern C execution from `tools/call`, check `client.capabilities.resources.subscribe`:
- **Supported**: return structured content `{execution_id, resource_uri, status: "running"}`
- **Not supported**: return text content `"Composition started. Status: https://bigmcp.cloud/app/compositions/executions/{id}\nID: {execution_id}"` — user can paste this into a follow-up `tools/call composition_status({id})` (a public meta-tool we expose for this)

Add new pool meta-tool `composition_status(execution_id)` that any agent can call to poll status. Returns the same payload as `resources/read composition://executions/{id}`. This is the polling fallback for clients without subscribe support.

### #8 — `notifications/resources/updated` payload
**Decision**: per spec, the notification carries only the URI:
```json
{ "method": "notifications/resources/updated",
  "params": { "uri": "composition://executions/abc" } }
```

The pending notification queue stores `(session_id, uri, created_at)` tuples — no payload. Client must call `resources/read` to fetch the new content. Saves DB storage and matches spec literally.

### #9 — Cross-user notifications (DEFERRED to B-1)
B-0 only handles same-user notifications (the user who triggered the execution = the user who gets notified). B-1 introduces:
- Table `user_notification(id, recipient_user_id, type, title, body, action_url, read_at, created_at)`
- API `GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read`
- Banner UI BigMCP global
- Email opt-in via `user.preferences.email_notifications`

This is needed for `approval` step type in B-1.

### #10 — Triggers unifiés (PARTIAL in B-0)
B-0 implements `trigger ENUM(mcp_call, manual, api)` on the row. B-2 adds `cron` and B-3 adds `webhook`. The enum is extensible; no schema migration needed when adding new trigger types.

Table `composition_trigger(composition_id, type, config jsonb, enabled)` is added in B-2 (cron) since it's where it earns its keep.

### #11 — Quotas + queueing
**Decision** for B-0:
- Hard limit `MAX_CONCURRENT_EXECUTIONS_PER_USER=50` (env, configurable)
- New status `queued` for executions blocked by quota
- FIFO consume by background worker (released when an `running` becomes terminal)
- 429 response from `tools/call` if user already has 50 concurrent + a hint about queuing

For B-2 cron specifically: `composition_schedule.max_concurrent` per schedule (default 1, prevents overlap of weekly reports etc.).

### #12 — Capability declaration audit
**Already declared correctly** (`mcp_unified.py:485-496`):
- `tools.listChanged: true` ✅
- `resources.subscribe: true` ✅
- `resources.listChanged: true` ✅
- `prompts.listChanged: false`

**To add in B-0**:
```json
"experimental": {
  "compositions": {
    "version": "1.0",
    "asyncExecution": true,
    "resourceScheme": "composition://executions/{id}"
  }
}
```

Hint informatif. Optional for compliance.

### #13 — Cost accounting `sample` (DEFERRED to B-5)
B-0 doesn't introduce LLM calls. Accounting infrastructure (`llm_usage` table, opt-in flag) lands with B-5.

### #14 — Pydantic ↔ runtime mismatch
**Decision**: fix `CompositionStep` Pydantic schema to match runtime conventions, BUT keep dual-read for backward compat.

```python
class CompositionStep(BaseModel):
    # Runtime canonical names
    step_id: str = Field(..., alias="id")  # accept both, serialize as step_id
    tool: str
    parameters: Dict[str, Any] = Field(default_factory=dict, alias="params")
    depends_on: List[str] = Field(default_factory=list)
    type: str = Field(default="tool")
    optional: bool = False
    retry_strategy: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: Optional[int] = None
    cancellable: bool = False  # NEW for #4

    model_config = ConfigDict(populate_by_name=True)
```

Existing rows with `id`/`params` keep loading via aliases. New writes use canonical `step_id`/`parameters`. After 1-2 weeks observability, decide whether to migrate old rows.

### #15 — `server_bindings` decision
**Decision**: deprecate cleanly. The field stays on the model (no migration), but:
- Marked deprecated in the docstring
- Frontend stops sending it on POST/PUT
- Executor no longer reads it (was already unused)
- Add `${binding.X}` resolver in B-1 only IF a real use case emerges

Rationale: nothing in production uses it (verified empty in all live compositions). Carrying dead infra adds to confusion. Reactivating in a future phase is cheap (it's just JSON).

---

## 2. Schema

### 2.1 `composition_execution`

```sql
CREATE TABLE composition_execution (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_id      UUID NOT NULL REFERENCES compositions(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    parent_execution_id UUID REFERENCES composition_execution(id) ON DELETE SET NULL,

    status              VARCHAR(20) NOT NULL,  -- queued|running|suspended|completed|failed|expired|cancelled
    state               JSONB NOT NULL DEFAULT '{}'::jsonb,
                        -- { step_results: {...}, step_status: {...}, current_step_id, suspension, depth }

    trigger             VARCHAR(20) NOT NULL,  -- mcp_call|manual|api|cron|webhook (extensible)
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
```

### 2.2 `execution_step_event` (timeline)

```sql
CREATE TABLE execution_step_event (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL REFERENCES composition_execution(id) ON DELETE CASCADE,
    step_id         VARCHAR(64) NOT NULL,
    event_type      VARCHAR(32) NOT NULL,  -- started|succeeded|failed|suspended|skipped|retry
    payload         JSONB,                 -- duration_ms, error, retry_count, ...
    timestamp       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stepev_exec_time ON execution_step_event(execution_id, timestamp);
```

Cleanup job: drop events older than 90 days.

### 2.3 `execution_step_payload` (large step results, optional)

```sql
CREATE TABLE execution_step_payload (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL REFERENCES composition_execution(id) ON DELETE CASCADE,
    step_id         VARCHAR(64) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
```

Used only when a step result exceeds `MAX_STEP_RESULT_BYTES`. The `composition_execution.state.step_results[step_id]` becomes `{"$ref": "<payload_id>"}`.

### 2.4 `pending_notification`

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
                       status = queued
                              |
                              v
              quota check → no → wait in queue
                              ↓ yes
                       status = running
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
                                  ┌───────────┼────────────┐
                                  v           v            v
                              completed   suspended again   failed
```

Terminal statuses: `completed | failed | expired | cancelled`. Each emits `notifications/resources/updated`.

---

## 4. Executor refactor

Current `composition_executor.py` is a sync loop. Refactor to:

```python
class ExecutionState:
    """In-memory mirror of state JSONB, with helpers."""
    step_results: dict[str, Any]
    step_status: dict[str, Literal["pending","in_progress","succeeded","failed"]]
    current_step_id: str | None
    suspension: dict | None  # {type, payload, ttl_seconds}
    depth: int               # subcomposition nesting

class StepOutcome:
    """Either a result or a Suspend signal."""

@dataclass
class Suspend:
    reason: Literal["elicit", "wait_callback", "wait_until", "subcomposition", "_test_suspend"]
    payload: dict
    ttl_seconds: int

class ResumableExecutor:
    async def run(self, execution_id: UUID) -> Literal["completed","suspended","failed","cancelled"]:
        execution = await self._load(execution_id)
        state = ExecutionState.from_jsonb(execution.state)

        try:
            while True:
                if execution.cancel_requested:
                    return await self._mark_cancelled(execution_id)

                step = self._next_step(state, execution.composition.steps)
                if step is None:
                    return await self._mark_completed(execution_id, state)

                outcome = await self._execute_step(step, state, execution)

                if isinstance(outcome, Suspend):
                    return await self._mark_suspended(execution_id, state, outcome)

                state.step_results[step.step_id] = outcome
                state.step_status[step.step_id] = "succeeded"
                await self._persist(execution_id, state)

        except Exception as e:
            return await self._mark_failed(execution_id, state, e)

    async def resume(self, execution_id: UUID, response: Any) -> str:
        execution = await self._load(execution_id)
        if execution.status != "suspended":
            raise BadRequest("not suspended")
        state = ExecutionState.from_jsonb(execution.state)
        # Inject the response into the step that suspended
        state.step_results[state.current_step_id] = response
        state.step_status[state.current_step_id] = "succeeded"
        state.suspension = None
        execution.status = "running"
        await self._persist(execution_id, state)
        return await self.run(execution_id)

    async def _execute_step(self, step, state, execution) -> Any | Suspend:
        # Idempotence guard (#1)
        prior_status = state.step_status.get(step.step_id)
        if prior_status == "in_progress":
            return await self._handle_in_progress(step, execution)
        if prior_status == "succeeded":
            return state.step_results[step.step_id]  # already done

        state.step_status[step.step_id] = "in_progress"
        state.current_step_id = step.step_id
        await self._persist(execution.id, state)
        await self._emit_event(execution.id, step.step_id, "started")

        # Dispatch by step type
        try:
            if step.type == "tool":
                return await self._call_tool(step, state, execution)
            elif step.type == "_test_suspend":  # B-0 only
                return Suspend(reason="_test_suspend", payload={}, ttl_seconds=300)
            else:
                # B-1+ types stub out as failure for now
                raise NotImplementedError(f"step type {step.type} not implemented yet")
        except Exception:
            state.step_status[step.step_id] = "failed"
            await self._persist(execution.id, state)
            raise
```

Parallel steps (#2): wrapped in `asyncio.gather` per "wave" (steps with all `depends_on` satisfied). When one returns Suspend, gather collects all running siblings before propagating.

---

## 5. Routing in `tools/call composition_X`

```python
async def call_tool_composition(name: str, arguments: dict, ctx):
    composition = await load_composition_by_tool_name(name)

    # Static analysis: any suspending step?
    suspending = any(s.type in {"elicit", "wait_callback", "wait_until", "approval", "_test_suspend"}
                     for s in composition.steps)
    forced_async = composition.extra_metadata.get("requires_async") is True
    cron_triggered = ctx.trigger == "cron"

    if not (suspending or forced_async or cron_triggered):
        # Pattern A/B: sync execute, return result inline
        execution_id = await create_execution(composition, ctx, status="running")
        result = await executor.run(execution_id)  # waits to terminal
        return wrap_as_mcp_tool_result(result)

    # Pattern C: detached
    execution_id = await create_execution(composition, ctx, status="running")
    asyncio.create_task(executor.run(execution_id))  # fire-and-forget background

    if ctx.client_capabilities.get("resources", {}).get("subscribe"):
        # Standard path: client will subscribe to the resource
        return {
            "content": [{
                "type": "text",
                "text": f"Composition started. Subscribe to composition://executions/{execution_id} for updates."
            }],
            "structuredContent": {
                "execution_id": str(execution_id),
                "resource_uri": f"composition://executions/{execution_id}",
                "status": "running"
            },
            "isError": False
        }

    # Fallback (#7): client without subscribe — point at webapp + polling tool
    return {
        "content": [{
            "type": "text",
            "text": (
                f"Composition started but your client doesn't support resource subscriptions.\n\n"
                f"Execution ID: {execution_id}\n"
                f"Status URL: https://bigmcp.cloud/app/compositions/executions/{execution_id}\n"
                f"Or call: composition_status(execution_id=\"{execution_id}\") to poll."
            )
        }],
        "structuredContent": {
            "execution_id": str(execution_id),
            "status": "running",
            "polling_tool": "composition_status",
            "webapp_url": f"https://bigmcp.cloud/app/compositions/executions/{execution_id}"
        },
        "isError": False
    }
```

---

## 6. MCP resource handler

### 6.1 `resources/list`
Adds entries `composition://executions/{id}` for executions where `user_id == current_user.id`. Filters by status (running + suspended visible by default; completed visible if not too old).

### 6.2 `resources/read`
For URI `composition://executions/{id}`:
1. Parse `id`
2. Query `composition_execution WHERE id = ? AND user_id = ?`
3. If no row → 404 (no info leak)
4. Return contents:
```json
{
  "uri": "composition://executions/abc",
  "mimeType": "application/json",
  "text": "{\"status\":\"running\",\"current_step_id\":\"3\",\"step_results\":{...},\"started_at\":\"...\"}"
}
```

### 6.3 `resources/subscribe` and `resources/unsubscribe`
Track `(session_id, uri)` pairs in-memory `Dict[str, Set[str]]`. On state transition of a subscribed execution, push `notifications/resources/updated` to the session if connected, else queue in `pending_notification`.

### 6.4 Notification flush on `initialize`
When a session sends `initialize` (could be the same client reconnecting):
1. Look up `pending_notification WHERE session_id = ?`
2. Push each as `notifications/resources/updated`
3. Delete the rows

The `mcp_session_id` on `composition_execution.mcp_session_id` is the original session that triggered. New sessions of the same user won't auto-receive — but they CAN list `resources/list` and see the executions there (UI BigMCP also shows them).

---

## 7. The new `composition_status` meta-tool

Added to `pool/definitions.py` alongside `search`, `execute`, `describe_tool`. Used by:
- Clients that didn't subscribe (fallback polling)
- Agents that explicitly want to check on a long-running execution

```python
{
    "name": "composition_status",
    "title": "Check the status of a running composition",
    "description": "Returns the current status, step results, and (if available) final result of a composition execution started via `composition_X` or scheduled via cron. Use the execution_id returned by tools/call.",
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
            "status": {"type": "string", "enum": ["queued","running","suspended","completed","failed","expired","cancelled"]},
            "current_step_id": {"type": ["string","null"]},
            "step_results": {"type": "object"},
            "result": {},
            "error": {"type": ["string","null"]},
            "expires_at": {"type": ["string","null"]}
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

---

## 8. Endpoints

```
GET    /api/v1/compositions/executions
       ?status=running,suspended  filter
       ?limit=50&offset=0          paginate
       Returns: list of execution summaries for current user

GET    /api/v1/compositions/executions/{id}
       Returns: full detail (state, events, result/error)

POST   /api/v1/compositions/executions/{id}/cancel
       Sets cancel_requested=true
       Returns: 202 Accepted

POST   /api/v1/compositions/executions/{id}/resume
       Body: { response: <step-type-specific> }
       Used by webhook + UI elicit response (B-1)
       In B-0: only accepts response for `_test_suspend` (debug)

GET    /api/v1/compositions/{composition_id}/executions
       Admin view: all executions of a composition (audit)
```

---

## 9. UI

### Page `/app/compositions/executions`
- List per user, filters by status
- Columns: composition name, status badge, started_at, last_update, current step, actions (cancel | view)
- Auto-refresh every 5s for non-terminal statuses (or via SSE in v2)
- Empty state: "No executions yet."

### Page `/app/compositions/executions/{id}`
- Header: composition name + status + cancel button (if running/suspended)
- Timeline of `execution_step_event` rows
- Current step highlighted if `running` or `suspended`
- For `suspended` with `_test_suspend`: a button "Provide test response" that POSTs to `/resume`
- Final result (if `completed`) or error (if `failed`) at the bottom

### Banner global (in MainLayout)
- Counts `suspended` executions for current user
- Click → navigates to executions page filtered by suspended

---

## 10. Tests (8 must-pass before merge)

```python
# tests/test_composition_executions_b0.py

async def test_sync_composition_unchanged():
    """Pattern A: existing sync compo runs end-to-end identically."""
    # Use Hostinger Overview composition or seed equivalent
    # Assert tool result returned inline, no execution row stuck

async def test_test_suspend_round_trip():
    """B-0 mechanism: _test_suspend yields, manual resume continues."""
    # Create compo with [tool, _test_suspend, tool]
    # Trigger via tools/call → execution suspended
    # POST /resume with payload → execution completes
    # Assert all steps succeeded

async def test_pattern_c_resource_flow():
    """tools/call → immediate return + resource subscribe + notif on complete."""
    # Mock client with resources.subscribe capability
    # Call composition_X with _test_suspend
    # Assert immediate return with resource_uri
    # Subscribe to the uri
    # Resume the suspended execution
    # Assert notifications/resources/updated received
    # Read the resource → status=completed

async def test_idempotence_after_crash():
    """If executor crashes mid-step, resume detects in_progress and doesn't re-fire."""
    # Mark step as in_progress in DB
    # Call resume
    # Assert tool NOT re-invoked, step marked failed (non-idempotent default)

async def test_cancel_during_running():
    """Cancel mid-flight → in-flight step finishes, execution marked cancelled."""

async def test_subcomposition_durable():
    """Compo A calls compo B; B suspends; A status = suspended; resume B → A continues."""

async def test_capability_negotiation_no_subscribe():
    """Client without resources.subscribe gets the text fallback + polling tool hint."""

async def test_per_user_resource_isolation():
    """User A cannot read composition://executions/{id_of_user_B}."""
```

Bonus (not blocking merge but desirable):
- Concurrent execution quota (#11): trigger 51 → 51st gets queued
- Step result > 256KB → spilled to `execution_step_payload`

---

## 11. Migration / backward compat

- Existing live compositions: 100% sync (no suspending steps) → routed to Pattern A → no behaviour change
- Existing in-flight executions: there is no "in-flight" state today (executor is sync), so no migration of prior state
- Pydantic schema dual-read (#14): `step_id` accepts both `id` and `step_id` aliases on read; writes canonical `step_id`. After 2 weeks, audit DB and migrate writes if all consumers updated

Migration file (Alembic) creates the 4 new tables. Reversible via standard `downgrade()`.

---

## 12. Estimation

| Sub-task | Days |
|---|---|
| Migration + models + schemas (`composition_execution`, events, payloads, pending_notif) | 2 |
| Executor refactor (state machine + persist + resume + idempotence) | 4 |
| Sub-composition support + chain propagation | 2 |
| MCP resource handler + per-user scoping + subscribe/unsubscribe + notif flush | 2 |
| `composition_status` meta-tool + fallback path | 1 |
| Pattern routing (A/B/C decision) in `call_tool` | 1 |
| Endpoints + Pydantic schemas | 1 |
| UI page list + detail + banner | 3 |
| Tests E2E (8 must-pass) | 3 |
| Pydantic mismatch fix (#14) + `server_bindings` deprecation (#15) | 1 |
| Buffer for surprises | 2 |

**Total: ~22 days realistic**, ~15 days minimum if all goes well.

---

## 13. Out of scope for B-0 (defers to next phases)

- Step types `elicit`, `wait_callback`, `wait_until`, `sample`, `approval` → B-1 to B-5
- Cron triggers + `composition_schedule` table → B-2
- Cross-user notifications (`user_notification` table) → B-1
- LLM cost accounting → B-5
- Branch / parallel / loop control flow → B-6
- `${binding.X}` resolver → only if needed in B-1+
- Email out-of-band notifications → optional in B-2

---

## 14. Open questions for review

1. Should `composition_status` be public to ALL clients or only emit for those without subscribe? (currently: always public, doesn't hurt)
2. TTL defaults: 24h for `_test_suspend`, but should longer types (B-3 wait_callback) push 7 days at suspension time? Decision: yes, set per Suspend payload.
3. Should we support resource subscription for COMPLETED executions too (so the client can re-fetch the result later)? Or are completed executions "read-only and that's it"? Decision: read-only, completed events fire one final notification then unsubscribe is implicit.
4. UI auto-refresh via polling (5s) or via SSE pushed from backend? B-0 ships polling, future polish to SSE.

Reviewer can amend.
