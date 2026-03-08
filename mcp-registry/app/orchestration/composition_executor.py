"""
Composition Executor
====================

Executes multi-step workflow compositions with:
- DAG-based execution
- Data flow between steps
- Retry logic
- Timeout handling
- Error management
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..core.registry import MCPRegistry

logger = logging.getLogger("orchestration.executor")


@dataclass
class StepExecution:
    """Result of a single step execution."""
    step_id: str
    tool: str
    status: str  # success, failed, skipped
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    retries: int = 0


@dataclass
class CompositionExecution:
    """Complete composition execution result."""
    composition_id: str
    execution_id: str
    status: str  # success, failed, partial
    steps_executed: List[StepExecution] = field(default_factory=list)
    result: Any = None
    total_duration_ms: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""


class CompositionExecutor:
    """
    Executes workflow compositions.

    Handles:
    - Step-by-step execution
    - Parameter resolution (${step_X.output})
    - Parallel execution when possible
    - Retry on failure
    - Timeout management
    """

    def __init__(self, registry: MCPRegistry):
        """
        Initialize executor.

        Args:
            registry: MCP Registry for tool execution
        """
        self.registry = registry
        self.max_retries = 3
        self.default_timeout = 60  # seconds

        # Use singleton composition store (shared across all modules)
        from .composition_store import get_composition_store
        self.composition_store = get_composition_store()

    async def execute(
        self,
        composition_id: str,
        parameters: Dict[str, Any],
        execution_mode: str = "auto",
        stream_results: bool = False,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        user_server_pool: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a composition.

        Args:
            composition_id: ID of composition to execute
            parameters: Input parameters
            execution_mode: "sequential", "parallel", or "auto"
            stream_results: Whether to stream intermediate results
            user_id: Optional user ID for multi-tenant tool execution
            organization_id: Optional organization ID for multi-tenant tool execution
            user_server_pool: Optional UserServerPool for multi-tenant tool execution

        Returns:
            Execution result with status, output, and metrics
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        logger.info(f"Starting execution {execution_id} for composition {composition_id}")

        try:
            # Load composition
            composition = await self._load_composition(composition_id)

            if not composition:
                return {
                    "composition_id": composition_id,
                    "execution_id": execution_id,
                    "status": "failed",
                    "error": f"Composition not found: {composition_id}"
                }

            # Validate input parameters
            validation_errors = self._validate_input(composition, parameters)
            if validation_errors:
                return {
                    "composition_id": composition_id,
                    "execution_id": execution_id,
                    "status": "failed",
                    "errors": validation_errors
                }

            # Execute steps
            start_time = time.time()

            execution_context = {
                "parameters": parameters,
                "step_results": {},
                "execution_id": execution_id,
                "server_bindings": composition.get("server_bindings", {}),
                # Multi-tenant context
                "user_id": user_id,
                "organization_id": organization_id,
                "user_server_pool": user_server_pool
            }

            steps_executed = []

            for step in composition.get("steps", []):
                step_result = await self._execute_step(step, execution_context)
                steps_executed.append(step_result)

                # Store step result for future steps ONLY if successful
                if step_result.status == "success":
                    execution_context["step_results"][step.get("step_id")] = step_result.result
                else:
                    # Store None for failed steps to prevent error propagation
                    execution_context["step_results"][step.get("step_id")] = None

                if step_result.status == "failed":
                    # Check if we should continue or abort
                    if not step.get("optional", False):
                        break

            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)

            # Determine overall status
            failed_steps = [s for s in steps_executed if s.status == "failed"]
            success_steps = [s for s in steps_executed if s.status == "success"]

            if not failed_steps:
                overall_status = "success"
            elif success_steps:
                overall_status = "partial"
            else:
                overall_status = "failed"

            # Get final result (from last successful step)
            final_result = None
            if success_steps:
                final_result = success_steps[-1].result

            return {
                "composition_id": composition_id,
                "execution_id": execution_id,
                "status": overall_status,
                "result": final_result,
                "steps_executed": [
                    {
                        "step_id": s.step_id,
                        "tool": s.tool,
                        "status": s.status,
                        "duration_ms": s.duration_ms,
                        "result": s.result if s.status == "success" else None,
                        "error": s.error,
                        "retries": s.retries
                    }
                    for s in steps_executed
                ],
                "total_duration_ms": duration_ms,
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "errors": [s.error for s in failed_steps if s.error]
            }

        except Exception as e:
            logger.error(f"Error executing composition: {e}", exc_info=True)
            return {
                "composition_id": composition_id,
                "execution_id": execution_id,
                "status": "failed",
                "error": str(e),
                "started_at": started_at,
                "completed_at": datetime.now().isoformat()
            }

    async def execute_direct(
        self,
        composition: Dict[str, Any],
        parameters: Dict[str, Any],
        execution_mode: str = "auto",
        stream_results: bool = False,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        user_server_pool: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a composition directly from its definition.

        This allows executing compositions without storing them first.
        Useful for one-off workflows or testing.

        Args:
            composition: Composition definition dict with steps, name, etc.
            parameters: Input parameters
            execution_mode: "sequential", "parallel", or "auto"
            stream_results: Whether to stream intermediate results
            user_id: Optional user ID for multi-tenant tool execution
            organization_id: Optional organization ID for multi-tenant tool execution
            user_server_pool: Optional UserServerPool for multi-tenant tool execution

        Returns:
            Execution result with status, output, and metrics
        """
        execution_id = str(uuid.uuid4())
        composition_id = composition.get("id", f"direct_{uuid.uuid4().hex[:8]}")
        started_at = datetime.now().isoformat()

        logger.info(f"Starting direct execution {execution_id} for composition {composition_id}")

        try:
            # Validate input parameters
            validation_errors = self._validate_input(composition, parameters)
            if validation_errors:
                return {
                    "composition_id": composition_id,
                    "execution_id": execution_id,
                    "status": "failed",
                    "errors": validation_errors
                }

            # Execute steps
            start_time = time.time()

            execution_context = {
                "parameters": parameters,
                "step_results": {},
                "execution_id": execution_id,
                "server_bindings": composition.get("server_bindings", {}),
                # Multi-tenant context
                "user_id": user_id,
                "organization_id": organization_id,
                "user_server_pool": user_server_pool
            }

            steps_executed = []

            for step in composition.get("steps", []):
                step_result = await self._execute_step(step, execution_context)
                steps_executed.append(step_result)

                # Store step result for future steps ONLY if successful
                if step_result.status == "success":
                    execution_context["step_results"][step.get("step_id")] = step_result.result
                else:
                    # Store None for failed steps to prevent error propagation
                    execution_context["step_results"][step.get("step_id")] = None

                if step_result.status == "failed":
                    # Check if we should continue or abort
                    if not step.get("optional", False):
                        break

            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)

            # Determine overall status
            failed_steps = [s for s in steps_executed if s.status == "failed"]
            success_steps = [s for s in steps_executed if s.status == "success"]

            if not failed_steps:
                overall_status = "success"
            elif success_steps:
                overall_status = "partial"
            else:
                overall_status = "failed"

            # Get final result (from last successful step)
            final_result = None
            if success_steps:
                final_result = success_steps[-1].result

            result = {
                "composition_id": composition_id,
                "execution_id": execution_id,
                "status": overall_status,
                "result": final_result,
                "steps_executed": [
                    {
                        "step_id": s.step_id,
                        "tool": s.tool,
                        "status": s.status,
                        "duration_ms": s.duration_ms,
                        "result": s.result if s.status == "success" else None,
                        "error": s.error,
                        "retries": s.retries
                    }
                    for s in steps_executed
                ],
                "total_duration_ms": duration_ms,
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "errors": [s.error for s in failed_steps if s.error]
            }

            # Update composition stats if it has an ID
            if composition_id and composition_id.startswith("temp_"):
                try:
                    await self.composition_store.update_stats(composition_id, result)
                except Exception as e:
                    logger.warning(f"Could not update stats for {composition_id}: {e}")

            return result

        except Exception as e:
            logger.error(f"Error executing composition directly: {e}", exc_info=True)
            return {
                "composition_id": composition_id,
                "execution_id": execution_id,
                "status": "failed",
                "error": str(e),
                "started_at": started_at,
                "completed_at": datetime.now().isoformat()
            }

    async def _load_composition(self, composition_id: str) -> Optional[Dict[str, Any]]:
        """
        Load composition definition from storage.

        First checks the file-based store, then falls back to database
        for compositions created via the API.

        Args:
            composition_id: ID of the composition to load

        Returns:
            Composition dictionary or None if not found
        """
        # First, try file-based store (for compositions created via orchestrator)
        composition_info = await self.composition_store.get(composition_id)

        if composition_info:
            # Convert CompositionInfo to dict format expected by executor
            return composition_info.to_dict()

        # If not in file store, try database (for compositions created via API)
        try:
            from ..db.session import AsyncSessionLocal
            from ..services.composition_service import CompositionService
            from uuid import UUID

            # Try to parse as UUID (database compositions have UUID ids)
            try:
                comp_uuid = UUID(composition_id)
            except (ValueError, TypeError):
                logger.warning(f"Composition not found in file store and ID is not a valid UUID: {composition_id}")
                return None

            async with AsyncSessionLocal() as db:
                service = CompositionService(db)
                # Get composition from database (without strict org filtering for execution)
                from sqlalchemy import select
                from ..models.composition import Composition as CompositionModel

                stmt = select(CompositionModel).where(CompositionModel.id == comp_uuid)
                result = await db.execute(stmt)
                db_composition = result.scalar_one_or_none()

                if db_composition:
                    logger.info(f"Loaded composition {composition_id} from database")
                    # Convert DB model to dict format expected by executor
                    return {
                        "id": str(db_composition.id),
                        "name": db_composition.name,
                        "description": db_composition.description or "",
                        "steps": db_composition.steps or [],
                        "data_mappings": db_composition.data_mappings or [],
                        "input_schema": db_composition.input_schema or {},
                        "output_schema": db_composition.output_schema,
                        "server_bindings": db_composition.server_bindings or {},
                        "organization_id": str(db_composition.organization_id),
                        "created_by": str(db_composition.created_by),
                        "visibility": db_composition.visibility.value if hasattr(db_composition.visibility, 'value') else db_composition.visibility,
                        "force_org_credentials": db_composition.force_org_credentials,
                        "allowed_roles": db_composition.allowed_roles or [],
                        "status": db_composition.status,
                        "metadata": db_composition.extra_metadata or {}
                    }

        except Exception as e:
            logger.error(f"Error loading composition from database: {e}", exc_info=True)

        logger.warning(f"Composition not found: {composition_id}")
        return None

    def _validate_input(
        self,
        composition: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> List[str]:
        """
        Validate input parameters against composition schema.

        Returns list of validation errors (empty if valid).
        """
        errors = []

        input_schema = composition.get("input_schema", {})
        required_params = input_schema.get("required", [])

        # Check required parameters
        for param in required_params:
            if param not in parameters:
                errors.append(f"Missing required parameter: {param}")

        return errors

    async def _execute_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any]
    ) -> StepExecution:
        """
        Execute a single step in the composition.

        Handles:
        - Parameter resolution
        - Retry logic
        - Timeout
        """
        step_id = step.get("step_id")
        tool_name = step.get("tool")
        step_parameters = step.get("parameters", {})
        max_retries = step.get("retry_strategy", {}).get("max_retries", self.max_retries)
        timeout = step.get("timeout_seconds", self.default_timeout)

        logger.info(f"Executing step {step_id}: {tool_name}")

        start_time = time.time()
        retries = 0

        while retries <= max_retries:
            try:
                # Resolve parameters (substitute ${step_X.output} references)
                resolved_params = self._resolve_parameters(step_parameters, context)

                # Execute tool via registry
                result = await asyncio.wait_for(
                    self._execute_tool(tool_name, resolved_params, context),
                    timeout=timeout
                )

                duration_ms = int((time.time() - start_time) * 1000)

                # Check if result indicates an error (multiple detection methods)
                is_error = False
                error_msg = "Tool execution failed"

                if isinstance(result, dict):
                    # Method 1: Check isError flag
                    if result.get("isError"):
                        is_error = True
                        if "content" in result and len(result["content"]) > 0:
                            content = result["content"][0]
                            if isinstance(content, dict) and "text" in content:
                                error_msg = content["text"]

                    # Method 2: Check structuredContent.success === false
                    # Some tools return errors without setting isError
                    structured = result.get("structuredContent", {})
                    if isinstance(structured, dict) and structured.get("success") is False:
                        is_error = True
                        error_msg = structured.get("message", error_msg)

                if is_error:
                    logger.warning(
                        f"Step {step_id} failed with error: {error_msg} "
                        f"(duration: {duration_ms}ms, retries: {retries})"
                    )

                    return StepExecution(
                        step_id=step_id,
                        tool=tool_name,
                        status="failed",
                        error=error_msg,
                        duration_ms=duration_ms,
                        retries=retries
                    )

                logger.info(
                    f"Step {step_id} completed successfully in {duration_ms}ms "
                    f"(retries: {retries})"
                )

                return StepExecution(
                    step_id=step_id,
                    tool=tool_name,
                    status="success",
                    result=result,
                    duration_ms=duration_ms,
                    retries=retries
                )

            except asyncio.TimeoutError:
                logger.warning(f"Step {step_id} timed out after {timeout}s")

                retries += 1
                if retries > max_retries:
                    duration_ms = int((time.time() - start_time) * 1000)
                    return StepExecution(
                        step_id=step_id,
                        tool=tool_name,
                        status="failed",
                        error=f"Timeout after {timeout}s (retries: {retries})",
                        duration_ms=duration_ms,
                        retries=retries
                    )

                # Wait before retry
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error executing step {step_id}: {e}")

                retries += 1
                if retries > max_retries:
                    duration_ms = int((time.time() - start_time) * 1000)
                    return StepExecution(
                        step_id=step_id,
                        tool=tool_name,
                        status="failed",
                        error=str(e),
                        duration_ms=duration_ms,
                        retries=retries
                    )

                # Wait before retry
                await asyncio.sleep(1)

    def _resolve_parameters(
        self,
        parameters: Dict[str, Any],
        context: Dict[str, Any],
        iteration_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve parameter references with path navigation.

        Replaces ${step_X.path.to.value} with actual values from previous steps.
        Also replaces ${input.param_name} with input parameters.

        Supports:
        - Scalar extraction: ${step_1.result.id} → "abc123"
        - Wildcard extraction: ${step_1.items[*].id} → ["id1", "id2", ...]
        - Nested wildcards: ${step_1.workspaces[*].docs[*].id} → flattened list
        - Template/Map: {"_template": "...", "_map": {...}} → array of objects

        When a parameter value is EXACTLY a single reference (e.g., "${step_1.items[*].id}"),
        the resolved value preserves the original type (list, dict, etc.).
        When embedded in a string, complex types are JSON-encoded.

        Context Variables (available during _template/_map iteration):
        - ${_item}: Current iteration item
        - ${_parent}: Parent object in nested iteration
        - ${_root}: Original step result root
        - ${_index}: Current iteration index
        - ${_now}: ISO timestamp

        Examples:
            ${step_1.structuredContent.organizations[0].id}
            ${step_1.result.results[0].id}
            ${step_1.items[*].name}  → list of names
            ${input.workspace_id}
        """
        import re
        import json
        from datetime import datetime

        resolved = {}

        for key, value in parameters.items():
            # Skip special keys used for comments
            if key == "_comment":
                continue

            if isinstance(value, str):
                # Check for ${...} pattern
                matches = re.findall(r'\$\{([^}]+)\}', value)

                # Check if value is exactly one reference (preserve type)
                is_single_reference = (
                    len(matches) == 1 and
                    value == f"${{{matches[0]}}}"
                )

                for match in matches:
                    extracted_value = None

                    if match.startswith("step_"):
                        # Parse: step_1.structuredContent.organizations[0].id
                        parts = match.split(".", 1)  # ["step_1", "structuredContent..."]
                        step_id = parts[0].replace("step_", "")
                        step_result = context.get("step_results", {}).get(step_id)

                        if step_result is not None:
                            if len(parts) > 1:
                                # Navigate the path to extract specific value
                                extracted_value = self._extract_value_from_path(
                                    step_result,
                                    parts[1]
                                )
                            else:
                                # No path specified, use entire result
                                extracted_value = step_result

                    elif match.startswith("input."):
                        # Reference to input parameter
                        param_name = match.replace("input.", "")
                        extracted_value = context.get("parameters", {}).get(param_name)

                    elif match.startswith("_") and iteration_context:
                        # Iteration context variable
                        extracted_value = self._resolve_iteration_variable(
                            match, iteration_context
                        )

                    # Apply the extracted value
                    if extracted_value is not None:
                        if is_single_reference:
                            # Preserve original type (list, dict, etc.)
                            value = extracted_value
                        else:
                            # Embedded in string - convert to string representation
                            if isinstance(extracted_value, (list, dict)):
                                str_value = json.dumps(extracted_value)
                            else:
                                str_value = str(extracted_value)
                            value = value.replace(f"${{{match}}}", str_value)
                    else:
                        if not is_single_reference:
                            # Path navigation failed for embedded reference
                            value = value.replace(f"${{{match}}}", "null")

                resolved[key] = value

            elif isinstance(value, dict):
                # Check for _template/_map pattern
                if "_template" in value and "_map" in value:
                    resolved[key] = self._resolve_template_map(value, context)
                else:
                    # Recursively resolve nested dicts
                    resolved[key] = self._resolve_parameters(value, context, iteration_context)

            elif isinstance(value, list):
                # Recursively resolve list items
                resolved[key] = [
                    self._resolve_parameters({"_": item}, context, iteration_context).get("_", item)
                    if isinstance(item, (str, dict)) else item
                    for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    def _resolve_iteration_variable(
        self,
        var_name: str,
        iteration_context: Dict[str, Any]
    ) -> Any:
        """
        Resolve iteration context variables like _item, _parent, _root.

        Args:
            var_name: Variable name (e.g., "_item", "_parent.id", "_now")
            iteration_context: Current iteration context

        Returns:
            Resolved value or None
        """
        from datetime import datetime

        # Handle system variables
        if var_name == "_now":
            return datetime.utcnow().isoformat() + "Z"

        if var_name == "_index":
            return iteration_context.get("_index", 0)

        # Handle path variables like "_item.id" or "_parent.name"
        parts = var_name.split(".", 1)
        base_var = parts[0]

        base_value = iteration_context.get(base_var)

        if base_value is None:
            return None

        if len(parts) == 1:
            return base_value

        # Navigate the remaining path
        return self._extract_value_from_path_no_wildcard(base_value, parts[1])

    def _resolve_template_map(
        self,
        template_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Resolve _template/_map pattern to produce array of mapped objects.

        Syntax:
            {
                "_template": "${step_1.workspaces[*].docs[*]}",
                "_map": {
                    "source": "literal-value",
                    "doc_id": "${_item.id}",
                    "workspace_id": "${_parent.id}",
                    "synced_at": "${_now}"
                }
            }

        Args:
            template_config: Dict with _template and _map keys
            context: Execution context with step_results

        Returns:
            List of mapped objects
        """
        template_ref = template_config.get("_template", "")
        map_template = template_config.get("_map", {})

        # Parse the template reference to get items with parent context
        items_with_context = self._extract_with_parent_context(template_ref, context)

        if not items_with_context:
            return []

        results = []

        for idx, item_ctx in enumerate(items_with_context):
            # Build iteration context
            iteration_context = {
                "_item": item_ctx.get("_item"),
                "_parent": item_ctx.get("_parent"),
                "_root": item_ctx.get("_root"),
                "_index": idx
            }

            # Resolve the map template with iteration context
            mapped_obj = self._resolve_parameters(
                map_template.copy(),
                context,
                iteration_context
            )

            results.append(mapped_obj)

        return results

    def _extract_with_parent_context(
        self,
        template_ref: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract items from template reference while preserving parent context.

        For "${step_1.workspaces[*].docs[*]}", returns list of:
        {
            "_item": <doc object>,
            "_parent": <workspace object>,
            "_root": <step_1 result>
        }

        Args:
            template_ref: Template reference string (e.g., "${step_1.items[*]}")
            context: Execution context

        Returns:
            List of dicts with _item, _parent, _root keys
        """
        import re

        # Extract the reference content from ${...}
        match = re.match(r'\$\{([^}]+)\}', template_ref)
        if not match:
            return []

        ref_path = match.group(1)

        # Parse step reference
        if not ref_path.startswith("step_"):
            return []

        parts = ref_path.split(".", 1)
        step_id = parts[0].replace("step_", "")
        step_result = context.get("step_results", {}).get(step_id)

        if step_result is None:
            return []

        if len(parts) < 2:
            # No path, just return the step result as single item
            return [{"_item": step_result, "_parent": None, "_root": step_result}]

        path = parts[1]

        # Use recursive extraction with parent tracking
        return self._iterate_with_parent_tracking(step_result, path, step_result)

    def _iterate_with_parent_tracking(
        self,
        obj: Any,
        path: str,
        root: Any,
        parent: Any = None
    ) -> List[Dict[str, Any]]:
        """
        Iterate over path with wildcard, tracking parent context at each level.

        For path "workspaces[*].docs[*]":
        - First iterates over workspaces
        - For each workspace, iterates over docs
        - Each doc gets its parent workspace in _parent

        Args:
            obj: Current object to navigate
            path: Remaining path to navigate
            root: Original root object (step result)
            parent: Parent object from previous level

        Returns:
            List of {_item, _parent, _root} dicts
        """
        import re

        # Check if path contains wildcard
        wildcard_match = re.match(r'^(.*?)\[\*\](.*)$', path)

        if not wildcard_match:
            # No wildcard - extract final value
            if path:
                final_value = self._extract_value_from_path_no_wildcard(obj, path)
            else:
                final_value = obj

            if final_value is not None:
                return [{"_item": final_value, "_parent": parent, "_root": root}]
            return []

        prefix = wildcard_match.group(1)  # e.g., "workspaces" or "data.items"
        suffix = wildcard_match.group(2)  # e.g., ".docs[*]" or ".id"

        # Remove leading dot from suffix
        if suffix.startswith("."):
            suffix = suffix[1:]

        # Navigate to the array using prefix
        if prefix:
            array_obj = self._extract_value_from_path_no_wildcard(obj, prefix)
        else:
            array_obj = obj

        if not isinstance(array_obj, list):
            return []

        results = []

        for item in array_obj:
            if suffix and "[*]" in suffix:
                # More wildcards to process - recurse with current item as parent
                nested_results = self._iterate_with_parent_tracking(
                    item, suffix, root, parent=item
                )
                results.extend(nested_results)
            elif suffix:
                # No more wildcards - extract final value
                final_value = self._extract_value_from_path_no_wildcard(item, suffix)
                if final_value is not None:
                    results.append({
                        "_item": final_value,
                        "_parent": item,  # The containing object is the parent
                        "_root": root
                    })
            else:
                # No suffix - the item itself is what we want
                results.append({
                    "_item": item,
                    "_parent": parent,
                    "_root": root
                })

        return results

    def _extract_value_from_path(self, obj: Any, path: str) -> Any:
        """
        Extract value from nested object using dot notation, array indices, and wildcards.

        Supports:
        - Nested objects: "structuredContent.organizations"
        - Array indices: "organizations[0].id"
        - Deep paths: "result.results[0].workspaces[0].name"
        - Wildcard extraction: "organizations[*].id" → list of all ids
        - Nested wildcards: "workspaces[*].docs[*].id" → flattened list

        Examples:
            _extract_value_from_path(result, "organizations[0].id")
            _extract_value_from_path(result, "organizations[*].id")  # → ["id1", "id2", ...]
            _extract_value_from_path(result, "workspaces[*].docs[*].name")  # → flattened

        Args:
            obj: Source object (dict, list, or any nested structure)
            path: Navigation path using dot notation, array indices, and wildcards

        Returns:
            Extracted value, list of values for wildcards, or None if path fails
        """
        import re

        # Check if path contains wildcard - use recursive extraction
        if "[*]" in path:
            return self._extract_with_wildcard(obj, path)

        # Standard extraction without wildcards
        current = obj
        parts = path.split(".")

        for part in parts:
            if current is None:
                return None

            # Check for array index: "organizations[0]"
            array_match = re.match(r'(\w+)\[(\d+)\]', part)

            if array_match:
                field_name = array_match.group(1)
                index = int(array_match.group(2))

                # Navigate to field
                if isinstance(current, dict):
                    current = current.get(field_name)
                else:
                    return None

                # Navigate to array index
                if isinstance(current, list) and len(current) > index:
                    current = current[index]
                else:
                    return None
            else:
                # Simple field access
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    def _extract_with_wildcard(self, obj: Any, path: str) -> List[Any]:
        """
        Extract values using wildcard [*] notation with auto-flattening.

        Handles paths like:
        - "items[*].id" → extracts id from each item
        - "workspaces[*].docs[*].id" → extracts and flattens all doc ids
        - "workspaces[0].docs[*].id" → first workspace, all docs (mixed index/wildcard)

        Args:
            obj: Source object
            path: Path containing one or more [*] wildcards

        Returns:
            List of extracted values (flattened if nested wildcards)
        """
        import re

        # Split path at first [*] occurrence (but handle preceding numeric indices)
        # Pattern: match everything up to and including [*], capturing prefix and suffix
        wildcard_match = re.match(r'^(.*?)\[\*\](.*)$', path)

        if not wildcard_match:
            # No wildcard found - shouldn't happen if called correctly
            result = self._extract_value_from_path_no_wildcard(obj, path)
            return [result] if result is not None else []

        prefix = wildcard_match.group(1)  # e.g., "items", "data.items", "workspaces[0].docs"
        suffix = wildcard_match.group(2)  # e.g., ".id" or ".docs[*].name"

        # Remove leading dot from suffix if present
        if suffix.startswith("."):
            suffix = suffix[1:]

        # Navigate to the array using prefix (use non-wildcard extraction for prefix)
        if prefix:
            array_obj = self._extract_value_from_path_no_wildcard(obj, prefix)
        else:
            array_obj = obj

        if not isinstance(array_obj, list):
            return []

        results = []

        for item in array_obj:
            if suffix:
                # Continue extraction with remaining path (may contain more wildcards)
                if "[*]" in suffix:
                    # Recursive wildcard extraction
                    extracted = self._extract_with_wildcard(item, suffix)
                else:
                    # Standard extraction for remaining path
                    extracted = self._extract_value_from_path_no_wildcard(item, suffix)

                if extracted is not None:
                    # Auto-flatten if result is a list (nested wildcard produced it)
                    if isinstance(extracted, list):
                        results.extend(extracted)
                    else:
                        results.append(extracted)
            else:
                # No suffix means we want the items themselves
                results.append(item)

        return results

    def _extract_value_from_path_no_wildcard(self, obj: Any, path: str) -> Any:
        """
        Extract value from path WITHOUT wildcard support.

        Internal method to avoid recursion when processing mixed paths.
        """
        import re

        current = obj
        parts = path.split(".")

        for part in parts:
            if current is None:
                return None

            # Check for array index: "organizations[0]"
            array_match = re.match(r'(\w+)\[(\d+)\]', part)

            if array_match:
                field_name = array_match.group(1)
                index = int(array_match.group(2))

                # Navigate to field
                if isinstance(current, dict):
                    current = current.get(field_name)
                else:
                    return None

                # Navigate to array index
                if isinstance(current, list) and len(current) > index:
                    current = current[index]
                else:
                    return None
            else:
                # Simple field access
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    def _resolve_tool_direct(
        self,
        tool_name: str,
        server_bindings: Dict[str, str]
    ) -> Optional[tuple]:
        """
        Resolve server_uuid and original tool name directly from server_bindings.

        Compositions reference tools as "server_id.tool_name" and provide
        server_bindings mapping server_id → server_uuid. This allows direct
        execution without tool discovery — the same fast path used by MCP clients.

        Args:
            tool_name: Tool reference (e.g., "grist-mcp.list_organizations")
            server_bindings: Mapping of server_id → server_uuid

        Returns:
            Tuple of (server_uuid, original_tool_name) or None if not resolvable
        """
        if not server_bindings:
            return None

        # Format: "server_id.tool_name" (e.g., "grist-mcp.list_organizations")
        if "." in tool_name:
            parts = tool_name.split(".", 1)
            if len(parts) == 2:
                server_id_str = parts[0]
                original_name = parts[1]

                # Direct lookup in server_bindings
                server_uuid = server_bindings.get(server_id_str)
                if server_uuid:
                    return (server_uuid, original_name)

        return None

    async def _resolve_server_from_prefix(
        self,
        tool_name: str,
        user_id,
        organization_id,
        user_server_pool,
        context: Dict[str, Any]
    ) -> Optional[tuple]:
        """
        Resolve server UUID and original tool name from prefixed tool name.

        Tool names in compositions use the format: ServerPrefix__tool_name
        (e.g., "Hostinger__VPS_getVirtualMachinesV1").

        The prefix is the server display name sanitized with:
            re.sub(r'[^a-zA-Z0-9_]', '_', name) + collapse + strip

        This method builds a prefix → server_id cache (once per execution)
        by querying the database, then resolves directly.

        Returns:
            Tuple of (server_uuid_str, original_tool_name) or None
        """
        import re
        from uuid import UUID

        if "__" not in tool_name:
            return None

        prefix, original_name = tool_name.split("__", 1)

        # Check cached prefix map
        prefix_cache = context.get("_prefix_to_server")

        if prefix_cache is None:
            # Build cache from DB — query all servers in this organization
            prefix_cache = {}
            try:
                from sqlalchemy import select
                from ..db.database import async_session_maker
                from ..models.mcp_server import MCPServer

                async with async_session_maker() as db:
                    result = await db.execute(
                        select(MCPServer).where(
                            MCPServer.organization_id == UUID(str(organization_id))
                        )
                    )
                    for server in result.scalars():
                        display_name = server.name
                        if hasattr(server, 'alias') and server.alias:
                            display_name = f"{server.name} ({server.alias})"
                        safe = re.sub(r'[^a-zA-Z0-9_]', '_', display_name)
                        safe = re.sub(r'_+', '_', safe).strip('_')
                        prefix_cache[safe] = str(server.id)
            except Exception as e:
                logger.error(f"Error building prefix cache: {e}")

            context["_prefix_to_server"] = prefix_cache
            logger.info(f"Built prefix cache: {len(prefix_cache)} servers mapped")

        server_uuid = prefix_cache.get(prefix)
        if server_uuid:
            return (server_uuid, original_name)

        return None

    async def _execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute a tool via the registry or UserServerPool.

        Uses the same direct execution path as MCP clients — only starts
        the specific server needed for each tool, not all servers.

        Resolution order:
        1. server_bindings (dot notation: server_id.tool_name)
        2. Prefix resolution (double underscore: ServerPrefix__tool_name)
           → DB lookup for server UUID → start ONLY that server → execute
        3. Discovery fallback (legacy: start all servers, search through tools)
        """
        from uuid import UUID

        # Extract multi-tenant context
        user_id = context.get("user_id") if context else None
        organization_id = context.get("organization_id") if context else None
        user_server_pool = context.get("user_server_pool") if context else None
        server_bindings = context.get("server_bindings", {}) if context else {}

        logger.info(f"_execute_tool: {tool_name} (user={user_id}, bindings={len(server_bindings)})")

        # =====================================================================
        # PATH 1: Direct resolution via server_bindings (dot notation)
        # =====================================================================
        if user_id and organization_id and user_server_pool:
            direct = self._resolve_tool_direct(tool_name, server_bindings)
            if direct:
                server_uuid, original_tool_name = direct
                logger.info(
                    f"Direct execution (bindings): {tool_name} → "
                    f"server={server_uuid}, tool={original_tool_name}"
                )
                result = await user_server_pool.execute_tool(
                    user_id=UUID(str(user_id)),
                    server_id=UUID(str(server_uuid)),
                    tool_name=original_tool_name,
                    parameters=parameters,
                    organization_id=UUID(str(organization_id))
                )
                return result

        # =====================================================================
        # PATH 2: Prefix resolution (ServerPrefix__tool_name)
        # Like the MCP client: resolve server from tool name, start ONLY that
        # server, execute directly. No ensure_configured_servers_started.
        # =====================================================================
        if user_id and organization_id and user_server_pool:
            resolved = await self._resolve_server_from_prefix(
                tool_name, user_id, organization_id, user_server_pool, context
            )
            if resolved:
                server_uuid, original_tool_name = resolved
                logger.info(
                    f"Direct execution (prefix): {tool_name} → "
                    f"server={server_uuid}, tool={original_tool_name}"
                )

                # Start ONLY this server (skip_rebuild: composition doesn't need semantic index)
                await user_server_pool.get_or_start_server(
                    user_id=UUID(str(user_id)),
                    server_id=UUID(str(server_uuid)),
                    organization_id=UUID(str(organization_id)),
                    skip_rebuild=True
                )

                result = await user_server_pool.execute_tool(
                    user_id=UUID(str(user_id)),
                    server_id=UUID(str(server_uuid)),
                    tool_name=original_tool_name,
                    parameters=parameters,
                    organization_id=UUID(str(organization_id))
                )
                return result

        # =====================================================================
        # PATH 3: Discovery fallback (legacy)
        # Only used when neither bindings nor prefix resolve the tool.
        # =====================================================================
        logger.info(f"Fallback: discovery-based resolution for {tool_name}")

        if user_id and organization_id and user_server_pool:
            all_tools = context.get("_cached_tools") if context else None

            if all_tools is None:
                try:
                    await user_server_pool.ensure_configured_servers_started(
                        UUID(str(user_id)),
                        UUID(str(organization_id))
                    )
                except Exception as e:
                    logger.warning(f"Error ensuring servers started: {e}")

                all_tools = await user_server_pool.get_user_tools(
                    UUID(str(user_id)),
                    UUID(str(organization_id)),
                    include_hidden=True
                )
                if context is not None:
                    context["_cached_tools"] = all_tools

                logger.info(f"Discovered {len(all_tools)} tools (cached for execution)")
            else:
                logger.info(f"Using cached tools ({len(all_tools)} tools)")
        else:
            logger.warning(f"Fallback to global registry (no user context)")
            all_tools = await self.registry.get_tools(refresh=False)

        tool_info = None

        # Try exact name match first
        for tool in all_tools:
            if tool.get("name") == tool_name:
                tool_info = tool
                break

        # If not found, try parsing server_id.tool_name format
        if not tool_info:
            if "." in tool_name:
                parts = tool_name.split(".", 1)
                if len(parts) == 2:
                    server_prefix = parts[0].replace("-", "_")
                    original_name = parts[1]
                    logger.info(f"Parsing composition tool: prefix={server_prefix}, name={original_name}")

                    expected_prefixed = f"{server_prefix}__{original_name}"
                    for tool in all_tools:
                        if tool.get("name") == expected_prefixed:
                            tool_info = tool
                            break

                    if not tool_info:
                        for tool in all_tools:
                            metadata = tool.get("metadata", {}) or tool.get("_metadata", {})
                            tool_original = metadata.get("original_tool_name", "")
                            tool_server_id = metadata.get("server_id", "")
                            tool_server_uuid = metadata.get("server_uuid", "")
                            tool_server_normalized = tool_server_id.replace("-", "_")

                            if tool_original == original_name:
                                if server_prefix in tool_server_normalized:
                                    tool_info = tool
                                    break
                                if parts[0] == tool_server_uuid:
                                    tool_info = tool
                                    break

            if not tool_info and "__" not in tool_name:
                for tool in all_tools:
                    metadata = tool.get("metadata", {}) or tool.get("_metadata", {})
                    tool_original = metadata.get("original_tool_name", "")
                    if tool_original == tool_name:
                        tool_info = tool
                        break

        if not tool_info:
            logger.error(f"Tool not found: {tool_name}. Available: {[t.get('name') for t in all_tools[:10]]}")
            raise ValueError(f"Tool not found: {tool_name}")

        server_id = (
            tool_info.get("server_id")
            or tool_info.get("_server_id")
            or (tool_info.get("metadata", {}) or {}).get("server_id")
            or (tool_info.get("server_info", {}) or {}).get("id")
        )

        if not server_id:
            tool_full_id = tool_info.get("id", "")
            if "." in tool_full_id:
                server_id = tool_full_id.split(".", 1)[0]

        if not server_id:
            raise ValueError(f"No server_id found for tool: {tool_name}")

        metadata = tool_info.get("metadata", {})
        original_tool_name = metadata.get("original_tool_name", tool_info.get("name", tool_name))

        actual_server_id = server_bindings.get(server_id, server_id)

        if user_id and organization_id and user_server_pool:
            logger.info(f"Executing via UserServerPool: {tool_name} (server: {actual_server_id})")
            result = await user_server_pool.execute_tool(
                user_id=UUID(str(user_id)),
                server_id=UUID(str(actual_server_id)),
                tool_name=original_tool_name,
                parameters=parameters,
                organization_id=UUID(str(organization_id))
            )
            return result

        tool_id = f"{server_id}.{original_tool_name}"
        logger.info(f"Executing via registry: {tool_name} (server: {actual_server_id})")
        result = await self.registry.execute_tool(
            server_id=actual_server_id,
            tool_id=tool_id,
            parameters=parameters
        )
        return result
