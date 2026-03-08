"""
Discovery Service - Intelligence layer for tool discovery and composition creation.

Combines:
- Installed tools (from Registry)
- Available tools (from Marketplace)
- Credential requirements
- Auto-installation capabilities
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from uuid import UUID

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .marketplace_service import get_marketplace_service, MarketplaceSyncService
from .mcp_server_service import MCPServerService
from .credential_service import CredentialService
from .catalog_composition_planner import get_catalog_planner, CatalogCompositionPlanner
from ..models.credential_setup_token import CredentialSetupToken
from ..models.user_credential import UserCredential, OrganizationCredential


logger = logging.getLogger(__name__)


class ToolDiscoveryResult:
    """Result from tool discovery with status classification."""

    def __init__(self):
        self.ready_tools: List[Dict[str, Any]] = []
        self.needs_install: List[Dict[str, Any]] = []
        self.needs_credentials: List[Dict[str, Any]] = []


class DiscoveryService:
    """
    Service for discovering tools and managing credential requirements.

    Workflow:
    1. User expresses intent: "sync Notion to Grist"
    2. Search in installed tools + marketplace
    3. Classify results: ready / needs_install / needs_credentials
    4. Generate setup instructions or credential links
    """

    def __init__(
        self,
        db: AsyncSession,
        registry=None,  # Registry from app.core.registry
        marketplace: Optional[MarketplaceSyncService] = None
    ):
        self.db = db
        self.registry = registry
        self.marketplace = marketplace or get_marketplace_service()
        self.mcp_service = MCPServerService(db)
        self.credential_service = CredentialService(db)

        # Catalog composition planner for intelligent composition creation
        self.catalog_planner = get_catalog_planner(self.marketplace)

    async def analyze_intent(
        self,
        query: str,
        organization_id: UUID,
        user_id: UUID,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: analyze user intent and return complete requirements.

        Args:
            query: User's natural language query
            organization_id: Organization context
            user_id: User making the request
            context: Additional context (create_composition, auto_install, etc.)

        Returns:
            {
                "intent": "data_sync",
                "confidence": 0.95,
                "proposed_composition": {...},
                "requirements": {...},
                "setup_actions": [...]
            }
        """
        context = context or {}

        logger.info(f"Analyzing intent for query: '{query}'")

        # NEW APPROACH: Use catalog composition planner
        # This generates a composition FIRST, then extracts required servers
        # Result: 2-3 specific servers instead of 20 generic ones

        # 1. Plan composition using catalog tools
        plan = await self.catalog_planner.plan_composition(
            query=query,
            context=context
        )

        composition = plan.get("composition")
        required_servers = plan.get("required_servers", [])

        logger.info(
            f"Composition planned: {len(required_servers)} required servers, "
            f"{len(plan.get('workflow_steps', []))} steps"
        )

        # 2. Build discovery result with only required servers
        discovery_result = ToolDiscoveryResult()

        # Check installed tools
        if self.registry:
            try:
                all_tools = await self.registry.get_tools(refresh=False)
                for tool in all_tools:
                    if isinstance(tool, dict):
                        discovery_result.ready_tools.append(tool)
                    elif hasattr(tool, 'model_dump'):
                        discovery_result.ready_tools.append(tool.model_dump())
            except Exception as e:
                logger.error(f"Error getting installed tools: {e}")

        # Add required servers to needs_install
        installed_server_ids = {
            tool.get('server_id') for tool in discovery_result.ready_tools
        }

        for server in required_servers:
            if server['id'] not in installed_server_ids:
                discovery_result.needs_install.append({
                    "server": server,
                    "tools_preview": server.get('tools_preview', [])
                })

        # 3. Classify tools by status
        requirements = await self._classify_requirements(
            discovery_result=discovery_result,
            organization_id=organization_id,
            user_id=user_id
        )

        # 4. Build setup actions
        setup_actions = self._build_setup_actions(requirements)

        # 5. Determine if credentials setup link is needed
        credential_setup_url = None
        if requirements["needs_credentials"]:
            # We'll generate this on-demand via separate endpoint
            credential_setup_url = None  # Placeholder

        return {
            "intent": self._detect_intent_type(query),
            "confidence": 0.85,  # TODO: Implement ML-based confidence
            "proposed_composition": composition,
            "requirements": requirements,
            "setup_actions": setup_actions,
            "credential_setup_url": credential_setup_url,
            "estimated_time": plan.get("estimated_time", "Unknown")
        }

    async def _discover_tools(
        self,
        query: str,
        organization_id: UUID,
        user_id: UUID,
        limit: int = 20
    ) -> ToolDiscoveryResult:
        """
        Search for tools in both installed servers and marketplace.

        Returns tools classified by availability status.
        """
        result = ToolDiscoveryResult()

        # Search in installed tools (via Registry)
        if self.registry:
            try:
                installed_tools = await self.registry.search_tools(query, limit=limit)
                logger.info(f"Found {len(installed_tools)} installed tools")

                # Convert to dict format
                for tool in installed_tools:
                    if hasattr(tool, 'dict'):
                        result.ready_tools.append(tool.dict())
                    elif hasattr(tool, 'model_dump'):
                        result.ready_tools.append(tool.model_dump())
                    elif isinstance(tool, dict):
                        result.ready_tools.append(tool)

            except Exception as e:
                logger.error(f"Error searching installed tools: {e}")

        # Search in marketplace using semantic search
        try:
            # Use semantic search for intelligent matching
            logger.info(f"Performing semantic search in marketplace for: '{query}'")

            marketplace_servers = await self.marketplace.semantic_search(
                query=query,
                limit=limit
            )

            logger.info(
                f"Found {len(marketplace_servers)} marketplace servers via semantic search"
            )

            # Add to needs_install if not already installed
            installed_server_ids = {
                tool.get('server_id') for tool in result.ready_tools
            }

            for server in marketplace_servers:
                if server['id'] not in installed_server_ids:
                    result.needs_install.append({
                        "server": server,
                        "tools_preview": server.get('tools_preview', [])
                    })

        except Exception as e:
            logger.error(f"Error searching marketplace: {e}", exc_info=True)

        return result

    def _extract_tool_keywords(self, query: str) -> List[str]:
        """
        Extract potential tool/service names from natural language query.

        Uses simple keyword matching and capitalization detection.
        Returns list of keywords to search for in marketplace.
        """
        import re

        # Common tool/service names to look for (case-insensitive)
        known_tools = [
            'notion', 'grist', 'github', 'gitlab', 'slack', 'gmail', 'google',
            'postgresql', 'mysql', 'sqlite', 'redis', 'mongodb', 'brave',
            'puppeteer', 'playwright', 'filesystem', 'memory', 'fetch',
            'aws', 'cloudflare', 'linear', 'sentry', 'everart', 'sequential',
            'time', 'filesystem', 'email', 'calendar', 'database', 'spreadsheet'
        ]

        query_lower = query.lower()
        keywords = []

        # Find known tools in query
        for tool in known_tools:
            if tool in query_lower:
                keywords.append(tool)

        # Extract capitalized words (likely proper nouns = tool names)
        capitalized = re.findall(r'\b[A-Z][a-z]+\b', query)
        keywords.extend([w.lower() for w in capitalized])

        # If no keywords found, use intent-based keywords
        if not keywords:
            # Map intent keywords to search terms
            if any(word in query_lower for word in ['sync', 'synchronise', 'synchronize']):
                # For sync queries, return generic terms
                keywords.append('database')
                keywords.append('api')
            elif any(word in query_lower for word in ['email', 'mail']):
                keywords.append('gmail')
                keywords.append('email')
            elif any(word in query_lower for word in ['document', 'note', 'wiki']):
                keywords.append('notion')
                keywords.append('filesystem')

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords or ['']  # Return empty string if nothing found

    async def _classify_requirements(
        self,
        discovery_result: ToolDiscoveryResult,
        organization_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Classify discovered tools by their requirements.

        Returns:
            {
                "ready_tools": [...],      # Can use immediately
                "needs_install": [...],     # Need MCP server installation
                "needs_credentials": [...]  # Need credential configuration
            }
        """
        ready_tools = []
        needs_install = []
        needs_credentials = []

        # Check installed tools for credential requirements
        for tool_data in discovery_result.ready_tools:
            server_id = tool_data.get('server_id')

            if not server_id:
                # Tool doesn't specify server, assume ready
                ready_tools.append(tool_data)
                continue

            # Check if credentials are configured
            has_credentials = await self._check_credentials_configured(
                server_id=server_id,
                organization_id=organization_id,
                user_id=user_id
            )

            if has_credentials:
                ready_tools.append({
                    "tool_id": tool_data.get('id') or tool_data.get('name'),
                    "server_id": server_id,
                    "status": "ready",
                    "credentials_configured": True
                })
            else:
                # Get credential requirements from marketplace
                server_info = await self.marketplace.get_server(server_id)
                if server_info and server_info.get('credentials'):
                    needs_credentials.append({
                        "server_id": server_id,
                        "server_name": server_info.get('name', server_id),
                        "credentials": server_info['credentials']
                    })

        # Process servers that need installation
        for item in discovery_result.needs_install:
            server = item['server']

            needs_install.append({
                "server_id": server['id'],
                "server_name": server['name'],
                "install_type": server['install_type'],
                "install_package": server['install_package'],
                "tools_preview": item['tools_preview'],
                "credentials_required": server.get('credentials', [])
            })

            # Also add to credentials list if credentials are required
            if server.get('credentials'):
                needs_credentials.append({
                    "server_id": server['id'],
                    "server_name": server['name'],
                    "credentials": server['credentials']
                })

        return {
            "ready_tools": ready_tools,
            "needs_install": needs_install,
            "needs_credentials": needs_credentials
        }

    async def _check_credentials_configured(
        self,
        server_id: str,
        organization_id: UUID,
        user_id: UUID
    ) -> bool:
        """
        Check if credentials are configured for a server.

        For Team Services: checks merged credentials (org + user)
        For Personal servers: checks only user credentials
        """
        try:
            # Get server to check if it's a Team server
            from sqlalchemy import select
            from ..models.mcp_server import MCPServer

            result = await self.db.execute(
                select(MCPServer).where(MCPServer.id == server_id)
            )
            server = result.scalar_one_or_none()

            if not server:
                return False

            # Check if this is a Team server
            is_team_server = (server.env or {}).get('_IS_TEAM_SERVER') == 'true'

            if is_team_server:
                # Team server: check merged credentials
                credentials = await self.credential_service.resolve_credentials_merged(
                    user_id=user_id,
                    server_id=server_id,
                    organization_id=organization_id
                )
            else:
                # Personal server: check ONLY user credentials
                user_cred = await self.credential_service._get_user_credential(user_id, server_id)
                credentials = user_cred.credentials if user_cred and user_cred.is_active else None

            return bool(credentials)
        except Exception as e:
            logger.error(f"Error checking credentials for {server_id}: {e}")
            return False

    def _build_setup_actions(self, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate ordered list of setup actions needed.

        Returns list of actions in execution order.
        """
        actions = []
        step = 1

        # Group servers by install requirement
        servers_to_install = {
            item['server_id']: item for item in requirements['needs_install']
        }

        servers_needing_creds = {
            item['server_id']: item for item in requirements['needs_credentials']
        }

        # Process each server that needs attention
        all_servers = set(servers_to_install.keys()) | set(servers_needing_creds.keys())

        for server_id in all_servers:
            # Step 1: Install if needed
            if server_id in servers_to_install:
                server_info = servers_to_install[server_id]
                actions.append({
                    "step": step,
                    "action": "install_server",
                    "server_id": server_id,
                    "server_name": server_info['server_name'],
                    "install_type": server_info['install_type'],
                    "install_package": server_info['install_package'],
                    "estimated_time": "30s"
                })
                step += 1

            # Step 2: Configure credentials if needed
            if server_id in servers_needing_creds:
                cred_info = servers_needing_creds[server_id]
                actions.append({
                    "step": step,
                    "action": "configure_credentials",
                    "server_id": server_id,
                    "server_name": cred_info['server_name'],
                    "credentials": [c['name'] for c in cred_info['credentials']],
                    "credential_count": len(cred_info['credentials'])
                })
                step += 1

        # Final step: Execute/test composition
        if requirements['ready_tools'] or servers_to_install or servers_needing_creds:
            actions.append({
                "step": step,
                "action": "test_composition",
                "description": "Test the complete workflow"
            })

        return actions

    async def _propose_composition(
        self,
        query: str,
        requirements: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a composition proposal based on discovered tools.

        TODO: Integrate with IntentAnalyzer or use LLM for composition generation.
        """
        # For now, return a simple structure
        # In production, this would call IntentAnalyzer or similar
        return {
            "name": f"Composition: {query[:50]}",
            "description": f"Auto-generated composition for: {query}",
            "steps": [
                # TODO: Generate actual steps from tools
            ]
        }

    def _detect_intent_type(self, query: str) -> str:
        """
        Detect the type of intent from query.

        Returns: data_sync, notification, search, automation, etc.
        """
        query_lower = query.lower()

        # Simple keyword-based detection
        # TODO: Use ML model for better classification
        if any(word in query_lower for word in ['sync', 'synchronise', 'synchronize', 'copy']):
            return "data_sync"
        elif any(word in query_lower for word in ['notify', 'alert', 'send', 'message']):
            return "notification"
        elif any(word in query_lower for word in ['search', 'find', 'query', 'get']):
            return "data_retrieval"
        elif any(word in query_lower for word in ['create', 'add', 'new']):
            return "data_creation"
        elif any(word in query_lower for word in ['update', 'modify', 'change']):
            return "data_update"
        elif any(word in query_lower for word in ['delete', 'remove', 'clean']):
            return "data_deletion"
        else:
            return "general_automation"

    async def create_credential_setup_token(
        self,
        user_id: UUID,
        organization_id: UUID,
        required_credentials: Dict[str, Any],
        composition_id: Optional[str] = None,
        callback_url: Optional[str] = None,
        webhook_url: Optional[str] = None,
        expires_in_seconds: int = 3600,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CredentialSetupToken:
        """
        Generate a secure token for credential configuration.

        Returns token with setup URL for user to configure credentials.
        """
        token = CredentialSetupToken.create_token(
            user_id=user_id,
            organization_id=organization_id,
            required_credentials=required_credentials,
            composition_id=composition_id,
            callback_url=callback_url,
            webhook_url=webhook_url,
            expires_in_seconds=expires_in_seconds,
            created_from="api",
            metadata=metadata
        )

        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)

        logger.info(
            f"Created credential setup token {token.id} for user {user_id}, "
            f"expires at {token.expires_at}"
        )

        return token

    async def get_token(self, token_str: str) -> Optional[CredentialSetupToken]:
        """Get credential setup token by token string."""
        stmt = select(CredentialSetupToken).where(
            CredentialSetupToken.token == token_str
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def complete_credential_setup(
        self,
        token_str: str,
        credentials_data: Dict[str, Dict[str, str]],
        aliases: Dict[str, str] = None,
        test_connection: bool = True
    ) -> Dict[str, Any]:
        """
        Complete credential setup from token.

        Args:
            token_str: Token string from URL
            credentials_data: Dict of {server_id: {credential_name: value}}
            aliases: Optional dict of {server_id: 'alias_name'} for server instances
            test_connection: Whether to test credentials after saving

        Returns:
            {
                "success": bool,
                "credentials_saved": [...],
                "test_results": {...},
                "composition_ready": bool
            }
        """
        if aliases is None:
            aliases = {}
        # Get token
        token = await self.get_token(token_str)

        if not token:
            raise ValueError("Token not found")

        if not token.is_valid:
            raise ValueError(
                f"Token is invalid: "
                f"{'already used' if token.is_used else 'expired'}"
            )

        # Save credentials for each server AND track server bindings
        credentials_saved = []
        server_bindings = {}  # Maps server_id → server_uuid for composition

        # Get server metadata from token
        required_servers = token.required_credentials.get("servers", [])
        server_metadata_map = {s["server_id"]: s for s in required_servers}

        for server_id, creds in credentials_data.items():
            try:
                # Ensure MCP server record exists (deduplicate by credentials)
                server_uuid = await self._ensure_mcp_server_exists(
                    organization_id=token.organization_id,
                    server_id=server_id,
                    server_metadata=server_metadata_map.get(server_id, {}),
                    credentials=creds,  # Pass credentials for deduplication
                    alias=aliases.get(server_id)  # Pass user-provided alias if any
                )

                # Track server binding for composition
                server_bindings[server_id] = str(server_uuid)

                # Check if credentials already exist
                all_creds = await self.credential_service.get_user_credentials(
                    user_id=token.user_id,
                    organization_id=token.organization_id
                )

                # Filter for specific server (by UUID)
                existing_creds = [c for c in all_creds if c.server_id == server_uuid]

                if existing_creds:
                    # Update existing credentials
                    await self.credential_service.update_user_credential(
                        user_id=token.user_id,
                        server_id=server_uuid,
                        credentials=creds
                    )
                else:
                    # Create new credentials
                    await self.credential_service.create_user_credential(
                        user_id=token.user_id,
                        organization_id=token.organization_id,
                        server_id=server_uuid,
                        credentials=creds
                    )

                test_result = "success"
                if test_connection:
                    # TODO: Implement credential testing
                    test_result = "not_tested"

                credentials_saved.append({
                    "server_id": server_id,
                    "server_uuid": str(server_uuid),
                    "test_result": test_result
                })

                logger.info(
                    f"Saved credentials for server {server_id} → {server_uuid} "
                    f"for user {token.user_id}"
                )

            except Exception as e:
                logger.error(f"Error saving credentials for {server_id}: {e}")
                credentials_saved.append({
                    "server_id": server_id,
                    "error": str(e)
                })

        # Save server bindings to composition (if composition_id present)
        if token.composition_id:
            await self._save_server_bindings_to_composition(
                composition_id=token.composition_id,
                server_bindings=server_bindings
            )
            logger.info(
                f"💾 Saved server bindings to composition {token.composition_id}: "
                f"{server_bindings}"
            )

        # Mark token as used
        token.mark_as_used()
        await self.db.commit()

        # Trigger webhook if configured
        if token.webhook_url:
            # Fire and forget - don't block the response
            asyncio.create_task(
                self._send_webhook_notification(
                    webhook_url=token.webhook_url,
                    token=token,
                    credentials_saved=credentials_saved,
                    composition_id=composition_id
                )
            )

        return {
            "success": True,
            "credentials_saved": credentials_saved,
            "composition_ready": len(credentials_saved) > 0,
            "redirect_url": token.callback_url,
            "message": "✅ Credentials configured successfully!"
        }

    async def _send_webhook_notification(
        self,
        webhook_url: str,
        token: CredentialSetupToken,
        credentials_saved: List[Dict[str, Any]],
        composition_id: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Send webhook notification with exponential backoff retry logic.

        Args:
            webhook_url: URL to send webhook to
            token: Setup token with context
            credentials_saved: List of saved credentials info
            composition_id: Associated composition ID
            max_retries: Maximum retry attempts (default: 3)
        """
        payload = {
            "event": "credentials_configured",
            "token_id": str(token.id),
            "user_id": str(token.user_id),
            "organization_id": str(token.organization_id),
            "composition_id": composition_id,
            "credentials_saved": credentials_saved,
            "timestamp": datetime.now().isoformat(),
            "meta": token.meta
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MCPHub-Webhook/1.0"
        }

        for attempt in range(max_retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=10)  # 10s timeout
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        webhook_url,
                        json=payload,
                        headers=headers
                    ) as response:
                        if response.status >= 200 and response.status < 300:
                            logger.info(
                                f"✅ Webhook sent successfully to {webhook_url} "
                                f"(status: {response.status}, attempt: {attempt + 1})"
                            )
                            return
                        else:
                            response_text = await response.text()
                            logger.warning(
                                f"⚠️  Webhook returned {response.status} from {webhook_url}: {response_text[:200]}"
                            )

                            # Retry on 5xx errors, not on 4xx (client errors)
                            if response.status < 500:
                                logger.error(f"❌ Webhook failed with client error, not retrying")
                                return

            except asyncio.TimeoutError:
                logger.warning(f"⏱️  Webhook timeout to {webhook_url} (attempt {attempt + 1}/{max_retries + 1})")

            except aiohttp.ClientError as e:
                logger.warning(f"🔌 Webhook connection error to {webhook_url}: {e} (attempt {attempt + 1}/{max_retries + 1})")

            except Exception as e:
                logger.error(f"❌ Unexpected error sending webhook: {e}")
                return

            # Exponential backoff: 1s, 2s, 4s
            if attempt < max_retries:
                backoff_delay = 2 ** attempt
                logger.info(f"⏳ Retrying webhook in {backoff_delay}s...")
                await asyncio.sleep(backoff_delay)

        logger.error(f"❌ Webhook failed after {max_retries + 1} attempts: {webhook_url}")

    async def _save_server_bindings_to_composition(
        self,
        composition_id: str,
        server_bindings: Dict[str, str]
    ):
        """
        Save server bindings to a composition.

        This allows the composition to know which specific server instances to use
        during execution (e.g., notion_personal vs notion_work).

        Args:
            composition_id: Composition ID
            server_bindings: Dict mapping server_id → server_uuid
        """
        from ..orchestration.composition_store import get_composition_store

        store = get_composition_store()
        composition = await store.get(composition_id)

        if not composition:
            logger.warning(f"Composition {composition_id} not found, cannot save bindings")
            return

        # Update server bindings
        composition.server_bindings = server_bindings
        composition.updated_at = datetime.now().isoformat()

        # Save back to store (will persist if permanent)
        if composition.status == "temporary":
            await store.save_temporary(composition, ttl=composition.ttl or 3600)
        else:
            await store.save_permanent(composition)

        logger.info(
            f"✅ Updated composition {composition_id} with server bindings: "
            f"{server_bindings}"
        )

    def _compute_credential_hash(self, credentials: Dict[str, Any]) -> str:
        """
        Compute a stable hash of credentials for deduplication.

        Args:
            credentials: Dictionary of credential values

        Returns:
            SHA256 hash (first 16 chars) of sorted credential keys+values
        """
        import hashlib
        import json

        # Sort keys for stable hashing
        sorted_creds = json.dumps(credentials, sort_keys=True)
        hash_obj = hashlib.sha256(sorted_creds.encode())
        return hash_obj.hexdigest()[:16]

    async def _ensure_mcp_server_exists(
        self,
        organization_id: UUID,
        server_id: str,
        server_metadata: Dict[str, Any],
        credentials: Dict[str, Any],
        alias: Optional[str] = None
    ) -> UUID:
        """
        Find or create MCP server with specific credentials (deduplication by credentials).

        This allows multiple instances of the same server type with different credentials.
        Example: notion-account-perso, notion-account-pro

        Args:
            organization_id: Organization UUID
            server_id: Server string ID (e.g., "notion", "grist-mcp")
            server_metadata: Metadata from marketplace/token
            credentials: Actual credential values for deduplication
            alias: Optional user-friendly alias (e.g., "personal", "work")

        Returns:
            Server UUID for use in credential creation
        """
        from ..models.mcp_server import MCPServer, InstallType

        # Compute credential hash for deduplication
        cred_hash = self._compute_credential_hash(credentials)
        unique_server_id = f"{server_id}_{cred_hash}"

        # Check if server with these exact credentials already exists
        stmt = select(MCPServer).where(
            MCPServer.organization_id == organization_id,
            MCPServer.server_id == unique_server_id
        )
        result = await self.db.execute(stmt)
        existing_server = result.scalar_one_or_none()

        if existing_server:
            logger.info(
                f"♻️  Reusing existing MCP server with matching credentials: "
                f"{server_id} -> {existing_server.id}"
            )
            return existing_server.id

        # Create new server instance with unique ID
        server_name = server_metadata.get("server_name", server_id)
        install_type = InstallType.NPM  # Default

        # Try to get install info from metadata
        if "install_type" in server_metadata:
            install_type = InstallType(server_metadata["install_type"].upper())

        install_package = server_metadata.get("install_package", f"mcp-server-{server_id}")

        # Generate display name and alias
        # Alias: user-provided or default to short hash
        final_alias = alias or cred_hash[:8]
        display_name = f"{server_name} ({final_alias})"

        server = MCPServer(
            organization_id=organization_id,
            server_id=unique_server_id,  # Unique per credentials
            name=display_name,  # Human-readable with alias
            alias=final_alias,  # Store alias for tool namespacing
            install_type=install_type,
            install_package=install_package,
            command="npx" if install_type == InstallType.NPM else "python",
            args=["-m", install_package] if install_type == InstallType.PIP else ["-y", install_package]
        )

        self.db.add(server)
        await self.db.flush()  # Get ID without committing

        logger.info(
            f"✨ Created new MCP server instance: {unique_server_id} (alias: {final_alias}) -> {server.id}"
        )

        return server.id


# Singleton-like access
_discovery_service: Optional[DiscoveryService] = None


def get_discovery_service(
    db: AsyncSession,
    registry=None
) -> DiscoveryService:
    """Get or create discovery service instance."""
    return DiscoveryService(db=db, registry=registry)
