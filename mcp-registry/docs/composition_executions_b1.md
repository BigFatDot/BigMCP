# Composition Workflow Engine — Phase B-1 design

> **Status**: design draft. B-0 (durable suspension infra) is shipped — see
> `composition_executions_b0.md`. B-1 builds on top of it by adding the
> first batch of **production-ready suspending step types**, exercising
> the suspension/resume loop with real semantics rather than the
> debug-only `_test_suspend`.
>
> **Scope freeze**: this document covers the FIRST B-1 step type
> (`elicit`) end-to-end. Subsequent step types (`wait_until`,
> `subcomposition`, `wait_callback`, `approval`) get their own design
> doc as they get queued.

## 0. Why B-1 — what suspends today vs. tomorrow

B-0 ships the suspension MACHINERY (status-as-lock, MCP resource +
notify, REST resume, queue, orphan recovery). The only step type
that exercises it is `_test_suspend` — a debug type whose payload
shape is opaque and whose only job is to round-trip a yield/resume.

B-1 turns the machinery into a real product. The unifying contract:

> A step that suspends MUST declare **(a)** the reason it suspended
> so the resume path can validate the response, **(b)** a schema for
> the response so authors and clients agree on the shape, and **(c)**
> a TTL so abandoned suspensions auto-expire instead of leaking
> resources.

`_test_suspend` violates (a) and (b) by design. The B-1 step types
fix this.

## 1. Step types in scope (B-1)

| Step type     | Resume trigger                                       | Schema?              | TTL default | Cross-user? |
|---------------|------------------------------------------------------|----------------------|-------------|-------------|
| `elicit`      | MCP `notifications/elicitation/create` round-trip OR REST `/resume` | YES (per spec)       | 5 min       | NO (caller only) |
| `wait_until`  | clock tick (executor scheduler)                       | N/A (no payload)     | the wait    | N/A         |
| `subcomposition` | child execution reaches a terminal state          | child result envelope | parent ttl  | N/A         |
| `wait_callback` | external HTTP POST with HMAC token                  | per-step `expected_schema` | 24h     | NO (caller only) |
| `approval`    | another user's `/approve` REST call                   | YES (per-step)       | 24h         | YES (deferred to B-1.4) |

**This document covers `elicit` only. Other types get their own doc.**

## 2. `elicit` — the first B-1 step type

### 2.1 Why `elicit` first

- **Highest leverage**: the most common workflow gap is "ask the user
  something mid-flow". Approval gates, parameter clarification,
  confirmation before destructive actions — all are special cases of
  `elicit`.
- **Smallest cross-cutting**: same-user only (B-0's notification
  routing already supports this), no new auth, no new infrastructure
  beyond the dispatch branch + UI widget.
- **MCP-native**: the spec gives us
  `notifications/elicitation/create` for clients that support it; we
  fall back gracefully to the REST `/resume` path for clients that
  don't (B-0 chunk 4 capability negotiation).

### 2.2 Author-facing shape

A composition author declares an `elicit` step:

```json
{
  "step_id": "confirm_destructive_action",
  "type": "elicit",
  "elicit": {
    "message": "About to delete ${step_load_record.title}. Confirm?",
    "schema": {
      "type": "object",
      "properties": {
        "confirmed": {"type": "boolean"},
        "reason":    {"type": "string", "maxLength": 200}
      },
      "required": ["confirmed"]
    },
    "ttl_seconds": 300
  },
  "depends_on": ["load_record"]
}
```

- `message` — free-form prompt; supports `${input.X}` and `${step_X.path}`
  substitutions, resolved at suspend time (NOT at resume time, so the
  prompt the user saw is what they answered).
- `schema` — JSON Schema validated against the resume payload BOTH
  client-side (UI form generation) AND server-side (REST resume +
  MCP elicitation response). Reject 422 on mismatch.
- `ttl_seconds` — defaults to 300 (5 min). Hard cap: 86_400 (24h);
  longer-running waits should use `wait_until` or `wait_callback`.

### 2.3 Runtime contract

**Suspend payload** (lives in `state.suspension`):

```json
{
  "reason": "elicit",
  "payload": {
    "step_id": "confirm_destructive_action",
    "message": "About to delete record_42. Confirm?",
    "schema": { ... },
    "client_capabilities_at_suspend": { ... }
  },
  "ttl_seconds": 300
}
```

The `message` is the RESOLVED prompt (substitutions already applied).
`client_capabilities_at_suspend` is a snapshot so the resume path
can decide whether the original session supported MCP elicitation —
relevant when a different SSE session ends up draining the resume
notification.

**Resume payload** (POST `/api/v1/compositions/executions/{id}/resume`):

```json
{ "response": {"confirmed": true, "reason": "approved by ops"} }
```

The executor validates `response` against `state.suspension.payload.schema`
BEFORE calling the underlying `executor.resume(...)`. On validation
failure, return 422 with the JSON Schema error path; the row stays
in `suspended` so the user can retry.

### 2.4 MCP elicitation round-trip

When the gateway holds a live SSE session for the user that triggered
the execution AND that session declared `elicitation: true` in its
`initialize` capabilities, we don't wait for the user to open the UI
— we push an MCP elicitation request:

```jsonc
// → client (server-initiated)
{
  "jsonrpc": "2.0",
  "id": "elicit_<execution_id>_<step_id>",
  "method": "elicitation/create",
  "params": {
    "message": "About to delete record_42. Confirm?",
    "requestedSchema": { "type": "object", ... }
  }
}

// ← client
{
  "jsonrpc": "2.0",
  "id": "elicit_<execution_id>_<step_id>",
  "result": { "action": "accept", "content": {"confirmed": true, ...} }
}
```

Inbound elicitation `result` lands at a new gateway dispatch branch
that maps `action: 'accept'` → `POST /resume` with `response = content`,
`action: 'reject'` → `POST /resume` with `response = {"_rejected": true}`
which the executor treats as a controlled failure on the suspended
step (step fails, composition flow continues per `step.optional`),
`action: 'cancel'` → `POST /cancel` on the execution.

Clients without `elicitation: true` capability get the standard
B-0 Pattern C response (subscribe to the resource URI + see the
suspended step in the web UI).

### 2.5 UI

`ExecutionDetailPage` already renders "Provide test response" for
`_test_suspend`. We extend the same component with an `elicit`
arm:

- Render a form generated from `state.suspension.payload.schema`
  (use react-hook-form + Zod from the existing schema, or a simple
  JSON-Schema → form mapper for B-1; sub-objects + arrays land in
  B-1.1 if needed).
- Display `state.suspension.payload.message` as the prompt.
- Submit → POST `/resume` with `{ "response": <form values> }`.
- 422 errors → inline field-level highlighting.

The list page gets a special status badge for `elicit` rows so users
can spot pending decisions at a glance.

### 2.6 Invariants

1. **Schema validation on resume is server-side authoritative**.
   Client-side validation is for UX, never for security.
2. **The resolved prompt is captured at suspend time**. Re-resolving
   at resume time would change the question after the user saw it.
3. **Same-user only in B-1**. The user_id on the execution is the
   only one allowed to resume; cross-user elicitation lands in B-1.4
   (`approval` step type) with its own permission model.
4. **TTL enforced**. The B-0 expiry scanner already moves
   `suspended` rows past `expires_at` to `expired`. `elicit` reuses
   this — no new scanner needed.
5. **Idempotence**: `elicit` is implicitly idempotent — re-rendering
   the prompt is harmless. The post-resume step that follows must
   be idempotent on its own merits.

## 3. Implementation plan

### Chunk 1 — executor dispatch + suspension shape
- Add `"elicit"` to `SUSPENDING_STEP_TYPES` in `composition_routing.py`.
- New branch in `_execute_step` that resolves the prompt
  substitutions, builds a `Suspend(reason="elicit", payload=…,
  ttl_seconds=…)`, and yields it.
- New schema validation helper:
  `app/orchestration/elicit_validation.py::validate_elicit_response(state, response)`
  used by REST resume + MCP elicitation result dispatch.
- 5 tests in `tests/test_elicit_step_b1.py`: yields with resolved
  prompt, ttl honoured, schema validation accept, schema validation
  reject (422), expired suspension auto-fails.

### Chunk 2 — REST resume validation + MCP elicitation/create dispatch
- `POST /resume`: when the suspended step type is `elicit`, validate
  `body.response` against the stored schema before delegating to the
  executor; 422 on failure with the JSON Schema error path.
- New gateway helper: `push_elicitation_create_to_session(session_id,
  execution_id, step_id, message, schema)` — symmetric to chunk 7's
  `push_resource_updated_to_session`. Best-effort; falls back to the
  pending-notification queue if the session is offline.
- New gateway dispatch branch for inbound JSON-RPC `result` to an
  `elicit_*` request id: routes to the validation + resume path.
- 4 tests: REST validate accept, REST validate reject (422), MCP
  result accept → resume, MCP result reject → controlled failure.

### Chunk 3 — UI form generation
- Extend `ExecutionDetailPage` with an `<ElicitForm>` component that
  takes the JSON Schema + initial values + submit handler.
- Status badge in `ExecutionsListPage` for `elicit` rows.
- Lightweight schema → form mapper (string / number / boolean /
  enum / required) for B-1.0; richer mapping (sub-objects, arrays,
  oneOf) deferred to B-1.1.
- 2 manual smoke tests: prompt + form rendered, submit fires resume.

### Chunk 4 — composition author validation
- Promote validator (`composition_promote_validation.py`) checks
  that `elicit` steps declare `elicit.message` + `elicit.schema`,
  that the schema is a valid JSON Schema, and that `ttl_seconds`
  if present is in `[1, 86400]`.
- 4 tests: missing message rejected, missing schema rejected,
  invalid schema rejected, ttl out-of-range rejected.

## 4. Non-goals for B-1.0

- Cross-user elicitation (waits for `approval` step type — B-1.4).
- Schema → form mapping for sub-objects, arrays, oneOf, conditional
  required (B-1.1).
- Replay-on-reconnect for the MCP elicitation request itself
  (current B-0 pending-notification only covers `resources/updated`).
  An offline elicitation falls through to the UI path.
- Streaming progress updates during the resume continuation
  (Pattern B is still deferred to its own phase).

## 5. Tests (B-1.0 must-pass)

```python
# tests/test_elicit_step_b1.py — 11 tests

def test_elicit_yields_with_resolved_prompt()
def test_elicit_yields_with_step_substitution()  # ${step_X.path}
def test_elicit_ttl_honoured()
def test_elicit_response_validates_against_schema_accept()
def test_elicit_response_validates_against_schema_reject_422()
def test_elicit_expired_suspension_marked_expired()
def test_elicit_resume_idempotent_on_replay()
def test_elicit_promote_validator_rejects_missing_message()
def test_elicit_promote_validator_rejects_invalid_schema()
def test_elicit_promote_validator_rejects_ttl_out_of_range()
def test_elicit_mcp_round_trip_accept_path()
```

## 6. Migration

None. `elicit` is pure code — uses existing `composition_execution.state`
and `pending_notification` schemas.

## 7. Audit log events

- `composition.elicit_requested`  — when the suspend lands (per-step audit
  beyond the existing execution_suspended event).
- `composition.elicit_responded`  — when the resume validates +
  delegates.
- `composition.elicit_rejected`   — when the user clicks "reject" or
  the schema validation fails permanently.

## 8. Roadmap after B-1.0

- **B-1.1**: richer JSON-Schema → form mapping (sub-objects, arrays).
- **B-1.2**: `wait_until` step type (clock-driven resume).
- **B-1.3**: `subcomposition` step type (uses the B-0 propagation hook).
- **B-1.4**: `approval` step type (cross-user elicitation, needs the
  cross-user notification table deferred from B-0 §9).
- **B-1.5**: `wait_callback` step type (HMAC-signed external resume).
