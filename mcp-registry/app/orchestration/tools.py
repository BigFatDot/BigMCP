"""
Orchestration Tools Implementation
===================================

Implements the meta-level orchestration tools that enable
intelligent workflow composition and execution.
"""

import logging
from typing import Dict, Any, List, Optional

from ..core.registry import MCPRegistry
from .intent_analyzer import IntentAnalyzer
from .composition_executor import CompositionExecutor

logger = logging.getLogger("orchestration.tools")


class OrchestrationTools:
    """
    Orchestration tools providing AI-powered capabilities.

    Tools:
    - search_tools: Semantic search for tools
    - analyze_intent: Intent analysis and workflow planning
    - execute_composition: Execute multi-step workflows
    - create_composition: Create reusable compositions
    - list_compositions: List available compositions
    - get_composition: Get composition details
    """

    def __init__(self, registry: MCPRegistry):
        """
        Initialize orchestration tools.

        Args:
            registry: MCP Registry instance for tool access
        """
        self.registry = registry
        self.intent_analyzer = IntentAnalyzer(registry)
        self.composition_executor = CompositionExecutor(registry)

        # Use singleton composition store (shared across all modules)
        from .composition_store import get_composition_store
        self.composition_store = get_composition_store()

    async def search_tools(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Semantic search for tools.

        Uses vector search to find tools based on natural language query.

        Args:
            arguments: {
                "query": "Natural language description",
                "limit": 5,
                "filters": {"server_id": "..."}  # optional
            }

        Returns:
            {
                "query": Original query,
                "results": [
                    {
                        "name": "tool_name",
                        "description": "...",
                        "score": 0.95,
                        "server_id": "...",
                        "parameters": {...}
                    }
                ],
                "count": Number of results
            }
        """
        query = arguments.get("query")
        limit = arguments.get("limit", 5)
        filters = arguments.get("filters", {})

        if not query:
            return {
                "error": "Missing 'query' parameter",
                "query": None,
                "results": [],
                "count": 0
            }

        try:
            # Use registry's semantic search
            results = await self.registry.search_tools(query, limit=limit)

            # Apply filters if specified
            if filters:
                server_id_filter = filters.get("server_id")
                if server_id_filter:
                    results = [
                        r for r in results
                        if r.get("server_id") == server_id_filter
                    ]

            logger.info(f"Search for '{query}' returned {len(results)} results")

            return {
                "query": query,
                "results": results,
                "count": len(results),
                "filters_applied": filters
            }

        except Exception as e:
            logger.error(f"Error searching tools: {e}", exc_info=True)
            return {
                "error": str(e),
                "query": query,
                "results": [],
                "count": 0
            }

    async def analyze_intent(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze user intent and propose workflow.

        Uses LLM API to understand what the user wants to accomplish
        and suggests an orchestrated workflow using available tools.

        Args:
            arguments: {
                "query": "User request in natural language",
                "context": {"previous_interactions": [...], ...}  # optional
            }

        Returns:
            {
                "query": Original query,
                "intent": Detected intent category,
                "confidence": Confidence score (0-1),
                "proposed_composition": {
                    "id": "temp_comp_id",
                    "name": "Composition name",
                    "description": "What it does",
                    "steps": [
                        {
                            "step_id": "1",
                            "tool": "tool_name",
                            "description": "What this step does",
                            "parameters": {...}
                        }
                    ],
                    "data_mappings": [...]
                },
                "missing_parameters": [
                    {
                        "name": "param_name",
                        "step": "step_id",
                        "question": "What is ...?"
                    }
                ],
                "estimated_execution_time_ms": 2500
            }
        """
        query = arguments.get("query")
        context = arguments.get("context", {})
        # Get pre-fetched tools if passed from mcp_unified (multi-tenant)
        available_tools = arguments.get("_available_tools", None)

        if not query:
            return {
                "error": "Missing 'query' parameter",
                "query": None,
                "intent": "unknown",
                "confidence": 0.0
            }

        try:
            # Analyze intent using LLM API (with user's tools if provided)
            analysis = await self.intent_analyzer.analyze(
                query,
                context,
                available_tools=available_tools
            )

            logger.info(
                f"Intent analysis for '{query}': "
                f"{analysis.get('intent')} ({analysis.get('confidence')})"
            )

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing intent: {e}", exc_info=True)
            return {
                "error": str(e),
                "query": query,
                "intent": "error",
                "confidence": 0.0
            }

    async def execute_composition(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a workflow composition.

        Executes a multi-step workflow, handling data flow between steps,
        retries, timeouts, and error handling.

        Supports both stored compositions (by ID) and direct execution (by definition).

        Args:
            arguments: {
                "composition_id": "comp_id",  # For stored compositions
                OR
                "composition": {...},  # For direct execution
                "parameters": {"input_param": "value"},
                "execution_mode": "sequential" | "parallel" | "auto",  # optional
                "stream_results": false,  # optional
                "_user_id": "user_uuid",  # optional - for multi-tenant execution
                "_organization_id": "org_uuid",  # optional - for multi-tenant execution
                "_user_server_pool": UserServerPool  # optional - for multi-tenant tool execution
            }

        Returns:
            {
                "composition_id": "comp_id",
                "execution_id": "exec_123",
                "status": "success" | "failed",
                "result": Final output,
                "steps_executed": [
                    {
                        "step_id": "1",
                        "tool": "tool_name",
                        "status": "success",
                        "duration_ms": 150,
                        "result": {...}
                    }
                ],
                "total_duration_ms": 2450,
                "errors": []  # If any
            }
        """
        composition_id = arguments.get("composition_id")
        composition_def = arguments.get("composition")
        parameters = arguments.get("parameters", {})
        execution_mode = arguments.get("execution_mode", "auto")
        stream_results = arguments.get("stream_results", False)

        # Extract user context for multi-tenant execution
        user_id = arguments.get("_user_id")
        organization_id = arguments.get("_organization_id")
        user_server_pool = arguments.get("_user_server_pool")

        # Check if we have either ID or definition
        if not composition_id and not composition_def:
            return {
                "error": "Missing 'composition_id' or 'composition' parameter",
                "status": "failed"
            }

        try:
            # Execute directly if composition definition is provided
            if composition_def:
                result = await self.composition_executor.execute_direct(
                    composition=composition_def,
                    parameters=parameters,
                    execution_mode=execution_mode,
                    stream_results=stream_results,
                    user_id=user_id,
                    organization_id=organization_id,
                    user_server_pool=user_server_pool
                )

                logger.info(
                    f"Composition executed directly: "
                    f"{result.get('status')} in {result.get('total_duration_ms')}ms"
                )

                return result

            # Otherwise, execute by ID
            else:
                result = await self.composition_executor.execute(
                    composition_id=composition_id,
                    parameters=parameters,
                    execution_mode=execution_mode,
                    stream_results=stream_results,
                    user_id=user_id,
                    organization_id=organization_id,
                    user_server_pool=user_server_pool
                )

                logger.info(
                    f"Composition {composition_id} executed: "
                    f"{result.get('status')} in {result.get('total_duration_ms')}ms"
                )

                return result

        except Exception as e:
            logger.error(f"Error executing composition: {e}", exc_info=True)
            return {
                "error": str(e),
                "composition_id": composition_id or composition_def.get("id"),
                "status": "failed"
            }

    async def create_composition(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new reusable composition.

        Args:
            arguments: {
                "name": "Composition name",
                "description": "What it does",
                "steps": [
                    {
                        "tool": "tool_name",
                        "parameters": {...}
                    }
                ],
                "data_mappings": [...],  # optional
                "input_schema": {...},  # optional
                "output_schema": {...}  # optional
            }

        Returns:
            {
                "composition_id": "comp_123",
                "name": "Composition name",
                "status": "created",
                "validation": {
                    "valid": true,
                    "warnings": [],
                    "errors": []
                }
            }
        """
        import uuid

        name = arguments.get("name")
        description = arguments.get("description")
        steps = arguments.get("steps", [])
        data_mappings = arguments.get("data_mappings", [])
        input_schema = arguments.get("input_schema", {})
        output_schema = arguments.get("output_schema")

        # Extract user context for multi-tenant tracking
        user_id = arguments.get("_user_id")
        organization_id = arguments.get("_organization_id")

        if not name or not steps:
            return {
                "error": "Missing required parameters: 'name' and 'steps'",
                "status": "failed"
            }

        try:
            logger.info(f"Creating composition: {name}")

            # Generate composition ID
            composition_id = f"comp_{uuid.uuid4().hex[:8]}"

            # Enrich steps with step_ids if missing
            for idx, step in enumerate(steps, start=1):
                if "step_id" not in step:
                    step["step_id"] = str(idx)

            # Validate tools exist
            validation_warnings = []
            validation_errors = []

            # Use user-specific tools if provided (multi-tenant), otherwise fall back to registry
            user_tools = arguments.get("_user_tools", [])
            if user_tools:
                all_tools = user_tools
                logger.info(f"Using {len(all_tools)} user-specific tools for validation")
            else:
                all_tools = await self.registry.get_tools(refresh=False)
                logger.warning("No user tools provided, falling back to global registry for validation")

            valid_tool_names = {tool.get("name") for tool in all_tools}

            # Build additional lookup for server.tool_name format -> prefixed name
            # E.g., "grist-mcp.list_organizations" -> "grist_mcp__list_organizations"
            original_to_prefixed = {}
            for tool in all_tools:
                metadata = tool.get("metadata", {}) or tool.get("_metadata", {})
                original_name = metadata.get("original_tool_name", "")
                server_id = metadata.get("server_id", "")
                if original_name and server_id:
                    # Create lookup key: "server-id.original_name"
                    key = f"{server_id}.{original_name}"
                    original_to_prefixed[key] = tool.get("name")

            for step in steps:
                tool_name = step.get("tool")
                if not tool_name:
                    validation_errors.append(f"Step {step.get('step_id')} missing 'tool' field")
                elif tool_name not in valid_tool_names:
                    # Check if it's in server.tool format that can be resolved
                    if tool_name in original_to_prefixed:
                        # Rewrite the step to use the actual tool name
                        step["tool"] = original_to_prefixed[tool_name]
                        logger.info(f"Rewriting tool name: {tool_name} -> {step['tool']}")
                    else:
                        validation_warnings.append(
                            f"Tool '{tool_name}' in step {step.get('step_id')} not found in registry"
                        )

            # Create CompositionInfo
            from .composition_store import CompositionInfo

            composition = CompositionInfo(
                id=composition_id,
                name=name,
                description=description,
                organization_id=str(organization_id) if organization_id else None,
                created_by=str(user_id) if user_id else None,
                visibility="private",  # Default to private, can be changed later
                steps=steps,
                data_mappings=data_mappings,
                input_schema=input_schema,
                output_schema=output_schema,
                status="temporary",
                metadata={
                    "creation_method": "orchestrator"
                }
            )

            # Save as temporary composition (1 hour TTL by default)
            await self.composition_store.save_temporary(composition, ttl=3600)

            logger.info(
                f"✅ Composition created: {composition_id} "
                f"(steps: {len(steps)}, warnings: {len(validation_warnings)})"
            )

            return {
                "composition_id": composition_id,
                "name": name,
                "description": description,
                "status": "created",
                "note": "Composition saved as temporary (TTL: 1 hour). Use orchestrator_promote_composition to make it permanent.",
                "validation": {
                    "valid": len(validation_errors) == 0,
                    "warnings": validation_warnings,
                    "errors": validation_errors
                },
                "steps_count": len(steps),
                "ttl_seconds": 3600
            }

        except Exception as e:
            logger.error(f"Error creating composition: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed"
            }

    async def list_compositions(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        List available compositions.

        Args:
            arguments: {
                "filter": "search text",  # optional
                "status": "validated" | "temporary" | "production",  # optional
                "limit": 20,  # optional
                "offset": 0  # optional
            }

        Returns:
            {
                "compositions": [
                    {
                        "id": "comp_123",
                        "name": "Composition name",
                        "description": "...",
                        "status": "validated",
                        "tools_count": 3,
                        "avg_execution_time_ms": 2450
                    }
                ],
                "total": 42,
                "limit": 20,
                "offset": 0
            }
        """
        filter_text = arguments.get("filter")
        status_filter = arguments.get("status")
        limit = arguments.get("limit", 20)
        offset = arguments.get("offset", 0)

        try:
            # Load compositions from storage
            logger.info(f"Listing compositions - status: {status_filter}, filter: {filter_text}")

            compositions = await self.composition_store.list_all(status=status_filter)

            # Apply text filter if specified
            if filter_text:
                filter_lower = filter_text.lower()
                compositions = [
                    c for c in compositions
                    if filter_lower in c.name.lower() or filter_lower in c.description.lower()
                ]

            total = len(compositions)

            # Apply pagination
            compositions = compositions[offset:offset + limit]

            # Format for response
            formatted_compositions = [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "status": c.status,
                    "tools_count": len(c.steps),
                    "avg_execution_time_ms": c.metadata.get("avg_duration_ms", 0),
                    "execution_count": c.metadata.get("execution_count", 0),
                    "success_rate": c.metadata.get("success_rate", 0),
                    "created_at": c.created_at,
                    "updated_at": c.updated_at
                }
                for c in compositions
            ]

            logger.info(f"Found {total} compositions, returning {len(formatted_compositions)}")

            return {
                "compositions": formatted_compositions,
                "total": total,
                "limit": limit,
                "offset": offset
            }

        except Exception as e:
            logger.error(f"Error listing compositions: {e}", exc_info=True)
            return {
                "error": str(e),
                "compositions": [],
                "total": 0
            }

    async def get_composition(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed information about a composition.

        Args:
            arguments: {
                "composition_id": "comp_123",
                "include_metrics": true  # optional
            }

        Returns:
            {
                "id": "comp_123",
                "name": "Composition name",
                "description": "...",
                "steps": [...],
                "data_mappings": [...],
                "input_schema": {...},
                "output_schema": {...},
                "metrics": {  # if include_metrics=true
                    "executions_count": 42,
                    "success_rate": 0.95,
                    "avg_duration_ms": 2450,
                    "last_executed": "2025-01-15T10:30:00Z"
                }
            }
        """
        composition_id = arguments.get("composition_id")
        include_metrics = arguments.get("include_metrics", True)

        if not composition_id:
            return {
                "error": "Missing 'composition_id' parameter"
            }

        try:
            # Load composition from storage
            logger.info(f"Getting composition: {composition_id}")

            composition = await self.composition_store.get(composition_id)

            if not composition:
                return {
                    "error": f"Composition not found: {composition_id}",
                    "composition_id": composition_id
                }

            # Build response
            response = {
                "id": composition.id,
                "name": composition.name,
                "description": composition.description,
                "steps": composition.steps,
                "data_mappings": composition.data_mappings,
                "input_schema": composition.input_schema,
                "output_schema": composition.output_schema,
                "server_bindings": composition.server_bindings,
                "status": composition.status,
                "ttl": composition.ttl,
                "created_at": composition.created_at,
                "updated_at": composition.updated_at
            }

            # Add metrics if requested
            if include_metrics:
                response["metrics"] = {
                    "execution_count": composition.metadata.get("execution_count", 0),
                    "success_rate": composition.metadata.get("success_rate", 0),
                    "avg_duration_ms": composition.metadata.get("avg_duration_ms", 0),
                    "last_executed_at": composition.metadata.get("last_executed_at"),
                    "successes": composition.metadata.get("successes", 0),
                    "failures": composition.metadata.get("failures", 0)
                }

            logger.info(f"Composition {composition_id} retrieved successfully")

            return response

        except Exception as e:
            logger.error(f"Error getting composition: {e}", exc_info=True)
            return {
                "error": str(e),
                "composition_id": composition_id
            }
