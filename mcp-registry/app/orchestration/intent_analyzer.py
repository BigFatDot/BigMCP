"""
Intent Analyzer
===============

Analyzes user intent and proposes orchestrated workflows using LLM API.

Uses:
- LLM API (Mistral, OpenAI, etc.) for intent understanding
- Registry for tool discovery
- Vector search for tool matching
"""

import logging
import os
import uuid
from typing import Dict, Any, List, Optional
import httpx

from ..core.registry import MCPRegistry
from .composition_store import get_composition_store, CompositionInfo

logger = logging.getLogger("orchestration.intent_analyzer")


class IntentAnalyzer:
    """
    Analyzes user queries to propose orchestrated workflows.

    Uses LLM API capabilities to:
    1. Understand what the user wants to accomplish
    2. Search for relevant tools
    3. Build a step-by-step execution plan
    4. Identify missing information
    """

    def __init__(self, registry: MCPRegistry):
        """
        Initialize intent analyzer.

        Args:
            registry: MCP Registry for tool access
        """
        self.registry = registry

        # Use singleton composition store (shared across all modules)
        self.composition_store = get_composition_store()

        # LLM API configuration (compatible with Mistral, OpenAI, etc.)
        self.llm_url = os.environ.get(
            "LLM_API_URL",
            "https://api.mistral.ai/v1"
        )
        self.llm_api_key = os.environ.get("LLM_API_KEY", "")
        self.llm_model = os.environ.get(
            "LLM_MODEL",
            "mistral-small-latest"
        )

        # HTTP client for LLM API
        self.http_client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }
        )

    async def analyze(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        available_tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Analyze user query and propose workflow.

        Args:
            query: User request in natural language
            context: Additional context (previous interactions, etc.)
            available_tools: Pre-fetched tools for the user (multi-tenant mode)

        Returns:
            Analysis result with proposed workflow
        """
        context = context or {}

        try:
            # Step 1: Use provided tools or search for relevant tools
            if available_tools:
                # The caller (L3 _run_full_orchestration) already selected and
                # ranked the relevant pool entries against the goal. Trust that
                # selection — re-filtering here with a naive lexical match that
                # only inspected the (often English) description, against a
                # possibly French goal, silently dropped the real tools and left
                # only an arbitrary subset (the pool-visibility bug).
                relevant_tools = available_tools
                logger.info(f"Using {len(relevant_tools)} caller-provided tools (multi-tenant)")
            else:
                # Fallback to registry search (legacy mode)
                relevant_tools = await self._search_relevant_tools(query)

            if not relevant_tools:
                return {
                    "query": query,
                    "intent": "unclear",
                    "confidence": 0.0,
                    "message": "No relevant tools found for this query",
                    "proposed_composition": None
                }

            # Step 2: Use LLM API to analyze intent and build workflow
            analysis = await self._analyze_with_llm(query, relevant_tools, context)

            # Step 3: Validate and enrich the analysis
            enriched_analysis = await self._enrich_analysis(analysis, relevant_tools)

            # Step 4: Save the composition if one was proposed
            # Only save compositions with more than 1 step (multi-tool workflows)
            if enriched_analysis.get("proposed_composition"):
                try:
                    composition_data = enriched_analysis["proposed_composition"]
                    steps = composition_data.get("steps", [])

                    # Skip saving single-tool compositions
                    if len(steps) <= 1:
                        logger.info(
                            f"⏭️ Skipping save for single-tool composition "
                            f"(steps: {len(steps)})"
                        )
                    else:
                        # Create CompositionInfo object
                        composition_info = CompositionInfo(
                            id=composition_data.get("id"),
                            name=composition_data.get("name"),
                            description=composition_data.get("description"),
                            steps=steps,
                            data_mappings=composition_data.get("data_mappings", []),
                            input_schema=composition_data.get("input_schema", {}),
                            output_schema=composition_data.get("output_schema"),
                            metadata={
                                "query": query,
                                "intent": enriched_analysis.get("intent"),
                                "confidence": enriched_analysis.get("confidence"),
                                "created_by": "intent_analyzer",
                                "context": context
                            }
                        )

                        # Save with 1 hour TTL by default
                        await self.composition_store.save_temporary(composition_info, ttl=3600)

                        logger.info(
                            f"💾 Composition saved: {composition_info.id} "
                            f"(TTL: 1h, steps: {len(composition_info.steps)})"
                        )

                except Exception as e:
                    logger.error(f"Error saving composition: {e}", exc_info=True)
                    # Don't fail the analysis if storage fails

            return enriched_analysis

        except Exception as e:
            logger.error(f"Error analyzing intent: {e}", exc_info=True)
            return {
                "query": query,
                "intent": "error",
                "confidence": 0.0,
                "error": str(e)
            }

    async def _search_relevant_tools(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for tools relevant to the query.

        Uses semantic search to find tools that might help.
        """
        try:
            results = await self.registry.search_tools(query, limit=limit)
            logger.info(f"Found {len(results)} relevant tools for query: {query}")

            # Convert ToolInfo objects to dicts for JSON serialization
            serializable_results = []
            for tool in results:
                if hasattr(tool, 'dict'):
                    serializable_results.append(tool.dict())
                elif hasattr(tool, 'model_dump'):
                    serializable_results.append(tool.model_dump())
                else:
                    serializable_results.append(tool)

            return serializable_results

        except Exception as e:
            logger.error(f"Error searching tools: {e}", exc_info=True)
            return []

    async def _analyze_with_llm(
        self,
        query: str,
        available_tools: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use LLM API to analyze intent and plan workflow.

        Sends a prompt to the LLM with:
        - User query
        - Available tools
        - Context
        And asks it to propose a workflow.
        """
        # Build prompt for LLM
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(query, available_tools, context)

        try:
            # Call LLM API (OpenAI-compatible endpoint)
            chat_url = f"{self.llm_url}/chat/completions" if "/v1" in self.llm_url else f"{self.llm_url}/v1/chat/completions"
            response = await self.http_client.post(
                chat_url,
                json={
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,  # Low temperature for structured output
                    "max_tokens": 2000
                }
            )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text}")
                raise Exception(f"LLM API returned status {response.status_code}")

            result = response.json()

            # Extract response
            assistant_message = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse the structured response
            analysis = self._parse_llm_response(assistant_message, query)

            return analysis

        except Exception as e:
            logger.error(f"Error calling LLM API: {e}", exc_info=True)
            # Fallback to basic analysis
            return self._fallback_analysis(query, available_tools)

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for LLM.

        Instructs the LLM on how to analyze intents and propose workflows.
        """
        return """You are an intelligent workflow orchestrator for the MCPHub Gateway.

Your role is to analyze user requests and propose step-by-step workflows using available MCP tools.

## CRITICAL CONSTRAINTS
1. ONLY use tools EXPLICITLY listed in "Available Tools"
2. DO NOT invent tools - if capability is missing, add to "missing_information"
3. Tool names use format: ServerName__tool_name (e.g., "Grist__list_workspaces")
4. PARAMETERS:
   - ALWAYS fill the parameters that carry the user's intent: a search tool's
     `query`/keywords MUST hold the user's search term (e.g. query="Paris"),
     an id/name param MUST hold the referenced value. Never leave these empty.
   - Do NOT add INCIDENTAL optional params (sort, order, filters, pagination,
     page, page_size, limit, …) unless the user explicitly asked for that
     behaviour. Never guess a value. Each param must exist in the tool's schema.
     Spurious params (e.g. sort="-last_modified") cause API 400 errors.

## COMPOSITION SYNTAX

### Parameter References (${...})
| Syntax | Description | Example |
|--------|-------------|---------|
| ${input.param} | Input parameter | ${input.workspace_id} |
| ${step_X.field} | Field from step X | ${step_1.id} |
| ${step_X.path.to.value} | Nested field | ${step_1.data.items[0].name} |

### Bridging prose output → `transform` step
Some tools return human-readable TEXT (a single string under
${step_X.structuredContent.result}) rather than navigable fields. If a LATER
step needs a specific value (an id, a name) out of such prose, you CANNOT
reference it with ${step_X.field} — there is no field to navigate. Insert a
`transform` step that extracts the structure you need:
{
  "step_id": "1b",
  "type": "transform",
  "source": "${step_1.structuredContent.result}",
  "output_schema": {"type":"object","properties":{
      "items":{"type":"array","items":{"type":"object",
        "properties":{"id":{"type":"string"}},"required":["id"]}}},
    "required":["items"]}
}
⚠️ The transform `source` MUST point at the RAW text the upstream tool
returned — almost always `${step_X.structuredContent.result}`. NEVER point
source at a structured sub-path like `${step_2.datasets}` or
`${step_1.organizations[0].id}`: that path does NOT exist on a prose tool
(its whole output is one text string). Extracting the structure is exactly
what transform does — so feed it the raw text, not an imagined field.

Then reference the transform's output DIRECTLY (it is already structured, no
.structuredContent prefix): ${step_1b.items[0].id}.
Use `transform` ONLY when a downstream step genuinely needs a value buried in
prose — it costs one LLM call. If a tool already returns structured fields,
reference them directly and skip transform.

### Fan-out over a list → `foreach` step
When the goal needs a tool run ONCE PER ITEM of a list (e.g. "for each
dataset, get its metrics") and that tool takes a SINGLE value (not an array),
do NOT pass a wildcard list to a single-value param — it fails validation.
Use a `foreach` step: it runs the inner `do` sub-step once per element, with
the current element available as ${_item}:
{
  "step_id": "3",
  "type": "foreach",
  "items": "${step_2b.datasets[*].id}",
  "do": {"tool": "DataGouv__get_metrics", "parameters": {"dataset_id": "${_item}"}}
}
Its result is {"results": [...], "count": N}; reference downstream as
${step_3.results[*]...}. (If the tool itself ACCEPTS an array param, prefer the
_template/_map pattern in a single call instead of foreach.)

### Wildcard [*] - Extract ALL from array
- ${step_1.items[*].id} → ["id1", "id2", "id3"]
- ${step_1.workspaces[*].docs[*].id} → flattened list

### Template/Map Pattern - Transform each item
{
  "_template": "${step_1.items[*]}",
  "_map": {
    "id": "${_item.id}",
    "parent_id": "${_parent.id}",
    "synced_at": "${_now}"
  }
}
Variables: ${_item}, ${_parent}, ${_root}, ${_index}, ${_now}

## RESPONSE FORMAT
{
  "intent": "category (data_sync, document_creation, etc.)",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "proposed_steps": [
    {
      "step_id": "1",
      "tool": "ServerName__tool_name",
      "description": "what this step does",
      "parameters": {"param": "${input.value}"}
    },
    {
      "step_id": "2",
      "tool": "ServerName__other_tool",
      "parameters": {
        "ids": "${step_1.items[*].id}",
        "data": {
          "_template": "${step_1.items[*]}",
          "_map": {"id": "${_item.id}", "timestamp": "${_now}"}
        }
      }
    }
  ],
  "missing_information": [
    {"parameter": "name", "question": "What is...?", "step": "1", "reason": "..."}
  ]
}

## EXAMPLE
Tools: ["Grist__list_workspaces", "Grist__list_docs", "Notion__create_page"]
Query: "sync Grist docs to Notion"

{
  "intent": "data_sync",
  "confidence": 0.9,
  "reasoning": "Sync Grist documents to Notion pages",
  "proposed_steps": [
    {"step_id": "1", "tool": "Grist__list_workspaces", "parameters": {}},
    {"step_id": "2", "tool": "Grist__list_docs", "parameters": {"workspace_id": "${step_1.workspaces[0].id}"}},
    {"step_id": "3", "tool": "Notion__create_page", "parameters": {
      "pages": {"_template": "${step_2.docs[*]}", "_map": {"title": "${_item.name}", "source_id": "${_item.id}"}}
    }}
  ]
}

## EXAMPLE (prose tool → transform → tool)
Tools: ["DataGouv__search_datasets" (returns prose text),
        "DataGouv__list_dataset_resources" (needs dataset_id)]
Query: "list the resources of the first Paris dataset"

{
  "intent": "data_exploration",
  "confidence": 0.85,
  "reasoning": "search_datasets returns prose; extract the first dataset id with a transform step, then list its resources",
  "proposed_steps": [
    {"step_id": "1", "tool": "DataGouv__search_datasets", "parameters": {"query": "Paris"}},
    {"step_id": "1b", "type": "transform", "source": "${step_1.structuredContent.result}",
     "output_schema": {"type":"object","properties":{
        "datasets":{"type":"array","items":{"type":"object",
          "properties":{"id":{"type":"string"},"title":{"type":"string"}},"required":["id"]}}},
       "required":["datasets"]}},
    {"step_id": "2", "tool": "DataGouv__list_dataset_resources",
     "parameters": {"dataset_id": "${step_1b.datasets[0].id}"}}
  ]
}
Note: step 1 only sets `query` (no sort/page — not requested). The transform
bridges the prose into a navigable id.
"""

    def _build_user_prompt(
        self,
        query: str,
        available_tools: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> str:
        """
        Build user prompt with query, tools, and context.
        """
        # Format tools for the prompt
        def _fmt_output(tool: Dict[str, Any]) -> str:
            out = tool.get("output") or {}
            fmt = out.get("format")
            if fmt == "prose_text":
                return f"Output: PROSE TEXT ⚠️ {out.get('note', '')}"
            if fmt == "structured":
                return f"Output (structured, navigable): {out.get('schema', {})}"
            return "Output: unknown"

        # The caller already caps + ranks the pool (L3 sends the top-N relevant
        # entries). Render them all — truncating to 10 here previously hid the
        # relevant tools when the pool was larger.
        _PROMPT_TOOL_CAP = 40
        prompt_tools = available_tools[:_PROMPT_TOOL_CAP]
        tools_description = "\n\n".join([
            f"Tool: {tool.get('name')}\n"
            f"Description: {tool.get('description', 'No description')}\n"
            f"Parameters: {tool.get('parameters', {})}\n"
            f"{_fmt_output(tool)}"
            for tool in prompt_tools
        ])

        # Create explicit list of tool names
        tool_names = [tool.get('name') for tool in prompt_tools]
        tool_names_str = ", ".join(tool_names)

        prompt = f"""User Query: {query}

Available Tools (COMPLETE LIST - use ONLY these):
{tools_description}

⚠️  REMINDER: The ONLY valid tool names are: {tool_names_str}
Do NOT use any other tool names.

"""

        if context:
            prompt += f"\nAdditional Context:\n{context}\n"

        prompt += "\nPropose a workflow to accomplish the user's request using ONLY the tools listed above."

        return prompt

    def _parse_llm_response(self, response: str, original_query: str) -> Dict[str, Any]:
        """
        Parse LLM response into structured format.

        Tries to extract JSON from the response.
        """
        import json
        import re

        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{[\s\S]*\}', response)

            if json_match:
                json_str = json_match.group()
                analysis = json.loads(json_str)

                # Ensure required fields
                analysis["query"] = original_query

                if "proposed_steps" in analysis:
                    # Convert to our composition format
                    analysis["proposed_composition"] = {
                        "id": f"temp_{uuid.uuid4().hex[:8]}",
                        "name": f"Workflow for: {original_query[:50]}",
                        "description": analysis.get("reasoning", ""),
                        "steps": analysis["proposed_steps"]
                    }

                if "missing_information" in analysis:
                    analysis["missing_parameters"] = analysis["missing_information"]

                return analysis

            # If no JSON found, create basic structure
            return {
                "query": original_query,
                "intent": "unclear",
                "confidence": 0.5,
                "reasoning": response[:500],  # First 500 chars
                "proposed_composition": None
            }

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing LLM response: {e}")
            logger.debug(f"Response was: {response}")

            return {
                "query": original_query,
                "intent": "unclear",
                "confidence": 0.3,
                "error": "Could not parse LLM response",
                "raw_response": response[:500]
            }

    def _fallback_analysis(
        self,
        query: str,
        available_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Fallback analysis when LLM API fails.

        Returns basic tool suggestions without workflow planning.
        """
        return {
            "query": query,
            "intent": "tool_search",
            "confidence": 0.5,
            "message": "LLM API unavailable, showing tool suggestions only",
            "suggested_tools": available_tools[:5],
            "proposed_composition": None,
            "note": "Full intent analysis requires LLM API connection"
        }

    @staticmethod
    def _strip_unknown_params(step: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
        """Remove step parameters not declared in the tool's inputSchema.

        Mutates ``step["parameters"]`` in place and returns the list of dropped
        keys. No-op (returns []) when the schema is open or unusable:
        - schema declares no ``properties`` → can't know what's valid
        - ``additionalProperties`` is explicitly ``True`` → extra keys allowed

        JSON Schema's default for additionalProperties is technically ``true``,
        but real MCP servers (data.gouv, n8n, …) validate strictly and 400 on
        unknown keys, so we treat "absent" as strict here.
        """
        params = step.get("parameters")
        if not isinstance(params, dict) or not params:
            return []
        if not isinstance(schema, dict):
            return []
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            return []
        if schema.get("additionalProperties") is True:
            return []

        allowed = set(properties.keys())
        dropped = [k for k in params if k not in allowed]
        for k in dropped:
            del params[k]
        return dropped

    async def _enrich_analysis(
        self,
        analysis: Dict[str, Any],
        available_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Enrich analysis with additional metadata.

        Adds:
        - Parameter schemas
        - Execution time estimates
        - Tool metadata
        - Validates tools exist
        """
        if not analysis.get("proposed_composition"):
            return analysis

        composition = analysis["proposed_composition"]

        # Build set of valid tool names for fast lookup
        valid_tool_names = {t.get("name") for t in available_tools}

        # Build lookup for server.tool_name format -> actual prefixed name
        # Handles cases where LLM generates "server-id.tool_name" instead of "server_id__tool_name"
        original_to_prefixed = {}
        for tool in available_tools:
            metadata = tool.get("metadata", {}) or tool.get("_metadata", {})
            original_name = metadata.get("original_tool_name", "")
            server_id = metadata.get("server_id", "")
            if original_name and server_id:
                # Create lookup keys for different formats the LLM might use
                key1 = f"{server_id}.{original_name}"  # server-id.tool_name
                key2 = f"{server_id.replace('-', '_')}.{original_name}"  # server_id.tool_name
                original_to_prefixed[key1] = tool.get("name")
                original_to_prefixed[key2] = tool.get("name")

        # Validate and enrich each step
        if "steps" in composition:
            invalid_steps = []
            valid_steps = []

            for step in composition["steps"]:
                # Non-tool step types (transform, elicit, …) carry no `tool`
                # field and aren't registry tools — keep them as-is rather
                # than flagging them hallucinated/invalid.
                if step.get("type", "tool") != "tool":
                    valid_steps.append(step)
                    continue

                tool_name = step.get("tool")

                if not tool_name:
                    logger.warning(f"Step {step.get('step_id')} has no tool name")
                    invalid_steps.append(step)
                    continue

                # Try to resolve tool name if not in valid names
                resolved_name = tool_name
                if tool_name not in valid_tool_names:
                    # Check if it's in server.tool format that can be resolved
                    if tool_name in original_to_prefixed:
                        resolved_name = original_to_prefixed[tool_name]
                        step["tool"] = resolved_name  # Rewrite to actual name
                        logger.info(f"Resolved tool name: {tool_name} -> {resolved_name}")
                    else:
                        logger.warning(
                            f"Tool '{tool_name}' in step {step.get('step_id')} "
                            f"does not exist in registry (hallucinated by LLM)"
                        )
                        invalid_steps.append(step)
                        continue

                # Find full tool info
                tool_info = next(
                    (t for t in available_tools if t.get("name") == resolved_name),
                    None
                )

                if tool_info:
                    schema = tool_info.get("parameters") or {}
                    step["tool_info"] = {
                        "description": tool_info.get("description"),
                        "parameters_schema": schema,
                        "server_id": tool_info.get("server_id"),
                        "metadata": tool_info.get("metadata", {})
                    }

                    # Strip LLM-hallucinated parameters: the model is handed the
                    # tool's inputSchema but still invents plausible-looking keys
                    # (e.g. sort=-last_modified on a tool that has no `sort`),
                    # which strict servers reject with HTTP 400. Drop any key not
                    # declared in the schema's properties — unless the schema
                    # explicitly opts into extra keys via additionalProperties.
                    dropped = self._strip_unknown_params(step, schema)
                    if dropped:
                        logger.info(
                            f"Stripped hallucinated params {dropped} from step "
                            f"{step.get('step_id')} (tool {resolved_name})"
                        )

                valid_steps.append(step)

            # Update composition with only valid steps
            composition["steps"] = valid_steps

            # Add warnings about invalid tools
            if invalid_steps:
                analysis["warnings"] = analysis.get("warnings", [])
                analysis["warnings"].append({
                    "type": "invalid_tools",
                    "message": f"Removed {len(invalid_steps)} invalid/hallucinated tools",
                    "invalid_tools": [s.get("tool") for s in invalid_steps]
                })

                logger.info(
                    f"Removed {len(invalid_steps)} invalid tools from composition: "
                    f"{[s.get('tool') for s in invalid_steps]}"
                )

        # Add execution estimate
        if "steps" in composition:
            # Rough estimate: 1 second per step + 0.5s overhead
            estimated_time = len(composition["steps"]) * 1000 + 500
            analysis["estimated_execution_time_ms"] = estimated_time

        return analysis

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()
