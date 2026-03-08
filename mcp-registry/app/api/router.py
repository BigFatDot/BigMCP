"""
API routes for MCP Registry.
"""

import logging
import os
import json
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Dict, Any, Optional
import time

from ..config import settings
from ..dependencies import get_registry
from .models import (
    ServerInfo,
    ToolInfo,
    SearchQuery,
    ExecuteToolRequest,
    ErrorResponse,
    ApiInfo
)

# Logging configuration
logger = logging.getLogger("mcp_registry.api")

# Create FastAPI router
router = APIRouter(tags=["MCP Registry"])

# Get the shared registry instance
registry = get_registry()

# Configuration LLM API (compatible with Mistral, OpenAI, etc.)
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.mistral.ai/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral-small-latest")

@router.get("/api/status", response_model=Dict[str, Any])
async def get_api_status():
    """Retrieve API status."""
    return {
        "status": "ok",
        "version": settings.app.version,
        "servers_count": len(registry.servers),
        "tools_count": len(registry.tools)
    }

@router.get("/api/servers", response_model=List[ServerInfo])
@router.get("/servers", response_model=List[ServerInfo])
async def get_servers():
    """
    Retrieve list of available MCP servers.
    """
    try:
        servers = await registry.get_servers()
        return servers
    except Exception as e:
        logger.exception(f"Error retrieving servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/tools", response_model=List[ToolInfo])
async def get_tools_api(refresh: bool = Query(False, description="Force refresh")):
    """
    Retrieve list of all available tools.

    - **refresh**: Force server refresh
    """
    try:
        tools = await registry.get_all_tools(refresh=refresh)
        return tools
    except Exception as e:
        logger.exception(f"Error retrieving tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/tools/{tool_id}", response_model=Optional[ToolInfo])
@router.get("/tools/{tool_id}", response_model=Optional[ToolInfo])
async def get_tool(tool_id: str):
    """
    Retrieve tool details by identifier.

    - **tool_id**: Complete tool identifier (server_id:tool_name)
    """
    try:
        tool = await registry.get_tool_by_id(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
        return tool
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving tool {tool_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/search", response_model=List[ToolInfo])
@router.post("/search", response_model=List[ToolInfo])
async def search_tools(query: SearchQuery):
    """
    Search tools by semantic query.

    - **query**: Query text
    - **limit**: Maximum number of tools to return
    """
    try:
        tools = await registry.get_tools_for_query(query.query, query.limit)
        return tools
    except Exception as e:
        logger.exception(f"Error searching tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute", response_model=Dict[str, Any])
@router.post("/execute", response_model=Dict[str, Any])
async def execute_tool(request: ExecuteToolRequest):
    """
    Execute a tool on an MCP server.

    - **server_id**: MCP server identifier
    - **tool_id**: Tool identifier
    - **parameters**: Parameters to pass to the tool
    """
    try:
        result = await registry.execute_tool(
            server_id=request.server_id,
            tool_id=request.tool_id,
            parameters=request.parameters
        )

        if "error" in result:
            logger.error(f"Error executing tool: {result['error']}")
            raise HTTPException(
                status_code=400,
                detail=result.get("message", result["error"])
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error executing tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/analyze")
async def analyze_intent(query: Dict[str, Any] = Body(...)):
    """
    Analyze user message intent and recommend relevant tools.

    This route uses the LLM API to analyze user intent
    and the MCP Registry to find matching tools.

    Args:
        query: Request containing the message to analyze

    Returns:
        Intent analysis with recommended tools
    """
    message = query.get("message", "")
    sender = query.get("sender", "")

    logger.info(f"Intent analysis for message: {message[:50]}...")

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        # 1. Determine query complexity to adjust number of tools
        # More complex queries may need more tools for composition
        message_words = len(message.split())

        # Number of tools to retrieve based on query complexity
        # For simple query, 2-3 tools suffice; for complex query, up to 5
        tools_limit = min(3 + message_words // 10, 5)  # Between 3 and 5 tools depending on complexity

        # 1. Search for relevant tools for the message with integrated reranking
        relevant_tools = await registry.search_tools(message, limit=tools_limit)

        # Convert tools to dictionaries if they are objects
        tools_dicts = []
        for tool in relevant_tools:
            if hasattr(tool, 'dict'):
                # If it's an object with a dict() method, call it to convert to dictionary
                tools_dicts.append(tool.dict())
            elif isinstance(tool, dict):
                # If it's already a dictionary, use it as is
                tools_dicts.append(tool)
            else:
                # Otherwise, try to convert to dictionary (fallback)
                tools_dicts.append(vars(tool) if hasattr(tool, "__dict__") else {"id": str(tool)})
        
        # Use dictionaries for subsequent processing
        relevant_tools = tools_dicts

        # 2. Format tool descriptions for LLM
        tools_descriptions = []
        for tool in relevant_tools:
            # Check if tool has required fields
            name = tool.get("name", "")
            description = tool.get("description", "")
            tool_id = tool.get("id", "")

            if name and tool_id:
                params_info = ""
                params = tool.get("parameters", {})

                # Extract parameter information if available
                if params and isinstance(params, dict) and "properties" in params:
                    properties = params.get("properties", {})
                    params_info = ", ".join([
                        f"{name}: {prop.get('description', '')}"
                        for name, prop in properties.items()
                    ])

                tool_desc = f"- {name} (id: {tool_id}): {description}"
                if params_info:
                    tool_desc += f". Parameters: {params_info}"

                tools_descriptions.append(tool_desc)

        # 3. Analyze intent with LLM API if key is available
        intent_analysis = {}

        if LLM_API_KEY:
            try:
                headers = {
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json"
                }

                tools_context = "\n".join(tools_descriptions) if tools_descriptions else "No tool available"

                # General prompt for all types of MCP tools
                prompt = f"""
                Analyze the user's intent and identify if one of the available tools can fulfill their request.

                Here are the available tools:
                {tools_context}

                User message: "{message}"

                If one of the tools above can help fulfill the request, select it and identify the necessary parameters.
                For tools that require executing multiple actions or calling multiple tools, you can simply identify the first tool needed.

                Respond in JSON format with:
                1. "intent": the type of intent detected (e.g., "query_data", "list_resources", "search", etc.)
                2. "confidence": confidence level (0 to 1)
                3. "requires_tool": boolean indicating if a tool is needed
                4. "tool_id": the recommended tool ID (or null if none)
                5. "tool_args": the recommended arguments for the tool (object)
                6. "rationale": explanation of your reasoning
                """

                # Prepare request for LLM API
                llm_request = {
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are an intent analysis assistant. Respond only in JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2
                }

                # Log request (with token masking)
                masked_headers = headers.copy()
                masked_headers["Authorization"] = "Bearer [MASKED]"
                chat_url = f"{LLM_API_URL}/chat/completions" if "/v1" in LLM_API_URL else f"{LLM_API_URL}/v1/chat/completions"
                logger.debug(f"Request sent to LLM API: URL={chat_url}, Headers={masked_headers}, Body={json.dumps(llm_request)}")

                # Call LLM API to analyze intent
                response = requests.post(
                    chat_url,
                    headers=headers,
                    json=llm_request
                )

                if response.status_code == 200:
                    # Extract LLM API response
                    llm_response = response.json()
                    answer_text = llm_response.get("choices", [{}])[0].get("message", {}).get("content", "")

                    # Log response
                    logger.debug(f"Response received from LLM API: {json.dumps(llm_response)}")

                    # Try to parse response as JSON
                    try:
                        # Extract only JSON part if response contains additional text
                        json_str = answer_text
                        if "```json" in answer_text:
                            json_str = answer_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in answer_text:
                            json_str = answer_text.split("```")[1].strip()

                        intent_analysis = json.loads(json_str)
                        logger.info(f"Intent analysis successful: {intent_analysis.get('intent')}")
                    except json.JSONDecodeError:
                        logger.error(f"Unable to parse JSON response: {answer_text}")
                        # Provide default analysis
                        intent_analysis = {
                            "intent": "unknown",
                            "confidence": 0.0,
                            "requires_tool": False,
                            "error": "JSON parsing error",
                            "raw_response": answer_text
                        }
                else:
                    logger.error(f"Error calling LLM API: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Exception during intent analysis: {str(e)}")
        
        # 4. If LLM analysis failed or unavailable, do simplified analysis
        if not intent_analysis:
            # Simplified analysis based on found tools
            if relevant_tools:
                top_tool = relevant_tools[0]
                score = top_tool.get("similarity_score", 0)

                intent_analysis = {
                    "intent": "tool_request",
                    "confidence": min(score, 0.95),  # Limit confidence to 0.95 max
                    "requires_tool": True,
                    "tool_id": top_tool.get("id"),
                    "server_id": top_tool.get("server_id"),
                    "tool_args": {},
                    "rationale": f"Tool '{top_tool.get('name')}' seems to match the user's request"
                }
            else:
                intent_analysis = {
                    "intent": None,
                    "confidence": 0.0,
                    "requires_tool": False,
                    "tool_id": None,
                    "rationale": "No tool matches this request"
                }

        # 5. Build final response
        response = {
            "intent": intent_analysis.get("intent"),
            "confidence": intent_analysis.get("confidence", 0.0),
            "requires_tool": intent_analysis.get("requires_tool", False),
            "tool_id": intent_analysis.get("tool_id"),
            "server_id": intent_analysis.get("server_id", None),
            "tool_args": intent_analysis.get("tool_args", {}),
            "tools": relevant_tools[:3],  # Include top 3 tools
            "rationale": intent_analysis.get("rationale", "")
        }

        return response

    except Exception as e:
        logger.error(f"Error during intent analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during intent analysis: {str(e)}")

# Aliases for other intent analysis endpoints
@router.post("/intent/analyze")
async def intent_analyze_alias(query: Dict[str, Any] = Body(...)):
    """Alias for /api/analyze"""
    return await analyze_intent(query)

@router.post("/api/intent")
async def api_intent_alias(query: Dict[str, Any] = Body(...)):
    """Alias for /api/analyze"""
    return await analyze_intent(query)

# ============================================================================
# ORCHESTRATION ENDPOINTS
# ============================================================================

@router.post("/api/orchestrate")
async def orchestrate_workflow(request: Dict[str, Any] = Body(...)):
    """
    Unified endpoint for complete orchestration: analysis + execution.

    Takes a natural language request, analyzes intent,
    proposes a workflow, and optionally executes it.

    Args:
        request: {
            "query": "Natural language request",
            "parameters": {...},  # Optional parameters
            "execute": true,  # If true, execute composition directly
            "context": {...},  # Optional context
            "server_bindings": {...}  # Optional: {server_id: server_uuid}
        }

    Returns:
        {
            "analysis": {...},  # Intent analysis result
            "execution": {...}  # Execution result (if execute=true)
        }
    """
    query = request.get("query")
    parameters = request.get("parameters", {})
    should_execute = request.get("execute", False)
    context = request.get("context", {})
    server_bindings = request.get("server_bindings", {})

    if not query:
        raise HTTPException(status_code=400, detail="Missing 'query' parameter")

    try:
        # Import orchestration tools
        from ..orchestration.tools import OrchestrationTools
        orchestration_tools = OrchestrationTools(registry)

        # Step 1: Analyze intent
        logger.info(f"🎯 Orchestrating query: {query}")
        analysis = await orchestration_tools.analyze_intent({
            "query": query,
            "context": context
        })

        response = {
            "query": query,
            "analysis": analysis
        }

        # Step 2: Execute if requested
        if should_execute and analysis.get("proposed_composition"):
            logger.info(f"⚡ Executing composition: {analysis['proposed_composition'].get('id')}")

            # Add server_bindings to composition if provided
            composition = analysis["proposed_composition"]
            if server_bindings:
                composition["server_bindings"] = server_bindings
                logger.info(f"📌 Using server_bindings: {server_bindings}")

            execution = await orchestration_tools.execute_composition({
                "composition": composition,
                "parameters": parameters
            })

            response["execution"] = execution
            response["status"] = execution.get("status")
        else:
            response["status"] = "analyzed"
            if not analysis.get("proposed_composition"):
                response["message"] = "No composition could be proposed"

        logger.info(f"✅ Orchestration complete: {response.get('status')}")
        return response

    except Exception as e:
        logger.error(f"Error during orchestration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/compositions")
async def list_compositions(
    status: Optional[str] = Query(None, description="Filter by status (temporary|validated|production)"),
    filter: Optional[str] = Query(None, description="Search text filter"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all available compositions.

    Returns:
        {
            "compositions": [...],
            "total": 42,
            "limit": 20,
            "offset": 0
        }
    """
    try:
        from ..orchestration.tools import OrchestrationTools
        orchestration_tools = OrchestrationTools(registry)

        result = await orchestration_tools.list_compositions({
            "status": status,
            "filter": filter,
            "limit": limit,
            "offset": offset
        })

        return result

    except Exception as e:
        logger.error(f"Error listing compositions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/compositions/{composition_id}")
async def get_composition(
    composition_id: str,
    include_metrics: bool = Query(True, description="Include execution metrics")
):
    """
    Retrieve details of a specific composition.

    Returns:
        Composition details with steps, schemas, and metrics
    """
    try:
        from ..orchestration.tools import OrchestrationTools
        orchestration_tools = OrchestrationTools(registry)

        result = await orchestration_tools.get_composition({
            "composition_id": composition_id,
            "include_metrics": include_metrics
        })

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting composition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/compositions/{composition_id}/execute")
async def execute_composition(
    composition_id: str,
    request: Dict[str, Any] = Body(...)
):
    """
    Execute a stored composition.

    Args:
        composition_id: Composition ID
        request: {
            "parameters": {...},  # Input parameters
            "execution_mode": "auto"  # optional
        }

    Returns:
        Execution result with status, steps, and output
    """
    parameters = request.get("parameters", {})
    execution_mode = request.get("execution_mode", "auto")

    try:
        from ..orchestration.tools import OrchestrationTools
        orchestration_tools = OrchestrationTools(registry)

        result = await orchestration_tools.execute_composition({
            "composition_id": composition_id,
            "parameters": parameters,
            "execution_mode": execution_mode
        })

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing composition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/compositions/{composition_id}/promote")
async def promote_composition(
    composition_id: str,
    request: Dict[str, Any] = Body(...)
):
    """
    Promote a composition in its lifecycle.

    Allows progressing a composition:
    - temporary → validated
    - validated → production

    Args:
        composition_id: Composition ID
        request: {
            "target_status": "validated" | "production"  # Target status
        }

    Returns:
        Promoted composition with its new status
    """
    target_status = request.get("target_status", "validated")

    # Target status validation
    if target_status not in ["validated", "production"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_status: {target_status}. Must be 'validated' or 'production'"
        )

    try:
        from ..orchestration.composition_store import get_composition_store
        composition_store = get_composition_store()

        # Retrieve current composition
        current_comp = await composition_store.get(composition_id)
        if not current_comp:
            raise HTTPException(
                status_code=404,
                detail=f"Composition not found: {composition_id}"
            )

        current_status = current_comp.status

        # Verify valid transitions
        valid_transitions = {
            "temporary": ["validated"],
            "validated": ["production"]
        }

        if target_status not in valid_transitions.get(current_status, []):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transition: {current_status} → {target_status}. "
                       f"Valid transitions from {current_status}: {valid_transitions.get(current_status, [])}"
            )

        # Promote
        promoted = await composition_store.promote_to_permanent(
            composition_id=composition_id,
            new_status=target_status
        )

        if not promoted:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to promote composition {composition_id}"
            )

        logger.info(f"✅ Composition {composition_id} promoted: {current_status} → {target_status}")

        return {
            "composition_id": composition_id,
            "previous_status": current_status,
            "new_status": target_status,
            "composition": promoted.to_dict(),
            "message": f"Composition successfully promoted to {target_status}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error promoting composition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint to verify service is working
@router.get("/api/ping")
async def api_ping():
    """Verify service is working."""
    return {"status": "ok", "timestamp": time.time()} 