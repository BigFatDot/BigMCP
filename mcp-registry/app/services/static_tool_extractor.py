"""
Static Tool Extractor Service

Extracts tool definitions from MCP server source code using AST parsing.
No execution required - just downloads and analyzes the code.

Supports:
- TypeScript/JavaScript (npm packages)
- Python (pip packages)

Patterns detected:
- TypeScript: server.registerTool("name", {...}, handler)
- Python: Tool(name=..., description=..., inputSchema=...)
- Python FastMCP: @mcp.tool decorator
"""

import ast
import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PackageType(str, Enum):
    NPM = "npm"
    PIP = "pip"
    GITHUB = "github"


@dataclass
class ExtractedTool:
    """Represents a tool extracted from source code."""
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    input_schema: dict = field(default_factory=dict)
    annotations: dict = field(default_factory=dict)

    # Derived from annotations
    is_read_only: bool = False
    is_destructive: bool = False
    is_idempotent: bool = False

    # Detected from code
    requires_env_vars: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of static analysis on a package."""
    package_name: str
    package_type: PackageType
    tools: list[ExtractedTool]
    detected_env_vars: list[str]
    detected_cli_args: list[str] = field(default_factory=list)
    requires_local_access: bool = False
    has_dynamic_tools: bool = False  # Tools are registered dynamically at runtime
    package_not_found: bool = False  # Package doesn't exist on registry (404)
    extraction_time_ms: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def all_required_config(self) -> list[str]:
        """All required configuration (env vars + CLI args)."""
        return self.detected_env_vars + self.detected_cli_args


class StaticToolExtractor:
    """
    Extracts tool definitions from MCP server packages without executing them.

    Usage:
        extractor = StaticToolExtractor()
        result = await extractor.extract_from_npm("@modelcontextprotocol/server-filesystem")
        for tool in result.tools:
            print(f"{tool.name}: {tool.description}")
    """

    # Environment variable patterns to detect
    ENV_VAR_PATTERNS = [
        r'process\.env\.([A-Z][A-Z0-9_]+)',  # JS: process.env.VAR
        r'os\.environ\[[\'"]([\w_]+)[\'\"]\]',  # Python: os.environ["VAR"]
        r'os\.getenv\([\'"]([\w_]+)[\'\"]\)',  # Python: os.getenv("VAR")
        r'getenv\([\'"]([\w_]+)[\'\"]\)',  # Python: getenv("VAR")
        r'\$\{([A-Z][A-Z0-9_]+)\}',  # Shell-style ${VAR}
    ]

    # CLI argument patterns (required configuration)
    CLI_ARG_PATTERNS = [
        # argparse
        r'add_argument\([\'"]--([a-z][a-z0-9_-]+)[\'"]',
        r'add_argument\([\'"]([A-Z][A-Z0-9_]+)[\'"]',  # positional
        # click
        r'@click\.option\([\'"]--([a-z][a-z0-9_-]+)[\'"]',
        r'@click\.argument\([\'"]([a-z][a-z0-9_]+)[\'"]',
        # typer
        r'typer\.Option\([^)]*[\'"]--([a-z][a-z0-9_-]+)[\'"]',
        r'typer\.Argument\(',
        # Generic patterns
        r'required[\'"]:\s*True[^}]*[\'"]([a-z_]+)[\'"]',
    ]

    # Patterns indicating local-only functionality (can't work with remote services)
    LOCAL_ACCESS_PATTERNS = [
        # Node.js fs module - direct filesystem access
        r'fs\.read(?!Stream)',  # fs.read but not fs.readStream
        r'fs\.write(?!Stream)',  # fs.write but not fs.writeStream
        r'fs\.access\(',
        r'fs\.stat\(',
        r'fs\.mkdir\(',
        r'fs\.unlink\(',
        r'fs\.rmdir\(',
        r'fs\.readdir\(',
        # Python direct filesystem operations
        r'open\([^)]*[\'"][rwab]',  # open() with file mode
        r'os\.remove\(',
        r'os\.unlink\(',
        r'os\.makedirs\(',
        r'shutil\.',
        # Git local repos (not remote URLs)
        r'git\.Repo\([^)]*[\'"]/',  # git.Repo with local path
        # Subprocesses and system access
        r'subprocess\.run\(',
        r'subprocess\.call\(',
        r'subprocess\.Popen\(',
        r'os\.system\(',
        r'os\.popen\(',
        # Docker local
        r'DockerClient\(',
        r'docker\.from_env\(',
        # Browser/Puppeteer - requires local browser
        r'puppeteer\.launch\(',
        r'playwright\.\w+\.launch\(',
        r'selenium\.webdriver\.',
        # Database files (local SQLite)
        r'sqlite3\.connect\([^)]*[\'"](?!:memory:)',  # SQLite with file path
        r'\.db[\'"]',
    ]

    # Patterns indicating REMOTE-configurable services (NOT local-only)
    REMOTE_CAPABLE_PATTERNS = [
        r'_API_URL',  # API_URL, GRIST_API_URL, etc.
        r'_BASE_URL',
        r'_ENDPOINT',
        r'_HOST\s*[=:]',
        r'https?://',  # HTTP/HTTPS URLs indicate remote capability
        r'requests\.',  # Python requests library = HTTP calls
        r'httpx\.',  # Python httpx library
        r'axios\.',  # JS axios
        r'fetch\(',  # JS fetch API
    ]

    # Patterns indicating DYNAMIC tool registration (tools loaded at runtime)
    DYNAMIC_TOOLS_PATTERNS = [
        r'registerToolsets?\s*\(',  # registerToolset(), registerToolsets()
        r'loadTools?\s*\(',  # loadTool(), loadTools()
        r'dynamicTools?',  # dynamicTool, dynamicTools variable
        r'toolLoader',  # tool loader patterns
        r'import\s*\(\s*[\'"].*tool',  # dynamic imports of tools
        r'require\s*\(\s*[\'"].*tool',  # dynamic require of tools
        r'glob\s*\([^)]*tool',  # glob pattern to find tools
        r'scanDir.*tool',  # directory scanning for tools
        r'pluginManager',  # plugin-based tool loading
    ]

    # Security limits
    MAX_PACKAGE_SIZE_MB = 50  # Max tarball size
    MAX_EXTRACTED_SIZE_MB = 200  # Max extracted size
    MAX_FILE_SIZE_MB = 10  # Max single file size to parse
    MAX_FILES_TO_PARSE = 100  # Max number of files to analyze

    def __init__(self, temp_dir: Optional[Path] = None):
        """
        Initialize the extractor.

        SECURITY: This extractor NEVER executes code. It only:
        1. Downloads package tarballs (no npm install, no pip install)
        2. Extracts to isolated temp directory
        3. Parses source code as TEXT using regex/AST
        4. Cleans up temp files

        Args:
            temp_dir: Optional custom temp directory for downloads
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "mcp_extractor"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def extract_from_npm(self, package_name: str) -> ExtractionResult:
        """
        Extract tools from an npm package.

        Args:
            package_name: npm package name (e.g., "@modelcontextprotocol/server-github")

        Returns:
            ExtractionResult with extracted tools and metadata
        """
        import time
        start_time = time.time()

        errors = []
        tools = []
        env_vars = set()
        cli_args = set()
        requires_local = False
        has_dynamic_tools = False

        try:
            # Download package without installing
            pkg_dir = await self._download_npm_package(package_name)

            # Find JavaScript/TypeScript files
            js_files = list(pkg_dir.glob("**/*.js")) + list(pkg_dir.glob("**/*.ts"))
            for js_file in js_files:
                try:
                    content = js_file.read_text(encoding="utf-8", errors="ignore")

                    # Extract tools
                    file_tools = self._extract_js_tools(content)
                    tools.extend(file_tools)

                    # Detect env vars
                    file_env_vars = self._detect_env_vars(content)
                    env_vars.update(file_env_vars)

                    # Detect CLI args
                    file_cli_args = self._detect_cli_args(content)
                    cli_args.update(file_cli_args)

                    # Check for local access patterns
                    if self._check_local_access(content):
                        requires_local = True

                    # Check for dynamic tool registration
                    if self._check_dynamic_tools(content):
                        has_dynamic_tools = True

                except Exception as e:
                    errors.append(f"Error parsing {js_file.name}: {str(e)}")

        except Exception as e:
            error_str = str(e)
            errors.append(f"Failed to download package: {error_str}")
            # Check if package doesn't exist (404)
            if "404" in error_str or "Not found" in error_str or "not in this registry" in error_str:
                package_not_found = True
            else:
                package_not_found = False
        else:
            package_not_found = False
        finally:
            # Cleanup
            self._cleanup_temp(package_name)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return ExtractionResult(
            package_name=package_name,
            package_type=PackageType.NPM,
            tools=tools,
            detected_env_vars=list(env_vars),
            detected_cli_args=list(cli_args),
            requires_local_access=requires_local,
            has_dynamic_tools=has_dynamic_tools,
            package_not_found=package_not_found,
            extraction_time_ms=elapsed_ms,
            errors=errors
        )

    async def extract_from_pip(self, package_name: str) -> ExtractionResult:
        """
        Extract tools from a pip package.

        Args:
            package_name: pip package name (e.g., "mcp-server-git")

        Returns:
            ExtractionResult with extracted tools and metadata
        """
        import time
        start_time = time.time()

        errors = []
        tools = []
        env_vars = set()
        cli_args = set()
        requires_local = False
        has_dynamic_tools = False

        try:
            # Download package without installing
            pkg_dir = await self._download_pip_package(package_name)

            # Find Python files
            py_files = list(pkg_dir.glob("**/*.py"))

            for py_file in py_files:
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")

                    # Extract tools using AST
                    file_tools = self._extract_python_tools(content)
                    tools.extend(file_tools)

                    # Detect env vars
                    file_env_vars = self._detect_env_vars(content)
                    env_vars.update(file_env_vars)

                    # Detect CLI args
                    file_cli_args = self._detect_cli_args(content)
                    cli_args.update(file_cli_args)

                    # Check for local access patterns
                    if self._check_local_access(content):
                        requires_local = True

                    # Check for dynamic tool registration
                    if self._check_dynamic_tools(content):
                        has_dynamic_tools = True

                except Exception as e:
                    errors.append(f"Error parsing {py_file.name}: {str(e)}")

        except Exception as e:
            error_str = str(e)
            errors.append(f"Failed to download package: {error_str}")
            # Check if package doesn't exist
            if "No matching distribution" in error_str or "not found" in error_str.lower():
                package_not_found = True
            else:
                package_not_found = False
        else:
            package_not_found = False
        finally:
            # Cleanup
            self._cleanup_temp(package_name)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return ExtractionResult(
            package_name=package_name,
            package_type=PackageType.PIP,
            tools=tools,
            detected_env_vars=list(env_vars),
            detected_cli_args=list(cli_args),
            requires_local_access=requires_local,
            has_dynamic_tools=has_dynamic_tools,
            package_not_found=package_not_found,
            extraction_time_ms=elapsed_ms,
            errors=errors
        )

    async def _download_npm_package(self, package_name: str) -> Path:
        """Download npm package and extract it."""
        pkg_dir = self.temp_dir / self._safe_name(package_name)
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # npm pack downloads the tarball
        # Use shell=True on Windows for proper PATH resolution
        import platform
        use_shell = platform.system() == "Windows"

        result = subprocess.run(
            ["npm", "pack", package_name, "--pack-destination", str(pkg_dir)],
            capture_output=True,
            text=True,
            timeout=60,
            shell=use_shell
        )

        if result.returncode != 0:
            raise RuntimeError(f"npm pack failed: {result.stderr}")

        # Find and extract the tarball
        tarballs = list(pkg_dir.glob("*.tgz"))
        if not tarballs:
            raise RuntimeError("No tarball found after npm pack")

        import tarfile
        extract_dir = pkg_dir / "extracted"
        with tarfile.open(tarballs[0], "r:gz") as tar:
            tar.extractall(extract_dir)

        # npm extracts to 'package' subdirectory
        return extract_dir / "package"

    async def _download_pip_package(self, package_name: str) -> Path:
        """Download pip package and extract it."""
        pkg_dir = self.temp_dir / self._safe_name(package_name)
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # pip download
        # Use shell=True on Windows for proper PATH resolution
        import platform
        use_shell = platform.system() == "Windows"

        result = subprocess.run(
            ["pip", "download", package_name, "--no-deps", "-d", str(pkg_dir)],
            capture_output=True,
            text=True,
            timeout=60,
            shell=use_shell
        )

        if result.returncode != 0:
            raise RuntimeError(f"pip download failed: {result.stderr}")

        # Find wheel or sdist
        wheels = list(pkg_dir.glob("*.whl"))
        if wheels:
            import zipfile
            extract_dir = pkg_dir / "extracted"
            with zipfile.ZipFile(wheels[0], 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            return extract_dir

        # Try tar.gz
        tarballs = list(pkg_dir.glob("*.tar.gz"))
        if tarballs:
            import tarfile
            extract_dir = pkg_dir / "extracted"
            with tarfile.open(tarballs[0], "r:gz") as tar:
                tar.extractall(extract_dir)
            return extract_dir

        raise RuntimeError("No wheel or tarball found after pip download")

    def _extract_js_tools(self, content: str) -> list[ExtractedTool]:
        """
        Extract tools from JavaScript/TypeScript content.

        Looks for patterns:
        - server.registerTool("name", {...}, handler)
        - server.tool("name", {...}, handler)
        - setRequestHandler(ListToolsRequestSchema, ...) with tools array
        """
        tools = []

        # Pattern 1: registerTool calls (new pattern)
        pattern = r'(?:server|app|mcp)\.(?:registerTool|tool)\s*\(\s*["\']([^"\']+)["\']'

        for match in re.finditer(pattern, content):
            tool_name = match.group(1)

            # Find the configuration object after the name
            start_pos = match.end()

            # Extract title, description from nearby content
            config_text = content[start_pos:start_pos + 2000]  # Look ahead

            title = self._extract_string_field(config_text, "title")
            description = self._extract_string_field(config_text, "description")

            # Extract annotations
            annotations = {}
            for hint in ["readOnlyHint", "destructiveHint", "idempotentHint"]:
                if f"{hint}: true" in config_text or f"{hint}:true" in config_text:
                    annotations[hint] = True
                elif f"{hint}: false" in config_text or f"{hint}:false" in config_text:
                    annotations[hint] = False

            tool = ExtractedTool(
                name=tool_name,
                title=title,
                description=description,
                annotations=annotations,
                is_read_only=annotations.get("readOnlyHint", False),
                is_destructive=annotations.get("destructiveHint", False),
                is_idempotent=annotations.get("idempotentHint", False),
            )
            tools.append(tool)

        # Pattern 2: server.tool("name", "description", {...}) - description as 2nd arg
        # Common pattern where description is a positional argument, not in config object
        existing_names = {t.name for t in tools}
        pattern_positional = r'\.tool\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern_positional, content):
            tool_name = match.group(1)
            description = match.group(2)
            if tool_name not in existing_names:
                existing_names.add(tool_name)
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=description,
                ))
            else:
                # Update existing tool's description if empty
                for t in tools:
                    if t.name == tool_name and not t.description:
                        t.description = description
                        break

        # Pattern 3: server.tool("name", `multi-line description`, ...) with backticks
        # This is common for packages like graphlit that use template literals
        pattern_backtick = r'\.tool\s*\(\s*["\']([^"\']+)["\']\s*,\s*`([^`]+)`'
        for match in re.finditer(pattern_backtick, content, re.DOTALL):
            tool_name = match.group(1)
            if tool_name not in existing_names:
                # Clean up multi-line description: collapse whitespace
                description = ' '.join(match.group(2).split())
                # Truncate if too long
                if len(description) > 300:
                    description = description[:297] + "..."
                existing_names.add(tool_name)
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=description,
                ))
            else:
                # Update existing tool's description if empty
                for t in tools:
                    if t.name == tool_name and not t.description:
                        description = ' '.join(match.group(2).split())
                        if len(description) > 300:
                            description = description[:297] + "..."
                        t.description = description
                        break

        # Pattern 4: ListToolsRequestSchema handler (SDK pattern)
        # Look for tools array in setRequestHandler
        if "ListToolsRequestSchema" in content:
            tools.extend(self._extract_tools_from_handler(content))

        # Pattern 5: const TOOLS = [...] or export const tools = [...] arrays
        # Common in TypeScript packages with predefined tool lists
        tools_array_pattern = r'(?:const|export\s+const)\s+(?:TOOLS|tools)\s*[:=]\s*\[([^\]]+)\]'
        for match in re.finditer(tools_array_pattern, content, re.DOTALL | re.IGNORECASE):
            array_content = match.group(1)
            # Extract individual tool definitions from the array
            tool_def_pattern = r'["\']([a-z][a-z0-9_-]+)["\']'
            for tool_match in re.finditer(tool_def_pattern, array_content, re.IGNORECASE):
                tool_name = tool_match.group(1)
                if tool_name not in existing_names and len(tool_name) > 2:
                    existing_names.add(tool_name)
                    tools.append(ExtractedTool(name=tool_name, description=""))

        # Pattern 6: defineTool("name", ...) or createTool("name", ...) patterns
        define_tool_pattern = r'(?:defineTool|createTool|addTool)\s*\(\s*["\']([^"\']+)["\']'
        for match in re.finditer(define_tool_pattern, content):
            tool_name = match.group(1)
            if tool_name not in existing_names:
                existing_names.add(tool_name)
                # Try to find description nearby
                start_pos = match.end()
                config_text = content[start_pos:start_pos + 500]
                description = self._extract_string_field(config_text, "description") or ""
                tools.append(ExtractedTool(name=tool_name, description=description))

        return tools

    def _extract_tools_from_handler(self, content: str) -> list[ExtractedTool]:
        """
        Extract tools from setRequestHandler(ListToolsRequestSchema, ...) pattern.

        Parses the tools array inside the handler with flexible field order.
        """
        tools = []
        existing_names = set()

        # Pattern 1: { name: "...", description: "..." } - name first
        pattern1 = r'\{\s*name:\s*["\']([^"\']+)["\']\s*,\s*description:\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern1, content):
            tool_name = match.group(1)
            if tool_name not in existing_names:
                existing_names.add(tool_name)
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=match.group(2),
                ))

        # Pattern 2: { description: "...", name: "..." } - description first
        pattern2 = r'\{\s*description:\s*["\']([^"\']+)["\']\s*,\s*name:\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern2, content):
            tool_name = match.group(2)
            if tool_name not in existing_names:
                existing_names.add(tool_name)
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=match.group(1),
                ))

        # Pattern 3: server.tool("name", "description", ...) or similar
        pattern3 = r'\.tool\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern3, content):
            tool_name = match.group(1)
            if tool_name not in existing_names:
                existing_names.add(tool_name)
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=match.group(2),
                ))

        # Pattern 3b: server.tool("name", `multi-line description`, ...) with backticks
        # Captures template literals that may span multiple lines
        pattern3b = r'\.tool\s*\(\s*["\']([^"\']+)["\']\s*,\s*`([^`]+)`'
        for match in re.finditer(pattern3b, content, re.DOTALL):
            tool_name = match.group(1)
            if tool_name not in existing_names:
                existing_names.add(tool_name)
                # Clean up multi-line description: collapse whitespace
                description = ' '.join(match.group(2).split())
                # Truncate if too long (keep first meaningful sentence)
                if len(description) > 300:
                    description = description[:297] + "..."
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=description,
                ))

        # Pattern 4: Look for name field, then find nearby description
        # More flexible pattern for multi-line tool definitions
        name_pattern = r'name:\s*["\']([^"\']+)["\']'
        for match in re.finditer(name_pattern, content):
            tool_name = match.group(1)
            if tool_name in existing_names:
                continue

            # Look for description within 500 chars after name
            start = match.end()
            snippet = content[start:start + 500]
            desc_match = re.search(r'description:\s*["\']([^"\']+)["\']', snippet)

            if desc_match:
                existing_names.add(tool_name)
                tools.append(ExtractedTool(
                    name=tool_name,
                    description=desc_match.group(1),
                ))

        return tools

    def _extract_python_tools(self, content: str) -> list[ExtractedTool]:
        """
        Extract tools from Python content using AST.

        Looks for patterns:
        - Tool(name=..., description=..., inputSchema=...)
        - @mcp.tool decorator
        - server.tool()(function_name) - FastMCP pattern
        """
        tools = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Try extracting with regex as fallback
            return self._extract_python_tools_regex(content)

        # Build a map of function definitions with their docstrings
        # Include both sync (FunctionDef) and async (AsyncFunctionDef) functions
        func_docs: dict[str, Optional[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_docs[node.name] = ast.get_docstring(node)

        for node in ast.walk(tree):
            # Pattern 1: Tool() constructor calls
            if isinstance(node, ast.Call):
                if self._is_tool_call(node):
                    tool = self._parse_tool_call(node)
                    if tool:
                        tools.append(tool)
                # Pattern 3: server.tool()(function_name) - FastMCP immediate call
                elif self._is_fastmcp_tool_registration(node):
                    tool = self._parse_fastmcp_registration(node, func_docs)
                    if tool:
                        tools.append(tool)

            # Pattern 2: @mcp.tool or @server.tool decorators (sync and async)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if self._is_tool_decorator(decorator):
                        tool = ExtractedTool(
                            name=node.name,
                            description=ast.get_docstring(node),
                        )
                        tools.append(tool)
                    # Pattern 4: @server.list_tools() handler returning Tool list
                    elif self._is_list_tools_decorator(decorator):
                        list_tools = self._extract_tools_from_list_handler(node)
                        tools.extend(list_tools)

        # Also try regex patterns for FastMCP that might be missed by AST
        regex_tools = self._extract_fastmcp_tools_regex(content, func_docs)

        # Add tools not already found
        existing_names = {t.name for t in tools}
        for tool in regex_tools:
            if tool.name not in existing_names:
                tools.append(tool)
                existing_names.add(tool.name)

        return tools

    def _extract_python_tools_regex(self, content: str) -> list[ExtractedTool]:
        """Fallback regex extraction for Python files with syntax errors."""
        tools = []

        # Pattern for Tool() calls
        pattern = r'Tool\s*\(\s*name\s*=\s*["\']?([^"\')\s,]+)["\']?\s*,'

        for match in re.finditer(pattern, content):
            tool_name = match.group(1)

            # Try to extract description
            desc_match = re.search(
                rf'Tool\s*\([^)]*name\s*=\s*["\']?{re.escape(tool_name)}[^)]*description\s*=\s*["\']([^"\']+)["\']',
                content,
                re.DOTALL
            )
            description = desc_match.group(1) if desc_match else None

            tools.append(ExtractedTool(name=tool_name, description=description))

        return tools

    def _is_tool_call(self, node: ast.Call) -> bool:
        """Check if AST Call node is a Tool() constructor."""
        if isinstance(node.func, ast.Name):
            return node.func.id == "Tool"
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr == "Tool"
        return False

    def _is_tool_decorator(self, decorator: ast.expr) -> bool:
        """Check if decorator is @mcp.tool or @server.tool."""
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "tool"
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr == "tool"
        return False

    def _is_list_tools_decorator(self, decorator: ast.expr) -> bool:
        """Check if decorator is @server.list_tools() for MCP SDK pattern."""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr == "list_tools"
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr == "list_tools"
        return False

    def _extract_tools_from_list_handler(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[ExtractedTool]:
        """
        Extract tools from @server.list_tools() handler.

        Pattern:
            @server.list_tools()
            async def handle_list_tools():
                return [
                    types.Tool(name="...", description="..."),
                    Tool(name="...", description="..."),
                ]
        """
        tools = []

        # Walk the function body to find Tool() calls
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                # Check if it's a Tool() or types.Tool() call
                is_tool_call = False
                if isinstance(node.func, ast.Name) and node.func.id == "Tool":
                    is_tool_call = True
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "Tool":
                    is_tool_call = True

                if is_tool_call:
                    tool = self._parse_sdk_tool_call(node)
                    if tool:
                        tools.append(tool)

        return tools

    def _parse_sdk_tool_call(self, node: ast.Call) -> Optional[ExtractedTool]:
        """
        Parse types.Tool() or Tool() call from MCP SDK pattern.

        Example:
            types.Tool(
                name="read_query",
                description="Execute a SELECT query on the SQLite database",
                inputSchema={...}
            )
        """
        name = None
        description = None

        for keyword in node.keywords:
            if keyword.arg == "name":
                if isinstance(keyword.value, ast.Constant):
                    name = keyword.value.value
            elif keyword.arg == "description":
                if isinstance(keyword.value, ast.Constant):
                    description = keyword.value.value

        if name:
            return ExtractedTool(name=name, description=description)
        return None

    def _is_fastmcp_tool_registration(self, node: ast.Call) -> bool:
        """
        Check if AST Call node is a FastMCP tool registration.

        Pattern: server.tool()(function_name)
        - The outer Call has a function that is itself a Call
        - That inner Call has a func that is an Attribute with attr="tool"
        """
        if isinstance(node.func, ast.Call):
            # node.func is the server.tool() call
            inner_call = node.func
            if isinstance(inner_call.func, ast.Attribute):
                return inner_call.func.attr == "tool"
        return False

    def _parse_fastmcp_registration(
        self, node: ast.Call, func_docs: dict[str, Optional[str]]
    ) -> Optional[ExtractedTool]:
        """
        Parse FastMCP tool registration: server.tool()(function_name)

        The function being registered is the first argument to the outer call.
        """
        if not node.args:
            return None

        first_arg = node.args[0]

        # Get the function name
        func_name = None
        if isinstance(first_arg, ast.Name):
            func_name = first_arg.id
        elif isinstance(first_arg, ast.Attribute):
            func_name = first_arg.attr

        if not func_name:
            return None

        # Get docstring from function map
        description = func_docs.get(func_name)

        return ExtractedTool(
            name=func_name,
            description=description,
        )

    def _extract_fastmcp_tools_regex(
        self, content: str, func_docs: dict[str, Optional[str]]
    ) -> list[ExtractedTool]:
        """
        Extract FastMCP tool registrations using regex.

        Patterns:
        - mcp_server.tool()(function_name)
        - server.tool()(function_name)
        - app.tool()(function_name)
        - mcp.tool()(function_name)
        """
        tools = []

        # Pattern for FastMCP tool registration
        # Matches: server.tool()(func), mcp_server.tool()(func), etc.
        patterns = [
            r'(?:mcp_server|server|mcp|app)\.tool\s*\(\s*\)\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)',
            # Also match with keyword args in tool(): server.tool(name="custom")(func)
            r'(?:mcp_server|server|mcp|app)\.tool\s*\([^)]*\)\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)',
        ]

        found_names = set()
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                func_name = match.group(1)
                if func_name not in found_names:
                    found_names.add(func_name)
                    description = func_docs.get(func_name)
                    tools.append(ExtractedTool(
                        name=func_name,
                        description=description,
                    ))

        return tools

    def _parse_tool_call(self, node: ast.Call) -> Optional[ExtractedTool]:
        """Parse Tool() call and extract metadata."""
        name = None
        description = None

        for keyword in node.keywords:
            if keyword.arg == "name":
                if isinstance(keyword.value, ast.Constant):
                    name = keyword.value.value
                elif isinstance(keyword.value, ast.Attribute):
                    # Handle GitTools.STATUS style
                    name = keyword.value.attr.lower()
            elif keyword.arg == "description":
                if isinstance(keyword.value, ast.Constant):
                    description = keyword.value.value

        if name:
            return ExtractedTool(name=name, description=description)
        return None

    def _extract_string_field(self, text: str, field_name: str) -> Optional[str]:
        """Extract a string field value from JavaScript object literal."""
        # Try various patterns
        patterns = [
            rf'{field_name}\s*:\s*["\']([^"\']+)["\']',  # title: "value"
            rf'{field_name}\s*:\s*`([^`]+)`',  # title: `value`
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _detect_env_vars(self, content: str) -> set[str]:
        """Detect environment variable references in code."""
        env_vars = set()

        for pattern in self.ENV_VAR_PATTERNS:
            for match in re.finditer(pattern, content):
                env_vars.add(match.group(1))

        return env_vars

    def _detect_cli_args(self, content: str) -> set[str]:
        """Detect required CLI arguments in code."""
        cli_args = set()

        for pattern in self.CLI_ARG_PATTERNS:
            for match in re.finditer(pattern, content):
                if match.lastindex:
                    cli_args.add(match.group(1))

        return cli_args

    def _check_local_access(self, content: str) -> bool:
        """
        Check if code requires local system resources.

        Returns True only if:
        - Code uses local-only patterns (filesystem, subprocess, etc.)
        - AND does NOT have remote-capable patterns (API URLs, HTTP libs, etc.)

        Services like Grist that can connect to remote URLs are NOT local-only,
        even if they have default localhost values.
        """
        # First check for remote-capable patterns
        # If found, the service can work with remote endpoints
        for pattern in self.REMOTE_CAPABLE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return False  # Can connect to remote services

        # Check for local-only patterns
        for pattern in self.LOCAL_ACCESS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False

    def _check_dynamic_tools(self, content: str) -> bool:
        """
        Check if code uses dynamic tool registration patterns.

        Returns True if tools are loaded/registered at runtime rather than
        statically defined. This means static analysis cannot extract all tools.

        Examples:
        - registerToolsets() - Salesforce pattern
        - loadTools() - dynamic loading
        - glob patterns to find tool files
        - plugin-based tool loading
        """
        for pattern in self.DYNAMIC_TOOLS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False

    def _safe_name(self, package_name: str) -> str:
        """Convert package name to safe directory name."""
        return package_name.replace("@", "").replace("/", "_").replace("-", "_")

    def _cleanup_temp(self, package_name: str) -> None:
        """Clean up temporary files for a package."""
        pkg_dir = self.temp_dir / self._safe_name(package_name)
        if pkg_dir.exists():
            try:
                shutil.rmtree(pkg_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup {pkg_dir}: {e}")


# Convenience function for quick extraction
async def extract_tools(package_name: str, package_type: PackageType = PackageType.NPM) -> ExtractionResult:
    """
    Extract tools from an MCP server package.

    Args:
        package_name: Package name
        package_type: Type of package (npm, pip)

    Returns:
        ExtractionResult with tools and metadata

    Example:
        result = await extract_tools("@modelcontextprotocol/server-filesystem")
        print(f"Found {len(result.tools)} tools")
        for tool in result.tools:
            print(f"  - {tool.name}: {tool.description[:50]}...")
    """
    extractor = StaticToolExtractor()

    if package_type == PackageType.NPM:
        return await extractor.extract_from_npm(package_name)
    elif package_type == PackageType.PIP:
        return await extractor.extract_from_pip(package_name)
    else:
        raise ValueError(f"Unsupported package type: {package_type}")
