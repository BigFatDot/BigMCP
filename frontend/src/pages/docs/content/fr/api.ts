/**
 * Documentation Référence API - Contenu en français
 *
 * Documentation complète de l'API REST BigMCP.
 */

export const apiContent: Record<string, string> = {
  'api-overview': `
# Vue d'ensemble de l'API

BigMCP propose deux façons d'interagir programmatiquement :

1. **Passerelle MCP** - Protocole MCP complet sur SSE pour les clients IA
2. **API REST** - Endpoints HTTP pour les outils, compositions et gestion

## URLs de base

| Environnement | URL de base |
|---------------|-------------|
| Cloud | \`https://bigmcp.cloud\` |
| Auto-hébergé | \`https://votre-domaine.com\` |

## Authentification

Toutes les requêtes API nécessitent une authentification via clé API :

\`\`\`bash
Authorization: Bearer mcphub_sk_votre_cle_api_ici
\`\`\`

Obtenez votre clé API depuis **Paramètres** → **Clés API** dans BigMCP.

## Passerelle MCP vs API REST

| Fonctionnalité | Passerelle MCP | API REST |
|----------------|----------------|----------|
| Protocole | SSE + JSON-RPC 2.0 | HTTP REST |
| Endpoint | \`/mcp/sse\` | \`/api/v1/*\` |
| Cas d'usage | Clients IA (Claude, etc.) | Automatisation, intégrations |
| Streaming | Oui | Non |
| Découverte d'outils | Intégrée | Endpoint séparé |

## Format de réponse

Toutes les réponses de l'API REST utilisent JSON :

\`\`\`json
{
  "success": true,
  "data": { ... },
  "error": null
}
\`\`\`

Réponses d'erreur :

\`\`\`json
{
  "detail": "Message d'erreur",
  "error_code": "INVALID_REQUEST"
}
\`\`\`

## Codes de statut HTTP

| Code | Signification |
|------|---------------|
| 200 | Succès |
| 201 | Créé |
| 400 | Requête invalide |
| 401 | Non autorisé (clé API invalide/manquante) |
| 403 | Interdit (permissions insuffisantes) |
| 404 | Non trouvé |
| 422 | Erreur de validation |
| 429 | Limite de débit atteinte |
| 500 | Erreur serveur |

## Limites de débit

| Plan | Requêtes/min | Concurrent |
|------|--------------|------------|
| Personnel | 60 | 5 |
| Team | 300 | 20 |
| Enterprise / Auto-hébergé | Illimité | Illimité |

## Scopes

Les clés API ont des scopes qui limitent l'accès :

| Scope | Autorise |
|-------|----------|
| \`tools:read\` | Lister les outils, voir les métadonnées |
| \`tools:execute\` | Exécuter les outils et compositions |
| \`credentials:read\` | Voir les infos des identifiants |
| \`credentials:write\` | Créer/modifier des identifiants |
| \`servers:read\` | Voir les configs serveur |
| \`servers:write\` | Gérer les serveurs |
| \`admin\` | Accès complet |
`,

  'api-marketplace': `
# API Marketplace

Découvrez et recherchez des serveurs MCP dans le marketplace.

## Lister les serveurs

\`\`\`http
GET /api/v1/marketplace/servers
\`\`\`

### Paramètres de requête

| Paramètre | Type | Description |
|-----------|------|-------------|
| \`category\` | string | Filtrer par catégorie |
| \`search\` | string | Recherche textuelle |
| \`source\` | string | Filtrer par source (local, npm, github) |
| \`limit\` | int | Résultats par page (défaut: 50) |
| \`offset\` | int | Décalage de pagination |

### Réponse

\`\`\`json
{
  "servers": [
    {
      "package_name": "@anthropic/mcp-server-github",
      "name": "GitHub MCP Server",
      "description": "Intégration GitHub avec issues, PRs et plus",
      "version": "1.2.0",
      "category": "development",
      "source": "npm",
      "icon_url": "https://cdn.simpleicons.org/github/white",
      "tools_count": 15,
      "downloads": 5420,
      "stars": 128,
      "verified": true
    }
  ],
  "total": 127,
  "limit": 50,
  "offset": 0
}
\`\`\`

## Obtenir les détails d'un serveur

\`\`\`http
GET /api/v1/marketplace/servers/{package_name}
\`\`\`

### Réponse

\`\`\`json
{
  "package_name": "@anthropic/mcp-server-github",
  "name": "GitHub MCP Server",
  "description": "Intégration GitHub complète...",
  "version": "1.2.0",
  "author": "Anthropic",
  "repository": "https://github.com/anthropics/mcp-server-github",
  "tools": [
    {
      "name": "create_issue",
      "description": "Créer une nouvelle issue GitHub",
      "parameters": {
        "type": "object",
        "properties": {
          "repo": {"type": "string"},
          "title": {"type": "string"},
          "body": {"type": "string"}
        },
        "required": ["repo", "title"]
      }
    }
  ],
  "required_credentials": [
    {
      "name": "GITHUB_TOKEN",
      "description": "Token d'accès personnel",
      "required": true
    }
  ]
}
\`\`\`

## Recherche sémantique

\`\`\`http
POST /api/v1/marketplace/search
\`\`\`

### Requête

\`\`\`json
{
  "query": "créer des documents dans Google Docs",
  "limit": 10
}
\`\`\`

### Réponse

\`\`\`json
{
  "results": [
    {
      "package_name": "@anthropic/mcp-server-gdocs",
      "name": "Google Docs",
      "relevance_score": 0.92,
      "matched_tools": ["create_document", "update_document"]
    }
  ]
}
\`\`\`

## Obtenir les catégories

\`\`\`http
GET /api/v1/marketplace/categories
\`\`\`

### Réponse

\`\`\`json
{
  "categories": [
    {"id": "development", "name": "Développement", "count": 32},
    {"id": "productivity", "name": "Productivité", "count": 28},
    {"id": "data", "name": "Données & Analytique", "count": 21},
    {"id": "communication", "name": "Communication", "count": 15},
    {"id": "ai", "name": "IA & ML", "count": 12},
    {"id": "other", "name": "Autre", "count": 19}
  ]
}
\`\`\`
`,

  'api-credentials': `
# API Identifiants

Gérez les identifiants pour les serveurs MCP connectés.

## Lister les identifiants utilisateur

\`\`\`http
GET /api/v1/credentials
\`\`\`

### Réponse

\`\`\`json
{
  "credentials": [
    {
      "id": "cred-123",
      "name": "Token GitHub",
      "credential_type": "api_key",
      "server_id": "github-mcp",
      "created_at": "2024-01-15T10:00:00Z",
      "last_used_at": "2024-01-20T14:30:00Z"
    }
  ]
}
\`\`\`

## Créer un identifiant

\`\`\`http
POST /api/v1/credentials
\`\`\`

### Requête

\`\`\`json
{
  "name": "Token GitHub",
  "credential_type": "api_key",
  "server_id": "github-mcp",
  "value": "ghp_xxxxxxxxxxxx",
  "metadata": {
    "scopes": ["repo", "read:org"]
  }
}
\`\`\`

### Réponse

\`\`\`json
{
  "id": "cred-456",
  "name": "Token GitHub",
  "credential_type": "api_key",
  "server_id": "github-mcp",
  "created_at": "2024-01-21T09:00:00Z"
}
\`\`\`

## Mettre à jour un identifiant

\`\`\`http
PATCH /api/v1/credentials/{credential_id}
\`\`\`

### Requête

\`\`\`json
{
  "value": "ghp_nouveau_token",
  "name": "Token GitHub (Mis à jour)"
}
\`\`\`

## Supprimer un identifiant

\`\`\`http
DELETE /api/v1/credentials/{credential_id}
\`\`\`

### Réponse

\`\`\`json
{
  "success": true,
  "message": "Identifiant supprimé"
}
\`\`\`

## Types d'identifiants

| Type | Description |
|------|-------------|
| \`api_key\` | Clé API / token simple |
| \`oauth2\` | Identifiants OAuth 2.0 |
| \`basic\` | Nom d'utilisateur/mot de passe |
| \`custom\` | Schéma d'identifiant personnalisé |
`,

  'api-mcp': `
# API Passerelle MCP

La passerelle MCP fournit un accès complet au Model Context Protocol via Server-Sent Events (SSE).

## Connexion à la passerelle

\`\`\`http
GET /mcp/sse
Authorization: Bearer mcphub_sk_votre_cle_api
\`\`\`

Cela établit une connexion SSE pour la communication JSON-RPC 2.0.

### Réponse de connexion

\`\`\`
HTTP/1.1 200 OK
Content-Type: text/event-stream
X-Session-ID: session_abc123

event: message
data: {"jsonrpc":"2.0","id":0,"result":{"capabilities":{"tools":{}}}}
\`\`\`

## Filtrage par Toolbox

**Fonctionnalité clé** : Si votre clé API est liée à une Toolbox, la passerelle n'expose que les outils de ce groupe.

\`\`\`
Clé API sans Toolbox → Voit TOUS vos outils
Clé API avec Toolbox → Voit UNIQUEMENT les outils de ce groupe
\`\`\`

Cela crée des serveurs MCP spécialisés à partir d'une seule instance BigMCP.

## Méthodes JSON-RPC

### Lister les outils

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
\`\`\`

Réponse :

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "github_create_issue",
        "description": "Créer une issue GitHub",
        "inputSchema": {
          "type": "object",
          "properties": {
            "repo": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"}
          },
          "required": ["repo", "title"]
        }
      },
      {
        "name": "workflow_issue_triage",
        "description": "Trier et catégoriser les issues",
        "inputSchema": {...}
      },
      {
        "name": "orchestrator_search_tools",
        "description": "Rechercher des outils par capacité",
        "inputSchema": {...}
      }
    ]
  }
}
\`\`\`

### Appeler un outil

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "github_create_issue",
    "arguments": {
      "repo": "monorg/monrepo",
      "title": "Bug: Échec de connexion",
      "body": "Étapes pour reproduire..."
    }
  }
}
\`\`\`

Réponse :

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Issue #42 créée: Bug: Échec de connexion"
      }
    ]
  }
}
\`\`\`

### Lister les ressources (Compositions)

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "resources/list"
}
\`\`\`

### Initialiser

\`\`\`json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "mon-client",
      "version": "1.0.0"
    }
  }
}
\`\`\`

## Outils d'orchestration intégrés

La passerelle inclut toujours ces outils :

| Outil | Description |
|-------|-------------|
| \`orchestrator_search_tools\` | Recherche sémantique d'outils |
| \`orchestrator_analyze_intent\` | Analyse d'intention par IA |
| \`orchestrator_execute_composition\` | Exécuter une composition |
| \`orchestrator_create_composition\` | Créer une nouvelle composition |

## Outils workflow

Les compositions en production apparaissent comme des outils \`workflow_*\` :

\`\`\`json
{
  "name": "workflow_daily_report",
  "description": "Générer un rapport d'analytique quotidien",
  "inputSchema": {
    "type": "object",
    "properties": {
      "date": {"type": "string", "format": "date"}
    }
  }
}
\`\`\`

## Endpoint Message (Alternative)

Pour les clients non-SSE, envoyez des messages individuels :

\`\`\`http
POST /mcp/message
Authorization: Bearer mcphub_sk_votre_cle_api
X-Session-ID: session_abc123
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
\`\`\`

## Exemple: Session complète

\`\`\`javascript
// 1. Connexion SSE
const eventSource = new EventSource(
  'https://bigmcp.cloud/mcp/sse',
  { headers: { 'Authorization': 'Bearer mcphub_sk_xxx' }}
);

// 2. Initialiser
await sendMessage({
  jsonrpc: '2.0',
  id: 0,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    clientInfo: { name: 'mon-app', version: '1.0.0' }
  }
});

// 3. Lister les outils (filtrés par Toolbox si applicable)
const tools = await sendMessage({
  jsonrpc: '2.0',
  id: 1,
  method: 'tools/list'
});

// 4. Exécuter un outil
const result = await sendMessage({
  jsonrpc: '2.0',
  id: 2,
  method: 'tools/call',
  params: {
    name: 'github_create_issue',
    arguments: { repo: 'org/repo', title: 'Titre de l issue' }
  }
});
\`\`\`
`,

  'api-tools': `
# API Outils

Exécutez des outils et gérez les bindings d'outils via l'API REST.

## Lister les outils disponibles

\`\`\`http
GET /api/v1/tools
\`\`\`

### Paramètres de requête

| Paramètre | Type | Description |
|-----------|------|-------------|
| \`server_id\` | string | Filtrer par serveur |
| \`refresh\` | bool | Forcer le rafraîchissement depuis les serveurs |

### Réponse

\`\`\`json
{
  "tools": [
    {
      "id": "tool-uuid",
      "name": "create_issue",
      "server_id": "github-mcp",
      "description": "Créer une issue GitHub",
      "parameters": {
        "type": "object",
        "properties": {...},
        "required": [...]
      }
    }
  ]
}
\`\`\`

## Exécuter un outil via binding

Les bindings d'outils permettent de préconfigurer des paramètres et d'exécuter des outils.

### Créer un binding

\`\`\`http
POST /api/v1/tool-bindings
\`\`\`

\`\`\`json
{
  "context_id": "context-uuid",
  "tool_id": "tool-uuid",
  "binding_name": "creer_rapport_bug",
  "default_parameters": {
    "repo": "monorg/monrepo",
    "labels": ["bug"]
  },
  "locked_parameters": ["repo"]
}
\`\`\`

### Exécuter un binding

\`\`\`http
POST /api/v1/tool-bindings/{binding_id}/execute
\`\`\`

\`\`\`json
{
  "parameters": {
    "title": "Bouton de connexion cassé",
    "body": "Le bouton de connexion ne répond pas sur mobile"
  }
}
\`\`\`

**Fusion des paramètres :**
- \`default_parameters\` du binding sont utilisés comme base
- \`locked_parameters\` ne peuvent pas être remplacés par l'utilisateur
- \`parameters\` utilisateur remplacent les defaults non verrouillés

### Réponse

\`\`\`json
{
  "success": true,
  "result": {
    "issue_number": 42,
    "url": "https://github.com/monorg/monrepo/issues/42"
  },
  "execution_time_ms": 245.3,
  "binding_id": "binding-uuid",
  "binding_name": "creer_rapport_bug",
  "tool_name": "create_issue",
  "server_id": "github-mcp",
  "merged_parameters": {
    "repo": "monorg/monrepo",
    "labels": ["bug"],
    "title": "Bouton de connexion cassé",
    "body": "Le bouton de connexion ne répond pas sur mobile"
  }
}
\`\`\`

## Orchestrer (IA)

Utilisez le langage naturel pour trouver et exécuter des outils :

\`\`\`http
POST /api/v1/orchestrate
\`\`\`

\`\`\`json
{
  "query": "Créer une issue sur le bug de connexion dans le repo principal",
  "execute": true,
  "parameters": {
    "title": "Bug de connexion",
    "body": "Détails..."
  }
}
\`\`\`

### Réponse

\`\`\`json
{
  "query": "Créer une issue...",
  "analysis": {
    "intent": "create_issue",
    "confidence": 0.95,
    "proposed_composition": {
      "steps": [
        {
          "tool": "github_create_issue",
          "parameters": {...}
        }
      ]
    }
  },
  "execution": {
    "status": "completed",
    "result": {...}
  }
}
\`\`\`

## Toolboxes

### Lister les Toolboxes

\`\`\`http
GET /api/v1/tool-groups
\`\`\`

### Créer une Toolbox

\`\`\`http
POST /api/v1/tool-groups
\`\`\`

\`\`\`json
{
  "name": "Agent Support Client",
  "description": "Outils pour les workflows de support client",
  "visibility": "private"
}
\`\`\`

### Ajouter un outil au groupe

\`\`\`http
POST /api/v1/tool-groups/{group_id}/items
\`\`\`

\`\`\`json
{
  "item_type": "tool",
  "tool_id": "tool-uuid",
  "order": 0
}
\`\`\`

### Ajouter une composition au groupe

\`\`\`json
{
  "item_type": "composition",
  "composition_id": "composition-uuid",
  "order": 1
}
\`\`\`

## API Compositions

### Lister les compositions

\`\`\`http
GET /api/v1/compositions
\`\`\`

### Exécuter une composition

\`\`\`http
POST /api/v1/compositions/{composition_id}/execute
\`\`\`

\`\`\`json
{
  "parameters": {
    "issue_number": 42
  }
}
\`\`\`

### Promouvoir une composition

\`\`\`http
POST /api/v1/compositions/{composition_id}/promote
\`\`\`

\`\`\`json
{
  "target_status": "production"
}
\`\`\`

Cycle de vie : \`temporary\` → \`validated\` → \`production\`

Les compositions en production apparaissent comme des outils \`workflow_*\` dans la passerelle MCP.
`,
}
