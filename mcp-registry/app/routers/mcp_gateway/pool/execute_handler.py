"""
Server-side handler for the `execute` MCP tool.

Routes a request through 4 levels of increasing cost so simple cases stay
fast and cheap:

  L0 explicit (composition_id | tool_name+params)
       → direct call, 0 LLM calls
  L1 pool has a single entry (tool or composition)
       → if params provided: direct; otherwise IntentAnalyzer scoped to
         that single entry (1 LLM call) then execute the plan
  L2 NL goal + clear textual top-1 in the unified pool (tools+compositions)
       → same as L1 with the chosen entry as the only available_tool
  L3 NL goal, ambiguous or multi-step
       → full IntentAnalyzer over the whole pool, then CompositionExecutor

Pool composition:
- Tools where `Tool.is_visible_to_oauth_clients = True` (mutated by `search`)
- All productions compositions of the user's organization (always visible)

An empty pool is a hard error: callers must call `search` first (or create
a production composition) to populate it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from ....db.database import async_session_maker
from .pool_loader import (
    PoolEntry,
    load_visible_pool,
    score_entry,
    serialize_for_intent_analyzer,
)
from .search_handler import _tokenize

logger = logging.getLogger(__name__)


# Conservative thresholds for the L2 shortcut. A clear winner must have a
# meaningful absolute score AND a clear gap over the runner-up.
#
# Calibration rationale (textual scoring on org catalogues, score_entry):
#   - Each query token in the tool name adds +2, in the haystack +1.
#   - "create dns record" against `create_dns_record` gives 9, against an
#     unrelated `send_email` gives 0 — the gap is wide.
#   - "list" alone against a pool full of `list_*` tools gives ties (gap≈0)
#     → must NOT trigger L2.
# A real corpus tuner can use execution_log.shortcut_level + status to
# refine these constants once we have ~1k samples in production.
_L2_MIN_TOP_SCORE = 4
_L2_MIN_GAP = 2


# ---------------------------------------------------------------------------
# Backward-compat helpers exposed for unit tests written before refactor.
# ---------------------------------------------------------------------------


def _sanitize_server_prefix(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name or "")
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe


class _ToolLike:
    """Adapter so test fakes (with attributes mirroring SQLAlchemy Tool) can
    be scored via the unified scorer without instantiating a real PoolEntry."""

    def __init__(self, tool, server_name: str):
        self.tool_name = getattr(tool, "tool_name", "") or ""
        self.display_name = getattr(tool, "display_name", None)
        self.description = getattr(tool, "description", "") or ""
        self.tags = getattr(tool, "tags", None) or []
        self.category = getattr(tool, "category", None)
        self.server_name = server_name


def _score_pool_against_goal(
    goal: str, pool: List[Tuple[Any, Any]]
) -> List[Tuple[int, Any, Any]]:
    """Test-only helper: score a list of (FakeTool, FakeServer) pairs."""
    tokens = _tokenize(goal)
    scored = []
    for tool, server in pool:
        adapter = _ToolLike(tool, getattr(server, "name", "") or "")
        # Reuse the same scoring formula as the unified scorer.
        haystack = " ".join(
            [
                adapter.tool_name,
                adapter.display_name or "",
                adapter.description,
                adapter.category or "",
                adapter.server_name,
                *adapter.tags,
            ]
        ).lower()
        name_lower = adapter.tool_name.lower()
        score = 0
        for token in tokens:
            if not token:
                continue
            if token in name_lower:
                score += 2
            if token in haystack:
                score += 1
        scored.append((score, tool, server))
    scored.sort(key=lambda triple: triple[0], reverse=True)
    return scored


def _single_entry_failed(result: Dict[str, Any]) -> bool:
    """True when an L1/L2 single-entry attempt did not succeed.

    The L2 textual shortcut can misfire on a multi-step goal: a tool whose
    name overlaps the goal (e.g. ``list_dataset_resources`` for a goal about
    "datasets") wins the lexical score, the IntentAnalyzer gets scoped to that
    lone tool, and it emits a 1-step plan that can't fill a required param it
    was supposed to receive from an earlier step. Detecting that here lets the
    caller escalate to full L3 orchestration instead of surfacing a confusing
    single-tool error.
    """
    if not isinstance(result, dict):
        return False
    level = result.get("level", "")
    if isinstance(level, str) and level.endswith("_extraction_failed"):
        return True
    if result.get("error"):
        return True
    # _run_inline_composition wraps execute_direct under "result"
    inner = result.get("result")
    if isinstance(inner, dict) and inner.get("status") in ("failed", "partial"):
        return True
    return False


# ---------------------------------------------------------------------------
# Core execution paths.
# ---------------------------------------------------------------------------


async def _run_explicit_tool(
    gateway: Any,
    tool_name: str,
    params: Dict[str, Any],
    user_id: str,
    organization_id: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """L0 — caller named the tool."""
    return await gateway._route_tool_execution(
        tool_name,
        params,
        session_id=session_id,
        user_id=user_id,
        organization_id=organization_id,
    )


async def _run_composition(
    gateway: Any,
    composition_id: str,
    params: Dict[str, Any],
    user_id: str,
    organization_id: str,
) -> Dict[str, Any]:
    """L0/L1/L2 — execute a saved composition by id."""
    return await gateway.orchestration_tools.execute_composition(
        {
            "composition_id": composition_id,
            "parameters": params,
            "_user_id": user_id,
            "_organization_id": organization_id,
            "_user_server_pool": gateway.user_server_pool,
        }
    )


async def _run_inline_composition(
    gateway: Any,
    composition: Dict[str, Any],
    parameters: Dict[str, Any],
    user_id: str,
    organization_id: str,
    level: str,
) -> Dict[str, Any]:
    executor = gateway.orchestration_tools.composition_executor
    result = await executor.execute_direct(
        composition=composition,
        parameters=parameters,
        execution_mode="auto",
        user_id=user_id,
        organization_id=organization_id,
        user_server_pool=gateway.user_server_pool,
    )
    return {
        "level": level,
        "composition": {
            "name": composition.get("name"),
            "steps_count": len(composition.get("steps", [])),
        },
        "result": result,
    }


async def _extract_composition_params(
    gateway: Any,
    entry: PoolEntry,
    goal: str,
    explicit_params: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Build the parameter dict for a composition.

    Returns ``(params, error)``. On success ``error`` is ``None``. On a
    failure that callers should surface (LLM unreachable, malformed JSON,
    or extracted dict missing fields the composition marks required), we
    return a non-None ``error`` so the caller can stop instead of running
    the composition with bogus parameters and producing a confusing
    downstream failure.

    The "no input schema declared" case is treated as success with empty
    params — that's the legitimate null-arg composition.
    """
    if explicit_params:
        return explicit_params, None

    schema = entry.parameters_schema or {}
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        # Composition declares no inputs — call directly with empty params.
        return {}, None

    required = schema.get("required") or []
    analyzer = gateway.orchestration_tools.intent_analyzer

    import json as _json

    prompt = (
        "Extract input parameters for a saved workflow from the user's goal. "
        "Return ONLY a JSON object matching the schema's properties — no prose, "
        "no markdown, no code fences.\n\n"
        f"Composition: {entry.name}\n"
        f"Description: {entry.description}\n"
        f"Input schema: {_json.dumps(schema)}\n"
        f"Required fields: {required}\n\n"
        f"User goal: {goal}\n\n"
        "JSON:"
    )

    extracted: Dict[str, Any] = {}
    extraction_error: Optional[str] = None

    try:
        chat_url = (
            f"{analyzer.llm_url}/chat/completions"
            if "/v1" in analyzer.llm_url
            else f"{analyzer.llm_url}/v1/chat/completions"
        )
        response = await analyzer.http_client.post(
            chat_url,
            json={
                "model": analyzer.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 400,
            },
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[-2] if raw.count("```") >= 2 else raw
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        candidate = _json.loads(raw) if raw else {}
        if isinstance(candidate, dict):
            extracted = candidate
        else:
            extraction_error = "LLM returned a non-object JSON value"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"composition param extraction failed: {e}")
        extraction_error = f"LLM extraction failed: {e}"

    # If the composition has required fields, refuse to run with a partial
    # set rather than failing later with an opaque executor error.
    if required:
        missing = [k for k in required if k not in extracted or extracted.get(k) in (None, "")]
        if missing:
            return extracted, (
                extraction_error
                or "The LLM could not infer the required parameters: " + ", ".join(missing)
                + ". Retry passing explicit `params`."
            )

    return extracted, None


async def _run_with_single_entry(
    gateway: Any,
    entry: PoolEntry,
    goal: str,
    params: Dict[str, Any],
    user_id: str,
    organization_id: str,
) -> Dict[str, Any]:
    """L1/L2 — one entry to execute. Direct if we have params, else 1 LLM call.

    For tools without params: scope IntentAnalyzer to a single tool to get a
    single-step plan.
    For compositions: if we have params, call the composition directly;
    otherwise also use IntentAnalyzer scoped to the composition to extract
    inputs from the goal.
    """
    if entry.kind == "composition":
        # Compositions are first-class — never fed through IntentAnalyzer to
        # produce a step plan (that would treat them as MCP tools and fail).
        # We extract params from the goal via a dedicated, lightweight LLM
        # call against the composition's input_schema, then invoke the
        # composition directly through the existing orchestration path.
        extracted, extract_error = await _extract_composition_params(
            gateway, entry, goal, params
        )
        if extract_error:
            return {
                "level": "L1_or_L2_composition_extraction_failed",
                "composition_id": entry.id,
                "composition_name": entry.name,
                "extracted_params": extracted,
                "error": extract_error,
            }
        result = await _run_composition(
            gateway, entry.id, extracted, user_id, organization_id
        )
        return {
            "level": (
                "L1_or_L2_composition_direct"
                if params
                else "L1_or_L2_composition_via_intent"
            ),
            "composition_id": entry.id,
            "composition_name": entry.name,
            "extracted_params": extracted if not params else None,
            "result": result,
        }

    # Tool path
    if params:
        result = await _run_explicit_tool(
            gateway,
            entry.name,
            params,
            user_id=user_id,
            organization_id=organization_id,
        )
        return {
            "level": "L1_or_L2_tool_direct",
            "tool": entry.name,
            "server": entry.server_name,
            "result": result,
        }

    serialized = [serialize_for_intent_analyzer(entry)]
    analysis = await gateway.orchestration_tools.intent_analyzer.analyze(
        query=goal,
        context={"single_entry_extraction": True, "kind": "tool"},
        available_tools=serialized,
    )
    proposed = (analysis or {}).get("proposed_composition")
    if not proposed or not proposed.get("steps"):
        return {
            "level": "L1_or_L2_tool_extraction_failed",
            "tool": entry.name,
            "server": entry.server_name,
            "intent_analysis": analysis,
            "error": (
                "Could not infer parameters for this tool from the goal. "
                "Retry passing explicit `params`."
            ),
        }

    return await _run_inline_composition(
        gateway,
        composition=proposed,
        parameters={},
        user_id=user_id,
        organization_id=organization_id,
        level="L1_or_L2_tool_via_intent",
    )


async def _run_full_orchestration(
    gateway: Any,
    goal: str,
    pool: List[PoolEntry],
    params: Dict[str, Any],
    user_id: str,
    organization_id: str,
) -> Dict[str, Any]:
    """L3 — full IntentAnalyzer over the entire pool (tools + compositions)."""
    serialized = [serialize_for_intent_analyzer(e) for e in pool]
    analysis = await gateway.orchestration_tools.intent_analyzer.analyze(
        query=goal,
        context={"pool_orchestration": True, "pool_size": len(pool)},
        available_tools=serialized,
    )
    proposed = (analysis or {}).get("proposed_composition")
    if not proposed or not proposed.get("steps"):
        return {
            "level": "L3_no_plan",
            "intent_analysis": analysis,
            "error": (
                "Could not build a plan from the loaded pool. The tools in "
                "your pool may not be relevant to the goal — try `search` "
                "with a different query."
            ),
        }

    return await _run_inline_composition(
        gateway,
        composition=proposed,
        parameters=params,
        user_id=user_id,
        organization_id=organization_id,
        level="L3_orchestrated",
    )


def _classify_status(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "success"
    if payload.get("error"):
        return "failed"
    inner = payload.get("result")
    if isinstance(inner, dict):
        s = inner.get("status")
        if isinstance(s, str):
            return s
    return "success"


async def _log_execution_async(
    *,
    user_id: str,
    organization_id: str,
    session_id: Optional[str],
    goal: Optional[str],
    mode: str,
    shortcut_level: Optional[str],
    composition_id: Optional[str],
    duration_ms: int,
    payload: Dict[str, Any],
) -> None:
    """Fire-and-forget audit row. Never raises into the caller."""
    try:
        from ....core.pii_sanitizer import PIIDetector
        from ....models.execution_log import ExecutionLog
        from sqlalchemy.exc import SQLAlchemyError

        # Goals are user-pasted free text — they may contain emails, tokens,
        # secrets. Strip detected PII before persisting; the audit row keeps
        # the routing semantics (level, status, duration, tools) intact.
        sanitized_goal = PIIDetector.sanitize_text(goal) if goal else goal

        async with async_session_maker() as db:
            try:
                row = ExecutionLog(
                    user_id=UUID(str(user_id)),
                    organization_id=UUID(str(organization_id)),
                    session_id=session_id,
                    goal=sanitized_goal,
                    mode=mode,
                    shortcut_level=shortcut_level,
                    duration_ms=duration_ms,
                    status=_classify_status(payload),
                    error=(payload.get("error") if isinstance(payload, dict) else None),
                    composition_id=(UUID(composition_id) if composition_id else None),
                )
                db.add(row)
                await db.commit()
            except SQLAlchemyError as e:
                logger.warning(f"execution_log insert failed (rolled back): {e}")
                await db.rollback()
    except Exception as e:  # noqa: BLE001 — never let logging break the call
        logger.warning(f"execution_log fire-and-forget failed: {e}")


async def handle_execute(
    arguments: Dict[str, Any],
    user_id: Optional[str],
    organization_id: Optional[str],
    gateway: Any = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Entry point wired from `mcp_unified.py` for the `execute` MCP tool."""
    import asyncio as _asyncio
    import time as _time

    started_at = _time.monotonic()

    goal: Optional[str] = arguments.get("goal")
    tool_name: Optional[str] = arguments.get("tool_name")
    composition_id: Optional[str] = arguments.get("composition_id")
    params: Any = arguments.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return {"error": "`params` must be an object"}

    if not (goal or tool_name or composition_id):
        return {
            "error": (
                "Provide one of: `goal` (NL), `tool_name` (+ params), or "
                "`composition_id` (+ params)."
            )
        }
    if not user_id or not organization_id:
        return {"error": "Authentication required: missing user/organization context"}

    try:
        org_uuid = UUID(str(organization_id))
    except (TypeError, ValueError):
        return {"error": "Invalid organization_id"}

    def _log(payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        try:
            duration_ms = int((_time.monotonic() - started_at) * 1000)
            level_value = (
                payload.get("level") if isinstance(payload, dict) else None
            )
            _asyncio.create_task(
                _log_execution_async(
                    user_id=str(user_id),
                    organization_id=str(organization_id),
                    session_id=session_id,
                    goal=goal,
                    mode=mode,
                    shortcut_level=level_value,
                    composition_id=composition_id,
                    duration_ms=duration_ms,
                    payload=payload,
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"execute logging schedule failed: {e}")
        return payload

    # L0: explicit composition
    if composition_id:
        result = await _run_composition(
            gateway, composition_id, params, user_id, organization_id
        )
        return _log(
            {"level": "L0_composition", "composition_id": composition_id, "result": result},
            mode="composition_id",
        )

    # L0: explicit tool (works for "composition_<name>" tools too via existing routing).
    if tool_name:
        result = await _run_explicit_tool(
            gateway,
            tool_name,
            params,
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
        )
        return _log(
            {"level": "L0_tool", "tool": tool_name, "result": result},
            mode="tool_name",
        )

    if not goal or not isinstance(goal, str) or not goal.strip():
        return {"error": "`goal` must be a non-empty string in goal-mode"}

    async with async_session_maker() as db:
        from uuid import UUID as _UUID
        try:
            user_uuid = _UUID(user_id) if user_id else None
        except (TypeError, ValueError):
            user_uuid = None
        pool = await load_visible_pool(db, org_uuid, user_id=user_uuid)
    if not pool:
        return _log(
            {
                "error": (
                    "Pool is empty. Call `search` first with a query describing "
                    "what you want to do (or create a production composition), "
                    "then retry `execute`."
                )
            },
            mode="goal",
        )

    # L1: single entry
    if len(pool) == 1:
        return _log(
            await _run_with_single_entry(
                gateway,
                pool[0],
                goal=goal,
                params=params,
                user_id=user_id,
                organization_id=organization_id,
            ),
            mode="goal",
        )

    # L2: clear textual winner across tools + compositions
    tokens = _tokenize(goal)
    scored: List[Tuple[int, PoolEntry]] = sorted(
        ((score_entry(tokens, e), e) for e in pool),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if scored:
        top_score, top_entry = scored[0]
        runner_up = scored[1][0] if len(scored) >= 2 else 0
        if top_score >= _L2_MIN_TOP_SCORE and (top_score - runner_up) >= _L2_MIN_GAP:
            l2_result = await _run_with_single_entry(
                gateway,
                top_entry,
                goal=goal,
                params=params,
                user_id=user_id,
                organization_id=organization_id,
            )
            # The lexical winner may have been a red herring for a multi-step
            # goal. If the scoped single-entry run failed, escalate to L3 over
            # the full pool rather than returning the misleading error.
            if not _single_entry_failed(l2_result):
                return _log(l2_result, mode="goal")
            logger.info(
                "L2 single-entry '%s' failed for goal — escalating to L3 full orchestration",
                getattr(top_entry, "name", "?"),
            )

    # L3: full orchestration
    return _log(
        await _run_full_orchestration(
            gateway,
            goal=goal,
            pool=pool,
            params=params,
            user_id=user_id,
            organization_id=organization_id,
        ),
        mode="goal",
    )
