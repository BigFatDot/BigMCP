"""
Catalog Composition Planner
============================

Creates compositions from catalog tools using LLM API.

This service:
1. Analyzes user intent and generates a concrete composition
2. Extracts required MCP servers from the composition
3. Searches the marketplace catalog for these servers
4. Returns a composition with only the necessary servers (2-3 instead of 20)

The key difference from discovery_service is that we:
- Create a composition FIRST (with concrete steps and tools)
- Extract servers FROM the composition
- Only return servers that are actually needed for the planned workflow
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

import requests

from .marketplace_service import MarketplaceSyncService

logger = logging.getLogger(__name__)


class CatalogCompositionPlanner:
    """
    Plans compositions using catalog tools.

    Uses LLM API (Mistral, OpenAI, etc.) to generate intelligent compositions,
    then extracts required MCP servers from the composition.
    """

    def __init__(self, marketplace: MarketplaceSyncService):
        """
        Initialize planner.

        Args:
            marketplace: Marketplace service for server lookup
        """
        self.marketplace = marketplace

        # LLM API configuration (compatible with Mistral, OpenAI, etc.)
        self.llm_api_url = os.environ.get("LLM_API_URL", "https://api.mistral.ai/v1")
        self.llm_api_key = os.environ.get("LLM_API_KEY", "")
        self.llm_model = os.environ.get("LLM_MODEL", "mistral-small-latest")

        if not self.llm_api_key:
            logger.warning("LLM_API_KEY not set, composition planning will fail")

    async def plan_composition(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan a composition from catalog tools.

        Process:
        1. Use LLM API to generate composition from query
        2. Extract MCP servers needed for the composition
        3. Search marketplace for these specific servers
        4. Return composition + required servers

        Args:
            query: User's natural language query
            context: Optional context (user preferences, etc.)

        Returns:
            {
                "composition": {...},  # Generated composition
                "required_servers": [...],  # Only 2-3 servers needed
                "workflow_steps": [...],  # Detailed steps
                "estimated_time": "2-3 minutes"
            }
        """
        logger.info(f"Planning composition for query: '{query}'")

        try:
            # Step 1: Generate composition using LLM
            composition = await self._generate_composition_with_llm(query, context)

            if not composition or not composition.get("steps"):
                logger.warning("Failed to generate composition from LLM API")
                return {
                    "composition": None,
                    "required_servers": [],
                    "workflow_steps": [],
                    "error": "Could not generate composition"
                }

            # Step 2: Extract MCP servers from composition
            required_servers = await self._extract_required_servers(composition)

            logger.info(
                f"Composition generated with {len(composition.get('steps', []))} steps, "
                f"requiring {len(required_servers)} servers"
            )

            return {
                "composition": composition,
                "required_servers": required_servers,
                "workflow_steps": composition.get("steps", []),
                "estimated_time": self._estimate_execution_time(composition)
            }

        except Exception as e:
            logger.error(f"Error planning composition: {e}", exc_info=True)
            return {
                "composition": None,
                "required_servers": [],
                "workflow_steps": [],
                "error": str(e)
            }

    async def _generate_composition_with_llm(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a composition using LLM API.

        Sends a prompt to the LLM asking it to create a workflow composition
        based on the user's query.

        Args:
            query: User query
            context: Optional context

        Returns:
            Composition dict with steps, tools, parameters
        """
        # Build the prompt for LLM
        prompt = self._build_composition_prompt(query, context)

        try:
            # Call LLM API
            chat_url = f"{self.llm_api_url}/chat/completions" if "/v1" in self.llm_api_url else f"{self.llm_api_url}/v1/chat/completions"

            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert workflow automation assistant. Your task is to create MCP (Model Context Protocol) compositions - structured workflows that use MCP tools to accomplish user goals."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,  # Lower temperature for more deterministic output
                "max_tokens": 2000
            }

            logger.debug(f"Calling LLM API for composition generation")

            response = requests.post(
                chat_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text}")
                return {}

            result = response.json()

            # Extract composition from response
            composition_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not composition_text:
                logger.warning("Empty response from LLM API")
                return {}

            # Parse composition from JSON in response
            composition = self._parse_composition_from_text(composition_text)

            return composition

        except Exception as e:
            logger.error(f"Error calling LLM API: {e}", exc_info=True)
            return {}

    def _build_composition_prompt(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build the prompt for LLM to generate a composition.

        The prompt includes:
        - User query
        - Available MCP server types
        - Expected output format (JSON composition)
        """
        prompt = f"""Create a workflow composition to accomplish this task:

**User Request:** {query}

**Available MCP Server Types:**
- Notion (notion-mcp-server): Access Notion databases, pages, blocks
- Grist (grist-mcp): Spreadsheet operations, data management
- GitHub (github-mcp): Repository operations, issues, PRs
- GitLab (gitlab-mcp): GitLab operations
- Slack (slack-mcp-server): Send messages, manage channels
- Gmail (gmail-mcp): Email operations
- PostgreSQL/MySQL (database servers): Database operations
- Filesystem (filesystem-mcp): File operations
- Browser (browser-mcp): Web scraping, automation
- Memory (memory-mcp): Persistent key-value storage

**Output Format (JSON):**
Return ONLY a JSON object with this structure:
```json
{{
  "name": "Descriptive workflow name",
  "description": "What this composition does",
  "steps": [
    {{
      "step_id": "1",
      "tool": "server_name.tool_name",
      "description": "What this step does",
      "parameters": {{
        "param1": "value or ${{input.param_name}} or ${{step_1.output}}"
      }},
      "optional": false
    }}
  ],
  "input_schema": {{
    "required": ["param1"],
    "properties": {{
      "param1": {{"type": "string", "description": "Description"}}
    }}
  }},
  "required_servers": ["notion-mcp-server", "grist-mcp"]
}}
```

**Important:**
1. Use realistic tool names like "notion.get_database", "grist.add_records"
2. Chain steps using ${{step_X.output}} for data flow
3. List ALL required MCP servers in "required_servers"
4. Keep it practical and executable
5. Return ONLY the JSON, no markdown, no explanation"""

        return prompt

    def _parse_composition_from_text(self, text: str) -> Dict[str, Any]:
        """
        Parse composition from LLM's response.

        Extracts JSON from markdown code blocks or raw text.
        """
        import json

        # Try to extract JSON from markdown code block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to extract JSON without markdown
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse composition JSON from LLM response")
        return {}

    async def _extract_required_servers(
        self,
        composition: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract MCP servers required by the composition.

        Two sources:
        1. Explicit "required_servers" field
        2. Parsing tool names from steps (e.g., "notion.get_database" → "notion")

        Args:
            composition: The generated composition

        Returns:
            List of server dicts from marketplace
        """
        required_server_names: Set[str] = set()

        # Source 1: Explicit required_servers field
        explicit_servers = composition.get("required_servers", [])
        required_server_names.update(explicit_servers)

        # Source 2: Extract from step tool names
        for step in composition.get("steps", []):
            tool = step.get("tool", "")
            if "." in tool:
                # Format: "server_name.tool_name"
                server_name = tool.split(".")[0]
                required_server_names.add(server_name)
            elif "_" in tool:
                # Format: "server_name_tool_name"
                server_name = tool.rsplit("_", 1)[0]
                required_server_names.add(server_name)

        logger.info(f"Extracted required server names: {required_server_names}")

        # Search marketplace for these specific servers
        required_servers = []

        for server_name in required_server_names:
            # Strategy 1: Try exact ID match first
            logger.info(f"Trying to find server '{server_name}'...")
            server = await self._find_server_by_id(server_name)

            if server:
                required_servers.append(server)
                logger.info(f"✅ Found server by exact ID match '{server_name}': {server.get('name')}")
                continue
            else:
                logger.warning(f"Exact ID match failed for '{server_name}', falling back to semantic search")

            # Strategy 2: Use semantic search to find the server
            # This handles variations like "notion" → "notion-mcp-server"
            servers = await self.marketplace.semantic_search(
                query=server_name,
                limit=1  # Only need the best match
            )

            if servers:
                required_servers.append(servers[0])
                logger.info(f"Found server by semantic search '{server_name}': {servers[0].get('name')}")
            else:
                logger.warning(f"Could not find server for '{server_name}' in marketplace")

        return required_servers

    def _generate_id_variations(self, server_id: str) -> List[str]:
        """
        Generate common ID variations for fuzzy matching.

        Examples:
        - "notion-mcp-server" → ["notion", "notion-mcp"]
        - "slack-mcp" → ["slack", "slack-server"]
        - "grist-mcp-server" → ["grist", "grist-mcp"]
        """
        variations = []

        # Remove common suffixes
        suffixes_to_remove = ["-mcp-server", "-mcp", "-server"]
        for suffix in suffixes_to_remove:
            if server_id.endswith(suffix):
                base = server_id[:-len(suffix)]
                variations.append(base)

        # Remove common prefixes (less common but worth trying)
        prefixes_to_remove = ["mcp-server-", "mcp-"]
        for prefix in prefixes_to_remove:
            if server_id.startswith(prefix):
                base = server_id[len(prefix):]
                variations.append(base)

        return variations

    async def _find_server_by_id(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Try to find a server by exact ID match with fuzzy variations.

        Tries in order:
        1. Exact match
        2. Lowercase match
        3. Fuzzy variations (removing -mcp-server, -mcp, etc.)
        4. Returns None (caller will use semantic search)

        Args:
            server_id: Server ID to search for

        Returns:
            Server dict if found, None otherwise
        """
        try:
            # Get all servers from marketplace
            await self.marketplace.sync()  # Ensure synced
            servers = self.marketplace._servers

            logger.info(f"Searching '{server_id}' in {len(servers)} servers. Sample IDs: {list(servers.keys())[:5]}")

            # Try exact match
            if server_id in servers:
                logger.info(f"Exact match found for '{server_id}'!")
                return servers[server_id].to_dict()

            # Try lowercase match
            server_id_lower = server_id.lower()
            for sid, server in servers.items():
                if sid.lower() == server_id_lower:
                    logger.info(f"Lowercase match found: '{sid}' for '{server_id}'")
                    return server.to_dict()

            # Try fuzzy variations (e.g., "notion-mcp-server" → "notion")
            variations = self._generate_id_variations(server_id)
            for variation in variations:
                if variation in servers:
                    logger.info(f"Fuzzy match found: '{variation}' for '{server_id}'")
                    return servers[variation].to_dict()
                # Try lowercase variations
                for sid, server in servers.items():
                    if sid.lower() == variation.lower():
                        logger.info(f"Fuzzy lowercase match: '{sid}' for '{server_id}' (via '{variation}')")
                        return server.to_dict()

            logger.warning(f"No exact match for '{server_id}'")
            return None

        except Exception as e:
            logger.error(f"Error finding server by ID: {e}", exc_info=True)
            return None

    def _estimate_execution_time(self, composition: Dict[str, Any]) -> str:
        """
        Estimate execution time based on composition complexity.

        Simple heuristic: ~30s per step
        """
        num_steps = len(composition.get("steps", []))

        if num_steps == 0:
            return "< 1 minute"
        elif num_steps <= 2:
            return "1-2 minutes"
        elif num_steps <= 5:
            return "2-5 minutes"
        else:
            return f"{num_steps // 2}-{num_steps} minutes"


# Singleton instance
_catalog_planner: Optional[CatalogCompositionPlanner] = None


def get_catalog_planner(marketplace: MarketplaceSyncService) -> CatalogCompositionPlanner:
    """Get or create catalog composition planner singleton."""
    global _catalog_planner

    if _catalog_planner is None:
        _catalog_planner = CatalogCompositionPlanner(marketplace=marketplace)

    return _catalog_planner
