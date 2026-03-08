"""
MCP Server Automatic Installation Module.

Handles installation from pip, git, or local sources.
"""

import asyncio
import logging
import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, Optional, Literal
import importlib.util

logger = logging.getLogger(__name__)


class MCPInstaller:
    """Installation manager for MCP servers."""

    def __init__(self, cache_file: str = "/app/data/installed_servers.json"):
        """
        Initialize the installer.

        Args:
            cache_file: Cache file to track installations
        """
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    def _load_cache(self):
        """Load the cache of installed servers."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    self.installed = json.load(f)
            except Exception as e:
                logger.warning(f"Unable to load cache: {e}")
                self.installed = {}
        else:
            self.installed = {}

    def _save_cache(self):
        """Save the cache of installed servers."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.installed, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def is_installed(self, server_id: str, install_config: Dict) -> bool:
        """
        Check if an MCP server is already installed.

        Args:
            server_id: Server identifier
            install_config: Installation configuration

        Returns:
            True if the server is installed
        """
        # Check the cache
        if server_id in self.installed:
            cached = self.installed[server_id]
            # Check that the config hasn't changed
            if cached.get("config") == install_config:
                # Check that the module is importable
                if self._check_module_exists(install_config):
                    return True

        return False

    def _check_module_exists(self, install_config: Dict) -> bool:
        """Check that a Python module can be imported."""
        install_type = install_config.get("type")

        if install_type == "pip":
            package = install_config.get("package", "")
            # Try to import the module
            module_name = package.replace("-", "_")
            try:
                spec = importlib.util.find_spec(module_name)
                return spec is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                return False

        elif install_type in ["git", "github"]:
            # For git/github, check that the folder exists
            if install_type == "github":
                package = install_config.get("package", "")
                repo_name = package.split('/')[-1] if package else ""
            else:
                url = install_config.get("url", "")
                repo_name = url.rstrip('/').split('/')[-1].replace('.git', '')

            repo_path = Path(f"/app/mcp_servers/{repo_name}")
            return repo_path.exists()

        elif install_type == "local":
            # For local, check that the path exists
            path = install_config.get("path", "")
            return Path(path).exists()

        return False

    async def install_server(self, server_id: str, install_config: Dict) -> bool:
        """
        Install an MCP server according to its configuration.

        Args:
            server_id: Server identifier
            install_config: Installation configuration

        Returns:
            True if installation succeeded
        """
        install_type = install_config.get("type")

        logger.info(f"Installing MCP server '{server_id}' (type: {install_type})")

        try:
            if install_type == "pip":
                success = await self._install_from_pip(server_id, install_config)
            elif install_type == "git":
                success = await self._install_from_git(server_id, install_config)
            elif install_type == "github":
                success = await self._install_from_github(server_id, install_config)
            elif install_type == "local":
                success = await self._install_local(server_id, install_config)
            elif install_type == "npm":
                # NPM packages are auto-installed by npx -y, skip installation
                logger.info(f"Server '{server_id}' of type npm - npx handles installation automatically")
                success = True
            else:
                logger.error(f"Unknown installation type: {install_type}")
                return False

            if success:
                # Update the cache
                self.installed[server_id] = {
                    "config": install_config,
                    "type": install_type
                }
                self._save_cache()
                logger.info(f"✅ Server '{server_id}' installed successfully")

            return success

        except Exception as e:
            logger.error(f"Error installing '{server_id}': {e}")
            return False

    async def _install_from_pip(self, server_id: str, config: Dict) -> bool:
        """Install a package from pip."""
        package = config.get("package")
        version = config.get("version", "")

        if not package:
            logger.error(f"No package specified for '{server_id}'")
            return False

        # Build the installation command
        install_spec = f"{package}{version}" if version else package
        # Note: No --no-cache-dir so pip cache is used on subsequent installs
        cmd = [sys.executable, "-m", "pip", "install", install_spec]

        logger.info(f"Executing: {' '.join(cmd)}")

        try:
            # Use asyncio subprocess to avoid blocking the event loop during install.
            # subprocess.run() would freeze all incoming requests for the entire
            # install duration (8-10 sec for large packages like mcp_server_grist).
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=300  # 5 minutes max
                )
            except asyncio.TimeoutError:
                proc.kill()
                logger.error(f"Timeout installing '{install_spec}'")
                return False

            if proc.returncode == 0:
                logger.info(f"Package '{install_spec}' installed")
                return True
            else:
                logger.error(f"Pip error: {stderr.decode(errors='replace')}")
                return False

        except Exception as e:
            logger.error(f"Subprocess error: {e}")
            return False

    async def _install_from_github(self, server_id: str, config: Dict) -> bool:
        """Install from a GitHub repository (format: owner/repo)."""
        package = config.get("package")

        if not package:
            logger.error(f"No GitHub package specified for '{server_id}'")
            return False

        # Convert owner/repo to full GitHub URL
        github_url = f"https://github.com/{package}.git"
        branch = config.get("branch", "main")

        logger.info(f"Installing from GitHub: {github_url}")

        # Create a new config for _install_from_git
        git_config = {
            "url": github_url,
            "branch": branch
        }

        # Use the standard git method
        return await self._install_from_git(server_id, git_config)

    async def _install_from_git(self, server_id: str, config: Dict) -> bool:
        """Clone and install from a git repository."""
        url = config.get("url")
        branch = config.get("branch", "main")

        if not url:
            logger.error(f"No git URL specified for '{server_id}'")
            return False

        # Create the destination folder
        repo_name = url.rstrip('/').split('/')[-1].replace('.git', '')
        dest_path = Path(f"/app/mcp_servers/{repo_name}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Clone the repo
        if dest_path.exists():
            logger.info(f"Repository already cloned: {dest_path}")
        else:
            cmd = ["git", "clone", "-b", branch, url, str(dest_path)]
            logger.info(f"Cloning: {' '.join(cmd)}")

            rc, _, stderr = await self._run_async(cmd)
            if rc != 0:
                logger.error(f"Git clone error: {stderr}")
                return False

        # Install dependencies if requirements.txt exists
        requirements = dest_path / "requirements.txt"
        if requirements.exists():
            cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements)]
            logger.info(f"Installing dependencies: {' '.join(cmd)}")
            rc, _, stderr = await self._run_async(cmd)
            if rc != 0:
                logger.warning(f"Warning during dependency installation: {stderr}")

        # Install the package itself if setup.py or pyproject.toml exists
        setup_py = dest_path / "setup.py"
        pyproject_toml = dest_path / "pyproject.toml"

        if setup_py.exists() or pyproject_toml.exists():
            cmd = [sys.executable, "-m", "pip", "install", "-e", str(dest_path)]
            config_file = "setup.py" if setup_py.exists() else "pyproject.toml"
            logger.info(f"Installing package ({config_file}): {' '.join(cmd)}")
            rc, _, stderr = await self._run_async(cmd)
            if rc != 0:
                logger.warning(f"Warning during installation: {stderr}")
            else:
                logger.info(f"Package installed successfully")

        return True

    async def _install_local(self, server_id: str, config: Dict) -> bool:
        """Configure an MCP server from a local path."""
        path = config.get("path")

        if not path:
            logger.error(f"No path specified for '{server_id}'")
            return False

        local_path = Path(path)

        if not local_path.exists():
            logger.error(f"Local path not found: {path}")
            return False

        # Install dependencies if requirements.txt exists
        requirements = local_path / "requirements.txt"
        if requirements.exists():
            cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements)]
            logger.info(f"Installing local dependencies: {' '.join(cmd)}")
            rc, _, stderr = await self._run_async(cmd)
            if rc != 0:
                logger.warning(f"Dependencies warning: {stderr}")

        logger.info(f"Local server configured: {path}")
        return True

    async def _run_async(self, cmd: list, timeout: int = 300):
        """
        Run a subprocess command without blocking the asyncio event loop.

        Returns (returncode, stdout, stderr) all as strings.
        Using asyncio.create_subprocess_exec prevents freezing the event loop
        during long-running installs (pip/git clone can take 8-10+ seconds).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                logger.error(f"Timeout running: {' '.join(cmd)}")
                return -1, "", "timeout"
            return (
                proc.returncode,
                stdout_b.decode(errors="replace"),
                stderr_b.decode(errors="replace"),
            )
        except Exception as e:
            logger.error(f"Error running {cmd}: {e}")
            return -1, "", str(e)

    async def ensure_server_installed(self, server_id: str, server_config: Dict) -> bool:
        """
        Ensure an MCP server is installed.

        Args:
            server_id: Server identifier
            server_config: Complete server configuration

        Returns:
            True if the server is ready to use
        """
        install_config = server_config.get("install")

        if not install_config:
            logger.warning(f"No installation configuration for '{server_id}', attempting direct startup")
            return True  # Continue without installing

        # Check if already installed
        if self.is_installed(server_id, install_config):
            logger.info(f"Server '{server_id}' already installed")
            return True

        # Install the server
        return await self.install_server(server_id, install_config)
