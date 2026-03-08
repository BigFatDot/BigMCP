"""
Tool Binding Service - Context-specific tool configuration and execution.

Handles creating, managing, and executing tool bindings with
pre-filled and locked parameters.
"""

import asyncio
import json
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tool import Tool, ToolBinding
from ..models.context import Context
from ..models.mcp_server import MCPServer, ServerStatus
from ..models.organization import Organization


logger = logging.getLogger(__name__)


class ToolBindingService:
    """
    Service for managing tool bindings and execution.

    Responsibilities:
    - Create context-specific tool bindings
    - Merge default and user parameters
    - Enforce locked parameters
    - Execute tool bindings via MCP servers
    - Validate parameters against schemas
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_binding(
        self,
        organization_id: UUID,
        context_id: UUID,
        tool_id: UUID,
        binding_name: str,
        default_parameters: Optional[Dict[str, Any]] = None,
        locked_parameters: Optional[List[str]] = None,
        description: Optional[str] = None,
        custom_validation: Optional[Dict[str, Any]] = None,
        created_by: Optional[UUID] = None
    ) -> ToolBinding:
        """
        Create a new tool binding for a context.

        Args:
            organization_id: Organization UUID
            context_id: Context UUID
            tool_id: Tool UUID
            binding_name: User-friendly name for binding
            default_parameters: Pre-filled parameters
            locked_parameters: Parameters that cannot be overridden
            description: Optional description
            custom_validation: Additional validation rules
            created_by: User who created the binding

        Returns:
            Created ToolBinding instance

        Raises:
            ValueError: If binding_name already exists in context or tool not found
        """
        # Check if binding_name already exists in context
        stmt = select(ToolBinding).where(
            ToolBinding.context_id == context_id,
            ToolBinding.binding_name == binding_name
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Binding '{binding_name}' already exists in this context")

        # Verify tool exists and belongs to organization
        tool_stmt = select(Tool).where(Tool.id == tool_id)
        tool_result = await self.db.execute(tool_stmt)
        tool = tool_result.scalar_one_or_none()

        if not tool:
            raise ValueError(f"Tool {tool_id} not found")

        if tool.organization_id != organization_id:
            raise ValueError("Tool does not belong to this organization")

        # Verify context exists and belongs to organization
        context_stmt = select(Context).where(Context.id == context_id)
        context_result = await self.db.execute(context_stmt)
        context = context_result.scalar_one_or_none()

        if not context:
            raise ValueError(f"Context {context_id} not found")

        if context.organization_id != organization_id:
            raise ValueError("Context does not belong to this organization")

        # Check organization limits
        org_stmt = select(Organization).where(Organization.id == organization_id)
        org_result = await self.db.execute(org_stmt)
        org = org_result.scalar_one_or_none()

        if org:
            count_stmt = select(ToolBinding).where(
                ToolBinding.organization_id == organization_id
            )
            count_result = await self.db.execute(count_stmt)
            existing_count = len(count_result.scalars().all())

            if existing_count >= org.max_tool_bindings:
                raise ValueError(
                    f"Organization has reached max tool bindings limit ({org.max_tool_bindings})"
                )

        # Validate default_parameters against tool schema
        if default_parameters:
            self._validate_parameters(default_parameters, tool.parameters_schema)

        # Validate locked_parameters exist in schema
        if locked_parameters:
            schema_params = tool.parameters_schema.get("properties", {}).keys()
            for locked_param in locked_parameters:
                if locked_param not in schema_params:
                    raise ValueError(
                        f"Locked parameter '{locked_param}' not in tool schema"
                    )

        # Create binding
        binding = ToolBinding(
            organization_id=organization_id,
            context_id=context_id,
            tool_id=tool_id,
            binding_name=binding_name,
            description=description,
            default_parameters=default_parameters or {},
            locked_parameters=locked_parameters or [],
            custom_validation=custom_validation,
            created_by=created_by
        )

        self.db.add(binding)
        await self.db.commit()
        await self.db.refresh(binding)

        logger.info(
            f"Created tool binding: {binding_name} for tool {tool.tool_name} "
            f"in context {context.path}"
        )

        return binding

    async def get_binding(self, binding_id: UUID) -> Optional[ToolBinding]:
        """Get binding by UUID."""
        stmt = select(ToolBinding).where(ToolBinding.id == binding_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_binding_by_name(
        self,
        context_id: UUID,
        binding_name: str
    ) -> Optional[ToolBinding]:
        """Get binding by name within context."""
        stmt = select(ToolBinding).where(
            ToolBinding.context_id == context_id,
            ToolBinding.binding_name == binding_name
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_bindings(
        self,
        context_id: UUID,
        include_inherited: bool = False
    ) -> List[ToolBinding]:
        """
        List all bindings in a context.

        Args:
            context_id: Context UUID
            include_inherited: Whether to include bindings from ancestor contexts

        Returns:
            List of ToolBindings
        """
        stmt = select(ToolBinding).where(ToolBinding.context_id == context_id)
        result = await self.db.execute(stmt)
        bindings = result.scalars().all()

        if include_inherited:
            # Get bindings from all ancestor contexts
            context_stmt = select(Context).where(Context.id == context_id)
            context_result = await self.db.execute(context_stmt)
            context = context_result.scalar_one_or_none()

            if context and context.parent_id:
                parent_bindings = await self.list_bindings(
                    context.parent_id,
                    include_inherited=True
                )
                bindings.extend(parent_bindings)

        return bindings

    async def update_binding(
        self,
        binding_id: UUID,
        binding_name: Optional[str] = None,
        description: Optional[str] = None,
        default_parameters: Optional[Dict[str, Any]] = None,
        locked_parameters: Optional[List[str]] = None,
        custom_validation: Optional[Dict[str, Any]] = None
    ) -> ToolBinding:
        """
        Update a tool binding.

        Args:
            binding_id: Binding UUID
            binding_name: New binding name
            description: New description
            default_parameters: New default parameters (replaces existing)
            locked_parameters: New locked parameters (replaces existing)
            custom_validation: New custom validation rules

        Returns:
            Updated ToolBinding

        Raises:
            ValueError: If binding not found or parameters invalid
        """
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        # Get tool for validation
        tool_stmt = select(Tool).where(Tool.id == binding.tool_id)
        tool_result = await self.db.execute(tool_stmt)
        tool = tool_result.scalar_one_or_none()

        if binding_name:
            # Check if new name already exists in context
            existing_stmt = select(ToolBinding).where(
                ToolBinding.context_id == binding.context_id,
                ToolBinding.binding_name == binding_name,
                ToolBinding.id != binding_id
            )
            existing_result = await self.db.execute(existing_stmt)
            if existing_result.scalar_one_or_none():
                raise ValueError(
                    f"Binding '{binding_name}' already exists in this context"
                )
            binding.binding_name = binding_name

        if description is not None:
            binding.description = description

        if default_parameters is not None:
            # Validate against tool schema
            if tool:
                self._validate_parameters(default_parameters, tool.parameters_schema)
            binding.default_parameters = default_parameters

        if locked_parameters is not None:
            # Validate locked parameters exist in schema
            if tool:
                schema_params = tool.parameters_schema.get("properties", {}).keys()
                for locked_param in locked_parameters:
                    if locked_param not in schema_params:
                        raise ValueError(
                            f"Locked parameter '{locked_param}' not in tool schema"
                        )
            binding.locked_parameters = locked_parameters

        if custom_validation is not None:
            binding.custom_validation = custom_validation

        await self.db.commit()
        await self.db.refresh(binding)

        logger.info(f"Updated tool binding: {binding.binding_name}")
        return binding

    async def delete_binding(self, binding_id: UUID) -> None:
        """Delete a tool binding."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        await self.db.delete(binding)
        await self.db.commit()

        logger.info(f"Deleted tool binding: {binding.binding_name}")

    async def execute_binding(
        self,
        binding_id: UUID,
        user_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool binding with merged parameters.

        Args:
            binding_id: Binding UUID
            user_parameters: Parameters provided by user

        Returns:
            Tool execution result

        Raises:
            ValueError: If binding not found or parameters invalid
            RuntimeError: If MCP server not running or execution fails
        """
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        # Merge parameters
        try:
            merged_params = binding.merge_parameters(user_parameters or {})
        except ValueError as e:
            raise ValueError(f"Parameter merge failed: {e}")

        # Get tool
        tool_stmt = select(Tool).where(Tool.id == binding.tool_id)
        tool_result = await self.db.execute(tool_stmt)
        tool = tool_result.scalar_one_or_none()

        if not tool:
            raise ValueError(f"Tool {binding.tool_id} not found")

        # Validate merged parameters against schema
        self._validate_parameters(merged_params, tool.parameters_schema)

        # Get MCP server
        server_stmt = select(MCPServer).where(MCPServer.id == tool.server_id)
        server_result = await self.db.execute(server_stmt)
        server = server_result.scalar_one_or_none()

        if not server:
            raise ValueError(f"MCP Server {tool.server_id} not found")

        if server.status != ServerStatus.RUNNING:
            raise RuntimeError(
                f"MCP Server '{server.server_id}' is not running (status: {server.status})"
            )

        # Execute tool via MCP server
        try:
            result = await self._execute_via_mcp(server, tool.tool_name, merged_params)

            # Update server statistics
            server.total_requests += 1
            await self.db.commit()

            logger.info(
                f"Executed binding '{binding.binding_name}' "
                f"(tool: {tool.tool_name}, server: {server.server_id})"
            )

            return result

        except Exception as e:
            # Update error statistics
            server.failed_requests += 1
            await self.db.commit()

            logger.error(
                f"Failed to execute binding '{binding.binding_name}': {e}"
            )
            raise RuntimeError(f"Tool execution failed: {e}")

    async def _execute_via_mcp(
        self,
        server: MCPServer,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute tool via MCP server using STDIO protocol.

        Args:
            server: MCPServer instance
            tool_name: Tool name
            parameters: Merged parameters

        Returns:
            Tool execution result

        Raises:
            RuntimeError: If execution fails
        """
        # This is a simplified implementation
        # In production, this would use a proper MCP client library
        # and maintain persistent connections to MCP servers

        # Build MCP request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": parameters
            }
        }

        # For now, we'll return a placeholder
        # TODO: Implement actual MCP STDIO communication
        logger.warning(
            f"MCP execution not fully implemented. "
            f"Would execute {tool_name} on {server.server_id} with params: {parameters}"
        )

        return {
            "success": True,
            "result": "Tool execution placeholder - implement MCP client",
            "tool": tool_name,
            "server": server.server_id
        }

    def _validate_parameters(
        self,
        parameters: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> None:
        """
        Validate parameters against JSON Schema.

        Args:
            parameters: Parameters to validate
            schema: JSON Schema

        Raises:
            ValueError: If validation fails
        """
        # Basic validation - in production, use jsonschema library
        schema_properties = schema.get("properties", {})
        required_params = schema.get("required", [])

        # Check required parameters
        for required_param in required_params:
            if required_param not in parameters:
                raise ValueError(f"Required parameter '{required_param}' missing")

        # Check unknown parameters
        for param_name in parameters.keys():
            if param_name not in schema_properties:
                raise ValueError(f"Unknown parameter '{param_name}'")

        # TODO: Add type validation, format validation, etc.
        # For production, use: jsonschema.validate(parameters, schema)

    async def copy_binding(
        self,
        binding_id: UUID,
        new_context_id: UUID,
        new_binding_name: Optional[str] = None
    ) -> ToolBinding:
        """
        Copy a binding to a different context.

        Args:
            binding_id: Source binding UUID
            new_context_id: Target context UUID
            new_binding_name: Optional new name (defaults to original name)

        Returns:
            New ToolBinding instance

        Raises:
            ValueError: If source binding not found or name conflict
        """
        source_binding = await self.get_binding(binding_id)
        if not source_binding:
            raise ValueError(f"Binding {binding_id} not found")

        binding_name = new_binding_name or source_binding.binding_name

        return await self.create_binding(
            organization_id=source_binding.organization_id,
            context_id=new_context_id,
            tool_id=source_binding.tool_id,
            binding_name=binding_name,
            default_parameters=source_binding.default_parameters.copy(),
            locked_parameters=source_binding.locked_parameters.copy(),
            description=source_binding.description,
            custom_validation=source_binding.custom_validation
        )

    async def get_binding_info(self, binding_id: UUID) -> Dict[str, Any]:
        """
        Get comprehensive binding information including tool and server details.

        Args:
            binding_id: Binding UUID

        Returns:
            Dictionary with binding, tool, and server information
        """
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        # Get tool
        tool_stmt = select(Tool).where(Tool.id == binding.tool_id)
        tool_result = await self.db.execute(tool_stmt)
        tool = tool_result.scalar_one_or_none()

        # Get server
        server = None
        if tool:
            server_stmt = select(MCPServer).where(MCPServer.id == tool.server_id)
            server_result = await self.db.execute(server_stmt)
            server = server_result.scalar_one_or_none()

        # Get context
        context_stmt = select(Context).where(Context.id == binding.context_id)
        context_result = await self.db.execute(context_stmt)
        context = context_result.scalar_one_or_none()

        return {
            "binding": binding.to_dict(),
            "tool": tool.to_dict() if tool else None,
            "server": server.to_dict() if server else None,
            "context": context.to_dict() if context else None,
            "available_parameters": tool.parameters_schema.get("properties", {}) if tool else {},
            "pre_filled_parameters": list(binding.default_parameters.keys()),
            "locked_parameters": binding.locked_parameters,
            "user_must_provide": [
                param for param in tool.parameters_schema.get("required", [])
                if param not in binding.default_parameters
            ] if tool else []
        }
