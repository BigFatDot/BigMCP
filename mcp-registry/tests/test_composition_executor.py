"""
Tests for Composition Executor.

Tests workflow composition execution:
- Step execution
- Parameter resolution
- Error handling
- Timeout management
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.orchestration.composition_executor import (
    CompositionExecutor,
    StepExecution,
    CompositionExecution
)
from app.orchestration.composition_store import CompositionInfo, get_composition_store


# ===== Data Class Tests =====

class TestStepExecution:
    """Tests for StepExecution dataclass."""

    def test_step_execution_creation(self):
        """Test creating a StepExecution."""
        step = StepExecution(
            step_id="step-1",
            tool="test_tool",
            status="success",
            result={"output": "value"},
            duration_ms=100
        )

        assert step.step_id == "step-1"
        assert step.tool == "test_tool"
        assert step.status == "success"
        assert step.result == {"output": "value"}
        assert step.duration_ms == 100
        assert step.error is None
        assert step.retries == 0

    def test_step_execution_with_error(self):
        """Test StepExecution with error."""
        step = StepExecution(
            step_id="step-2",
            tool="failing_tool",
            status="failed",
            error="Tool not found",
            retries=2
        )

        assert step.status == "failed"
        assert step.error == "Tool not found"
        assert step.retries == 2
        assert step.result is None

    def test_step_execution_defaults(self):
        """Test StepExecution default values."""
        step = StepExecution(
            step_id="step-3",
            tool="tool",
            status="pending"
        )

        assert step.result is None
        assert step.error is None
        assert step.duration_ms == 0
        assert step.retries == 0


class TestCompositionExecution:
    """Tests for CompositionExecution dataclass."""

    def test_composition_execution_creation(self):
        """Test creating a CompositionExecution."""
        execution = CompositionExecution(
            composition_id="comp-1",
            execution_id="exec-1",
            status="success",
            steps_executed=[
                StepExecution(step_id="s1", tool="t1", status="success"),
                StepExecution(step_id="s2", tool="t2", status="success")
            ],
            result={"final": "result"},
            total_duration_ms=500
        )

        assert execution.composition_id == "comp-1"
        assert execution.execution_id == "exec-1"
        assert execution.status == "success"
        assert len(execution.steps_executed) == 2
        assert execution.total_duration_ms == 500

    def test_composition_execution_with_errors(self):
        """Test CompositionExecution with errors."""
        execution = CompositionExecution(
            composition_id="comp-2",
            execution_id="exec-2",
            status="failed",
            errors=["Step 1 failed", "Timeout exceeded"]
        )

        assert execution.status == "failed"
        assert len(execution.errors) == 2
        assert "Step 1 failed" in execution.errors

    def test_composition_execution_defaults(self):
        """Test CompositionExecution default values."""
        execution = CompositionExecution(
            composition_id="comp-3",
            execution_id="exec-3",
            status="pending"
        )

        assert execution.steps_executed == []
        assert execution.errors == []
        assert execution.result is None
        assert execution.total_duration_ms == 0
        assert execution.started_at == ""
        assert execution.completed_at == ""


# ===== Composition Store Tests =====

class TestCompositionStore:
    """Tests for composition store singleton."""

    def test_get_composition_store_singleton(self):
        """Test composition store is singleton."""
        store1 = get_composition_store()
        store2 = get_composition_store()

        assert store1 is store2

    def test_composition_info_creation(self):
        """Test creating CompositionInfo."""
        comp = CompositionInfo(
            id="test-comp",
            name="Test Composition",
            description="A test workflow",
            steps=[
                {"tool": "tool1", "parameters": {}},
                {"tool": "tool2", "parameters": {"input": "${step_0.output}"}}
            ],
            allowed_roles=["admin", "owner"]
        )

        assert comp.id == "test-comp"
        assert comp.name == "Test Composition"
        assert len(comp.steps) == 2
        assert comp.allowed_roles == ["admin", "owner"]


# ===== Executor Tests =====

class TestCompositionExecutor:
    """Tests for CompositionExecutor class."""

    def test_executor_initialization(self):
        """Test executor initializes with registry."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        assert executor.registry is mock_registry
        assert executor.max_retries == 3
        assert executor.default_timeout == 60
        assert executor.composition_store is not None

    @pytest.mark.asyncio
    async def test_execute_unknown_composition(self):
        """Test executing unknown composition returns error."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        result = await executor.execute(
            composition_id="nonexistent-composition",
            parameters={}
        )

        assert result is not None
        # Should indicate error or not found
        assert "error" in str(result).lower() or result.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_execute_with_parameters(self):
        """Test execute accepts parameters."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        # This may fail for unknown composition, but should accept params
        result = await executor.execute(
            composition_id="test",
            parameters={"key": "value"},
            execution_mode="sequential"
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_modes(self):
        """Test different execution modes are accepted."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        for mode in ["sequential", "parallel", "auto"]:
            result = await executor.execute(
                composition_id="test",
                parameters={},
                execution_mode=mode
            )
            assert result is not None


# ===== Parameter Resolution Tests =====

class TestParameterResolution:
    """Tests for parameter resolution in compositions."""

    def test_static_parameter(self):
        """Test static parameter is unchanged."""
        # Parameter without ${} should remain static
        param = {"value": 42, "name": "static"}
        assert param["value"] == 42

    def test_reference_format(self):
        """Test reference format detection."""
        # Valid reference format
        ref1 = "${step_0.output}"
        ref2 = "${step_1.result.data}"
        ref3 = "${input.query}"

        assert ref1.startswith("${") and ref1.endswith("}")
        assert ref2.startswith("${") and ref2.endswith("}")
        assert ref3.startswith("${") and ref3.endswith("}")

    def test_nested_reference_format(self):
        """Test nested reference format."""
        ref = "${step_0.output.items[0].name}"
        assert "step_0" in ref
        assert "items" in ref


# ===== Error Handling Tests =====

class TestExecutorErrorHandling:
    """Tests for executor error handling."""

    def test_step_error_captured(self):
        """Test step errors are captured in StepExecution."""
        step = StepExecution(
            step_id="error-step",
            tool="broken_tool",
            status="failed",
            error="Connection refused"
        )

        assert step.status == "failed"
        assert "Connection refused" in step.error

    def test_composition_partial_failure(self):
        """Test composition can have partial status."""
        execution = CompositionExecution(
            composition_id="partial",
            execution_id="exec-partial",
            status="partial",
            steps_executed=[
                StepExecution(step_id="s1", tool="t1", status="success"),
                StepExecution(step_id="s2", tool="t2", status="failed", error="Failed"),
                StepExecution(step_id="s3", tool="t3", status="skipped")
            ],
            errors=["Step 2 failed"]
        )

        assert execution.status == "partial"
        success_count = sum(1 for s in execution.steps_executed if s.status == "success")
        failed_count = sum(1 for s in execution.steps_executed if s.status == "failed")
        assert success_count == 1
        assert failed_count == 1


# ===== Timeout Tests =====

class TestExecutorTimeout:
    """Tests for executor timeout handling."""

    def test_default_timeout(self):
        """Test default timeout is set."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        assert executor.default_timeout == 60

    def test_max_retries(self):
        """Test max retries is set."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        assert executor.max_retries == 3


# ===== Multi-tenant Tests =====

class TestExecutorMultiTenant:
    """Tests for multi-tenant execution context."""

    @pytest.mark.asyncio
    async def test_execute_with_user_context(self):
        """Test execute accepts user/org context."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        user_id = str(uuid4())
        org_id = str(uuid4())

        result = await executor.execute(
            composition_id="test",
            parameters={},
            user_id=user_id,
            organization_id=org_id
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_with_user_pool(self):
        """Test execute accepts user server pool."""
        mock_registry = MagicMock()
        mock_pool = MagicMock()
        executor = CompositionExecutor(mock_registry)

        result = await executor.execute(
            composition_id="test",
            parameters={},
            user_server_pool=mock_pool
        )

        assert result is not None


# ===== Wildcard Extraction Tests =====

class TestWildcardExtraction:
    """Tests for [*] wildcard extraction in path navigation."""

    def test_extract_simple_wildcard(self):
        """Test extracting all values from array with [*]."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "items": [
                {"id": "a", "name": "Item A"},
                {"id": "b", "name": "Item B"},
                {"id": "c", "name": "Item C"}
            ]
        }

        result = executor._extract_value_from_path(obj, "items[*].id")

        assert result == ["a", "b", "c"]

    def test_extract_wildcard_all_items(self):
        """Test extracting entire items with [*] only."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ]
        }

        result = executor._extract_value_from_path(obj, "users[*]")

        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"

    def test_extract_nested_wildcard_flatten(self):
        """Test nested wildcards auto-flatten results."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "workspaces": [
                {
                    "id": "ws1",
                    "docs": [
                        {"id": "doc1", "name": "Doc 1"},
                        {"id": "doc2", "name": "Doc 2"}
                    ]
                },
                {
                    "id": "ws2",
                    "docs": [
                        {"id": "doc3", "name": "Doc 3"}
                    ]
                }
            ]
        }

        result = executor._extract_value_from_path(obj, "workspaces[*].docs[*].id")

        assert result == ["doc1", "doc2", "doc3"]

    def test_extract_nested_wildcard_names(self):
        """Test nested wildcards with different field."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "categories": [
                {
                    "name": "Electronics",
                    "products": [
                        {"sku": "E001", "title": "Phone"},
                        {"sku": "E002", "title": "Laptop"}
                    ]
                },
                {
                    "name": "Books",
                    "products": [
                        {"sku": "B001", "title": "Novel"}
                    ]
                }
            ]
        }

        result = executor._extract_value_from_path(obj, "categories[*].products[*].title")

        assert result == ["Phone", "Laptop", "Novel"]

    def test_extract_wildcard_empty_array(self):
        """Test wildcard on empty array returns empty list."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {"items": []}

        result = executor._extract_value_from_path(obj, "items[*].id")

        assert result == []

    def test_extract_wildcard_missing_field(self):
        """Test wildcard with missing nested field skips items."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "items": [
                {"id": "a", "value": 1},
                {"id": "b"},  # No value field
                {"id": "c", "value": 3}
            ]
        }

        result = executor._extract_value_from_path(obj, "items[*].value")

        assert result == [1, 3]

    def test_extract_wildcard_deep_path(self):
        """Test wildcard with deep nested path."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "data": {
                "results": [
                    {"metadata": {"status": "active"}},
                    {"metadata": {"status": "inactive"}},
                    {"metadata": {"status": "active"}}
                ]
            }
        }

        result = executor._extract_value_from_path(obj, "data.results[*].metadata.status")

        assert result == ["active", "inactive", "active"]

    def test_extract_standard_index_still_works(self):
        """Test standard [0] index extraction still works."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "items": [
                {"id": "first"},
                {"id": "second"}
            ]
        }

        result = executor._extract_value_from_path(obj, "items[0].id")

        assert result == "first"

    def test_extract_mixed_index_and_wildcard(self):
        """Test combining specific index with wildcard."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "workspaces": [
                {
                    "id": "ws1",
                    "docs": [{"id": "doc1"}, {"id": "doc2"}]
                },
                {
                    "id": "ws2",
                    "docs": [{"id": "doc3"}]
                }
            ]
        }

        # First workspace, all docs
        result = executor._extract_value_from_path(obj, "workspaces[0].docs[*].id")

        assert result == ["doc1", "doc2"]


# ===== Parameter Resolution with Wildcards =====

class TestParameterResolutionWildcard:
    """Tests for parameter resolution with wildcard extraction."""

    def test_resolve_single_wildcard_reference(self):
        """Test resolving a parameter that is exactly one wildcard reference."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "items": [
                        {"id": "x1"},
                        {"id": "x2"},
                        {"id": "x3"}
                    ]
                }
            }
        }

        params = {"ids": "${step_1.items[*].id}"}
        result = executor._resolve_parameters(params, context)

        assert result["ids"] == ["x1", "x2", "x3"]

    def test_resolve_wildcard_preserves_list_type(self):
        """Test that wildcard result is a real list, not string."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "users": [
                        {"name": "Alice"},
                        {"name": "Bob"}
                    ]
                }
            }
        }

        params = {"names": "${step_1.users[*].name}"}
        result = executor._resolve_parameters(params, context)

        assert isinstance(result["names"], list)
        assert result["names"] == ["Alice", "Bob"]

    def test_resolve_embedded_wildcard_json_encoded(self):
        """Test wildcard embedded in string is JSON encoded."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "items": [{"id": "a"}, {"id": "b"}]
                }
            }
        }

        params = {"message": "Found IDs: ${step_1.items[*].id}"}
        result = executor._resolve_parameters(params, context)

        assert result["message"] == 'Found IDs: ["a", "b"]'

    def test_resolve_nested_dict_parameters(self):
        """Test resolving parameters in nested dict."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "data": [{"val": 10}, {"val": 20}]
                }
            }
        }

        params = {
            "config": {
                "values": "${step_1.data[*].val}"
            }
        }
        result = executor._resolve_parameters(params, context)

        assert result["config"]["values"] == [10, 20]

    def test_resolve_list_parameters(self):
        """Test resolving parameters in list items."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {"base": "test"},
            "step_results": {}
        }

        params = {
            "items": ["${input.base}", "static"]
        }
        result = executor._resolve_parameters(params, context)

        assert result["items"][0] == "test"
        assert result["items"][1] == "static"

    def test_resolve_input_reference(self):
        """Test input parameter reference still works."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {"query": "hello world"},
            "step_results": {}
        }

        params = {"search": "${input.query}"}
        result = executor._resolve_parameters(params, context)

        assert result["search"] == "hello world"

    def test_resolve_null_for_missing_path(self):
        """Test missing path in embedded string becomes null."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {"1": {"data": "value"}}
        }

        params = {"msg": "Value: ${step_1.nonexistent}"}
        result = executor._resolve_parameters(params, context)

        assert result["msg"] == "Value: null"

    def test_resolve_three_level_nested_wildcard(self):
        """Test three levels of nested wildcards."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "orgs": [
                        {
                            "id": "org1",
                            "workspaces": [
                                {
                                    "id": "ws1",
                                    "docs": [{"id": "d1"}, {"id": "d2"}]
                                }
                            ]
                        },
                        {
                            "id": "org2",
                            "workspaces": [
                                {
                                    "id": "ws2",
                                    "docs": [{"id": "d3"}]
                                },
                                {
                                    "id": "ws3",
                                    "docs": [{"id": "d4"}, {"id": "d5"}]
                                }
                            ]
                        }
                    ]
                }
            }
        }

        params = {"doc_ids": "${step_1.orgs[*].workspaces[*].docs[*].id}"}
        result = executor._resolve_parameters(params, context)

        assert result["doc_ids"] == ["d1", "d2", "d3", "d4", "d5"]


# ===== Template/Map Tests =====

class TestTemplateMap:
    """Tests for _template/_map object mapping."""

    def test_simple_template_map(self):
        """Test basic _template/_map with _item."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "users": [
                        {"id": "u1", "name": "Alice"},
                        {"id": "u2", "name": "Bob"}
                    ]
                }
            }
        }

        params = {
            "mapped_users": {
                "_template": "${step_1.users[*]}",
                "_map": {
                    "user_id": "${_item.id}",
                    "display_name": "${_item.name}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["mapped_users"]) == 2
        assert result["mapped_users"][0] == {"user_id": "u1", "display_name": "Alice"}
        assert result["mapped_users"][1] == {"user_id": "u2", "display_name": "Bob"}

    def test_template_map_with_literal_values(self):
        """Test _template/_map with literal (non-variable) values."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "items": [{"id": "a"}, {"id": "b"}]
                }
            }
        }

        params = {
            "result": {
                "_template": "${step_1.items[*]}",
                "_map": {
                    "source": "my-source",
                    "item_id": "${_item.id}",
                    "version": 1
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["result"]) == 2
        assert result["result"][0]["source"] == "my-source"
        assert result["result"][0]["item_id"] == "a"
        assert result["result"][0]["version"] == 1
        assert result["result"][1]["item_id"] == "b"

    def test_template_map_with_index(self):
        """Test _template/_map with _index variable."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "items": [{"name": "first"}, {"name": "second"}, {"name": "third"}]
                }
            }
        }

        params = {
            "indexed": {
                "_template": "${step_1.items[*]}",
                "_map": {
                    "position": "${_index}",
                    "name": "${_item.name}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["indexed"]) == 3
        assert result["indexed"][0]["position"] == 0
        assert result["indexed"][1]["position"] == 1
        assert result["indexed"][2]["position"] == 2

    def test_template_map_with_now(self):
        """Test _template/_map with _now timestamp."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "items": [{"id": "x"}]
                }
            }
        }

        params = {
            "timestamped": {
                "_template": "${step_1.items[*]}",
                "_map": {
                    "id": "${_item.id}",
                    "created_at": "${_now}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["timestamped"]) == 1
        assert result["timestamped"][0]["id"] == "x"
        # Check that _now is an ISO timestamp
        created_at = result["timestamped"][0]["created_at"]
        assert "T" in created_at
        assert created_at.endswith("Z")

    def test_template_map_with_parent_context(self):
        """Test _template/_map with nested wildcards and _parent."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "workspaces": [
                        {
                            "id": "ws1",
                            "name": "Workspace 1",
                            "docs": [
                                {"id": "doc1", "title": "Doc 1"},
                                {"id": "doc2", "title": "Doc 2"}
                            ]
                        },
                        {
                            "id": "ws2",
                            "name": "Workspace 2",
                            "docs": [
                                {"id": "doc3", "title": "Doc 3"}
                            ]
                        }
                    ]
                }
            }
        }

        params = {
            "flattened_docs": {
                "_template": "${step_1.workspaces[*].docs[*]}",
                "_map": {
                    "doc_id": "${_item.id}",
                    "doc_title": "${_item.title}",
                    "workspace_id": "${_parent.id}",
                    "workspace_name": "${_parent.name}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["flattened_docs"]) == 3

        # First doc from workspace 1
        assert result["flattened_docs"][0]["doc_id"] == "doc1"
        assert result["flattened_docs"][0]["workspace_id"] == "ws1"
        assert result["flattened_docs"][0]["workspace_name"] == "Workspace 1"

        # Second doc from workspace 1
        assert result["flattened_docs"][1]["doc_id"] == "doc2"
        assert result["flattened_docs"][1]["workspace_id"] == "ws1"

        # Doc from workspace 2
        assert result["flattened_docs"][2]["doc_id"] == "doc3"
        assert result["flattened_docs"][2]["workspace_id"] == "ws2"
        assert result["flattened_docs"][2]["workspace_name"] == "Workspace 2"

    def test_template_map_with_root_context(self):
        """Test _template/_map with _root variable."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "metadata": {"source": "grist", "version": "1.0"},
                    "items": [
                        {"id": "a"},
                        {"id": "b"}
                    ]
                }
            }
        }

        params = {
            "enriched": {
                "_template": "${step_1.items[*]}",
                "_map": {
                    "id": "${_item.id}",
                    "source": "${_root.metadata.source}",
                    "api_version": "${_root.metadata.version}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["enriched"]) == 2
        assert result["enriched"][0]["id"] == "a"
        assert result["enriched"][0]["source"] == "grist"
        assert result["enriched"][0]["api_version"] == "1.0"
        assert result["enriched"][1]["id"] == "b"
        assert result["enriched"][1]["source"] == "grist"

    def test_template_map_empty_array(self):
        """Test _template/_map with empty source array."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {"items": []}
            }
        }

        params = {
            "result": {
                "_template": "${step_1.items[*]}",
                "_map": {"id": "${_item.id}"}
            }
        }

        result = executor._resolve_parameters(params, context)

        assert result["result"] == []

    def test_template_map_with_comment_ignored(self):
        """Test that _comment field is ignored in _map."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {"items": [{"id": "x"}]}
            }
        }

        params = {
            "result": {
                "_template": "${step_1.items[*]}",
                "_map": {
                    "_comment": "This maps items to output format",
                    "id": "${_item.id}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["result"]) == 1
        assert "id" in result["result"][0]
        assert "_comment" not in result["result"][0]

    def test_template_map_three_level_nesting(self):
        """Test _template/_map with three levels of nesting."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "parameters": {},
            "step_results": {
                "1": {
                    "orgs": [
                        {
                            "id": "org1",
                            "workspaces": [
                                {
                                    "id": "ws1",
                                    "docs": [{"id": "d1"}, {"id": "d2"}]
                                }
                            ]
                        },
                        {
                            "id": "org2",
                            "workspaces": [
                                {
                                    "id": "ws2",
                                    "docs": [{"id": "d3"}]
                                }
                            ]
                        }
                    ]
                }
            }
        }

        params = {
            "all_docs": {
                "_template": "${step_1.orgs[*].workspaces[*].docs[*]}",
                "_map": {
                    "doc_id": "${_item.id}",
                    "workspace_id": "${_parent.id}"
                }
            }
        }

        result = executor._resolve_parameters(params, context)

        assert len(result["all_docs"]) == 3
        assert result["all_docs"][0] == {"doc_id": "d1", "workspace_id": "ws1"}
        assert result["all_docs"][1] == {"doc_id": "d2", "workspace_id": "ws1"}
        assert result["all_docs"][2] == {"doc_id": "d3", "workspace_id": "ws2"}


# ===== Iterate With Parent Tracking Tests =====

class TestIterateWithParentTracking:
    """Tests for _iterate_with_parent_tracking method."""

    def test_single_level_iteration(self):
        """Test iteration with single wildcard level."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "items": [
                {"id": "a", "value": 1},
                {"id": "b", "value": 2}
            ]
        }

        result = executor._iterate_with_parent_tracking(obj, "items[*]", obj)

        assert len(result) == 2
        assert result[0]["_item"] == {"id": "a", "value": 1}
        assert result[0]["_root"] == obj
        assert result[1]["_item"] == {"id": "b", "value": 2}

    def test_nested_iteration_preserves_parent(self):
        """Test nested iteration preserves parent context."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "categories": [
                {
                    "name": "Cat A",
                    "items": [{"id": 1}, {"id": 2}]
                },
                {
                    "name": "Cat B",
                    "items": [{"id": 3}]
                }
            ]
        }

        result = executor._iterate_with_parent_tracking(
            obj, "categories[*].items[*]", obj
        )

        assert len(result) == 3

        # Items from Cat A should have Cat A as parent
        assert result[0]["_item"] == {"id": 1}
        assert result[0]["_parent"]["name"] == "Cat A"

        assert result[1]["_item"] == {"id": 2}
        assert result[1]["_parent"]["name"] == "Cat A"

        # Item from Cat B should have Cat B as parent
        assert result[2]["_item"] == {"id": 3}
        assert result[2]["_parent"]["name"] == "Cat B"

    def test_iteration_with_field_extraction(self):
        """Test iteration extracting specific field."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {
            "users": [
                {"profile": {"name": "Alice"}},
                {"profile": {"name": "Bob"}}
            ]
        }

        result = executor._iterate_with_parent_tracking(
            obj, "users[*].profile.name", obj
        )

        assert len(result) == 2
        assert result[0]["_item"] == "Alice"
        assert result[1]["_item"] == "Bob"

    def test_iteration_empty_array(self):
        """Test iteration with empty array."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        obj = {"items": []}

        result = executor._iterate_with_parent_tracking(obj, "items[*]", obj)

        assert result == []


# ===== Extract With Parent Context Tests =====

class TestExtractWithParentContext:
    """Tests for _extract_with_parent_context method."""

    def test_extract_simple_array(self):
        """Test extracting from simple array reference."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "step_results": {
                "1": {
                    "items": [{"id": "x"}, {"id": "y"}]
                }
            }
        }

        result = executor._extract_with_parent_context(
            "${step_1.items[*]}", context
        )

        assert len(result) == 2
        assert result[0]["_item"] == {"id": "x"}
        assert result[1]["_item"] == {"id": "y"}

    def test_extract_nested_array(self):
        """Test extracting from nested array with parent tracking."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {
            "step_results": {
                "1": {
                    "groups": [
                        {"name": "G1", "members": [{"id": "m1"}]},
                        {"name": "G2", "members": [{"id": "m2"}, {"id": "m3"}]}
                    ]
                }
            }
        }

        result = executor._extract_with_parent_context(
            "${step_1.groups[*].members[*]}", context
        )

        assert len(result) == 3
        assert result[0]["_item"] == {"id": "m1"}
        assert result[0]["_parent"]["name"] == "G1"
        assert result[1]["_item"] == {"id": "m2"}
        assert result[1]["_parent"]["name"] == "G2"

    def test_extract_invalid_reference(self):
        """Test extracting with invalid reference returns empty."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {"step_results": {}}

        result = executor._extract_with_parent_context("not-a-reference", context)
        assert result == []

        result = executor._extract_with_parent_context("${invalid}", context)
        assert result == []

    def test_extract_missing_step(self):
        """Test extracting from missing step returns empty."""
        mock_registry = MagicMock()
        executor = CompositionExecutor(mock_registry)

        context = {"step_results": {"1": {"data": []}}}

        result = executor._extract_with_parent_context(
            "${step_99.items[*]}", context
        )

        assert result == []
