/**
 * Documentation Intégrations - Contenu en français
 *
 * Comment intégrer BigMCP avec différents clients et plateformes.
 */

export const integrationsContent: Record<string, string> = {
  'claude-desktop': `
# Intégration Claude Desktop

Connectez BigMCP à Claude Desktop pour accéder à tous vos outils directement dans Claude.

## Vue d'ensemble

Avec BigMCP + Claude Desktop, vous pouvez :
- Accéder à tous vos serveurs MCP connectés via un seul endpoint
- Utiliser les Toolboxes pour créer des profils Claude spécialisés
- Exploiter les compositions comme workflows prêts à l'emploi
- Maintenir une source unique de vérité pour les identifiants

## Prérequis

- [Claude Desktop](https://claude.ai/desktop) installé
- Compte BigMCP avec des serveurs connectés
- Clé API BigMCP

## Configuration rapide

### 1. Créer une clé API

1. Connectez-vous à BigMCP
2. Allez dans **Paramètres** → **Clés API**
3. Cliquez sur **Créer une clé**
4. Configurez :
   - **Nom** : "Claude Desktop"
   - **Scopes** : \`tools:read\`, \`tools:execute\`
   - **Toolbox** : (Optionnel) Sélectionnez pour limiter les outils disponibles
5. Copiez la clé générée (affichée une seule fois !)

### 2. Configurer Claude Desktop

Localisez votre fichier de configuration Claude :

| OS | Chemin |
|----|--------|
| macOS | \`~/Library/Application Support/Claude/claude_desktop_config.json\` |
| Windows | \`%APPDATA%\\Claude\\claude_desktop_config.json\` |
| Linux | \`~/.config/Claude/claude_desktop_config.json\` |

### 3. Ajouter le serveur BigMCP

Éditez le fichier de configuration :

\`\`\`json
{
  "mcpServers": {
    "bigmcp": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_votre_cle_ici"
      ]
    }
  }
}
\`\`\`

### 4. Redémarrer Claude Desktop

Fermez et rouvrez Claude Desktop pour appliquer les changements.

## Profils multiples avec les Toolboxes

Créez différentes configurations Claude pour différents cas d'usage :

\`\`\`json
{
  "mcpServers": {
    "outils-travail": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_cle_travail"
      ]
    },
    "outils-perso": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_cle_perso"
      ]
    },
    "lecture-seule": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_cle_readonly"
      ]
    }
  }
}
\`\`\`

Chaque clé peut être liée à une Toolbox différente, créant ainsi des agents spécialisés.

## Configuration auto-hébergée

Pour BigMCP auto-hébergé :

\`\`\`json
{
  "mcpServers": {
    "mon-bigmcp": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://votre-domaine.com/mcp/sse",
        "--api-key", "mcphub_sk_votre_cle"
      ]
    }
  }
}
\`\`\`

## Vérification

Après le redémarrage de Claude Desktop :

1. Démarrez une nouvelle conversation
2. Cherchez l'icône des outils (🔧) dans la zone de saisie
3. Cliquez pour voir les outils disponibles
4. Essayez : "Liste mes outils disponibles"

## Ce que vous verrez

Claude aura accès à :

- **Vos outils connectés** : Tous les outils des serveurs que vous avez connectés
- **Outils d'orchestration** : \`orchestrator_search_tools\`, \`orchestrator_analyze_intent\`, etc.
- **Outils workflow** : Compositions en production comme outils \`workflow_*\`

Si vous utilisez une clé restreinte à une Toolbox, seuls les outils de ce groupe apparaissent.

## Dépannage

### "Échec de connexion"

- Vérifiez que la clé API est correcte (commence par \`mcphub_sk_\`)
- Vérifiez votre connexion internet
- Assurez-vous que les serveurs BigMCP sont connectés
- Essayez d'accéder à \`https://bigmcp.cloud/mcp/sse\` dans un navigateur (devrait afficher un flux SSE)

### "Aucun outil disponible"

- Vérifiez les permissions de la Toolbox sur la clé API
- Vérifiez que les serveurs sont connectés dans le tableau de bord BigMCP
- Assurez-vous que la clé API a le scope \`tools:read\`
- Essayez de régénérer la clé API

### Les outils ne s'exécutent pas

- Assurez-vous que la clé API a le scope \`tools:execute\`
- Vérifiez la validité des identifiants dans BigMCP
- Consultez les messages d'erreur spécifiques à l'outil
- Testez l'outil directement dans BigMCP d'abord

### La configuration ne se charge pas

- Vérifiez que la syntaxe JSON est valide
- Vérifiez que le chemin du fichier est correct pour votre OS
- Assurez-vous qu'il n'y a pas de noms de serveur en double
- Essayez de supprimer et réajouter la configuration
`,

  'mistral-lechat': `
# Intégration Mistral Le Chat

Connectez BigMCP à Mistral Le Chat pour accéder à tous vos outils directement dans l'assistant IA de Mistral.

## Vue d'ensemble

Mistral Le Chat supporte les connexions MCP via deux méthodes :
- **OAuth 2.0** - Connexion fluide et sécurisée avec gestion automatique des tokens
- **Clé API** - Connexion directe avec support Toolbox pour le contrôle d'accès

Avec BigMCP + Mistral Le Chat :
- Accédez à tous vos serveurs MCP connectés via un seul endpoint
- Utilisez les Toolboxes pour contrôler quels outils sont disponibles
- Exploitez les compositions comme workflows prêts à l'emploi

## Prérequis

- Compte [Mistral Le Chat](https://chat.mistral.ai)
- Compte BigMCP avec des serveurs connectés
- Au moins un outil connecté

## Méthode 1 : Connexion OAuth (Recommandé)

OAuth fournit une authentification fluide sans gestion manuelle de clés.

### Configuration

1. Allez sur [chat.mistral.ai](https://chat.mistral.ai)
2. Naviguez vers **Paramètres** → **Serveurs MCP**
3. Cliquez sur **Ajouter un serveur**
4. Entrez l'endpoint BigMCP :
   \`\`\`
   https://bigmcp.cloud
   \`\`\`
5. Cliquez sur **Connecter**
6. Vous serez redirigé vers BigMCP pour autoriser
7. Connectez-vous et cliquez sur **Autoriser**

Terminé ! Mistral Le Chat a maintenant accès à tous vos outils BigMCP.

### Avantages OAuth
- Pas de clés API à gérer
- Rafraîchissement automatique des tokens
- Révocation facile depuis les paramètres BigMCP

## Méthode 2 : Connexion par clé API

Utilisez les clés API quand vous avez besoin du filtrage par Toolbox pour le contrôle d'accès.

### Configuration

1. Dans BigMCP, allez dans **Paramètres** → **Clés API**
2. Créez une nouvelle clé :
   - **Nom** : "Mistral Le Chat"
   - **Scopes** : \`tools:read\`, \`tools:execute\`
   - **Toolbox** : Sélectionnez un groupe pour limiter les outils disponibles
3. Copiez la clé générée

4. Dans Mistral Le Chat :
   - Allez dans **Paramètres** → **Serveurs MCP**
   - Cliquez sur **Ajouter un serveur**
   - Entrez l'endpoint : \`https://bigmcp.cloud\`
   - Sélectionnez l'authentification **Clé API**
   - Collez votre clé API BigMCP
   - Cliquez sur **Connecter**

### Avantages clé API
- Filtrage par Toolbox pour le contrôle d'accès
- Création de profils spécialisés avec outils limités
- Clés multiples pour différents cas d'usage

## Utiliser les outils

Une fois connecté, vos outils apparaissent dans l'interface de Mistral :

1. Démarrez une nouvelle conversation
2. Cherchez le bouton **Outils** dans la zone de saisie
3. Demandez à Mistral d'utiliser n'importe quel outil naturellement :

\`\`\`
"Créer une issue GitHub sur le bug de connexion"
"Rechercher dans mon espace Notion les notes de réunion"
"Envoyer un message Slack à #general"
\`\`\`

## Toolboxes pour le contrôle d'accès

Créez des profils Mistral spécialisés avec accès limité aux outils :

### Exemple : Profil lecture seule

1. Créez une Toolbox "Lecture seule" avec uniquement les outils \`list_*\`, \`get_*\`, \`read_*\`
2. Créez une clé API liée à ce groupe
3. Connectez Mistral avec cette clé

Mistral ne peut que lire les données, jamais les modifier.

### Exemple : Profil développement

1. Créez une Toolbox "Outils Dev" avec les outils GitHub, GitLab et Jira
2. Créez une clé API liée à ce groupe
3. Connectez Mistral avec cette clé

Mistral ne voit que les outils liés au développement.

## Configuration auto-hébergée

Pour BigMCP auto-hébergé :

\`\`\`
https://votre-domaine.com
\`\`\`

Les méthodes OAuth et clé API fonctionnent de la même manière.

## Dépannage

### "Échec d'autorisation"
- Assurez-vous que BigMCP est accessible
- Videz les cookies du navigateur et réessayez
- Vérifiez le statut de votre compte BigMCP

### "Aucun outil disponible"
- Vérifiez que vous avez des serveurs connectés dans BigMCP
- Vérifiez que les identifiants serveur sont valides
- Si vous utilisez une clé API, vérifiez que la Toolbox contient des outils

### "Échec d'exécution de l'outil"
- Vérifiez les identifiants du serveur spécifique
- Vérifiez les permissions requises par l'outil
- Consultez les détails d'erreur dans le tableau de bord BigMCP

## Révoquer l'accès

### OAuth
1. Allez dans BigMCP **Paramètres** → **Applications connectées**
2. Trouvez "Mistral Le Chat"
3. Cliquez sur **Révoquer l'accès**

### Clé API
1. Allez dans BigMCP **Paramètres** → **Clés API**
2. Trouvez la clé utilisée par Mistral
3. Cliquez sur **Supprimer**

## Comparaison

| Fonctionnalité | OAuth | Clé API |
|----------------|-------|---------|
| Configuration | Un clic | Manuelle |
| Toolboxes | Tous les outils | Filtré |
| Gestion des tokens | Automatique | Statique |
| Idéal pour | Démarrage rapide | Contrôle d'accès |
`,

  n8n: `
# Intégration n8n

Utilisez les outils BigMCP dans les workflows d'automatisation n8n via l'API REST.

## Vue d'ensemble

n8n est une puissante plateforme d'automatisation de workflows. Avec l'intégration BigMCP :
- Accédez à tous vos outils MCP depuis les nœuds n8n
- Construisez des automatisations complexes avec orchestration IA
- Exécutez des compositions en un seul appel API
- Connectez plus de 100 services via BigMCP

## Méthodes d'intégration

### Méthode 1 : Nœud HTTP Request (Recommandé)

Utilisez le nœud HTTP Request intégré de n8n pour appeler l'API BigMCP.

#### Exécuter un binding d'outil

\`\`\`
Méthode: POST
URL: https://bigmcp.cloud/api/v1/tool-bindings/{binding_id}/execute
Headers:
  Authorization: Bearer mcphub_sk_votre_cle
  Content-Type: application/json
Body:
{
  "parameters": {
    "title": "{{ $json.title }}",
    "body": "{{ $json.body }}"
  }
}
\`\`\`

#### Exécuter via orchestration

\`\`\`
Méthode: POST
URL: https://bigmcp.cloud/api/v1/orchestrate
Headers:
  Authorization: Bearer mcphub_sk_votre_cle
  Content-Type: application/json
Body:
{
  "query": "Créer une issue GitHub pour {{ $json.bug_description }}",
  "execute": true
}
\`\`\`

#### Exécuter une composition

\`\`\`
Méthode: POST
URL: https://bigmcp.cloud/api/v1/compositions/{composition_id}/execute
Headers:
  Authorization: Bearer mcphub_sk_votre_cle
  Content-Type: application/json
Body:
{
  "parameters": {
    "issue_number": {{ $json.issue_number }}
  }
}
\`\`\`

### Méthode 2 : Nœud n8n personnalisé (Bientôt disponible)

Nous développons un nœud BigMCP dédié pour n8n avec :
- Sélection visuelle des outils
- Auto-complétion des paramètres
- Explorateur de compositions
- Authentification intégrée

## Exemples de workflows

### Automatisation du triage d'issues

\`\`\`mermaid
flowchart LR
    GH(["<b>GitHub</b><br/>Webhook"])
    AI(["<b>BigMCP</b><br/>Analyser"])
    Label(["<b>BigMCP</b><br/>Ajouter labels"])
    Slack(["<b>Slack</b><br/>Notifier"])

    GH --> AI --> Label --> Slack

    style GH fill:#ffffff,stroke:#d4d4d4,color:#262626
    style AI fill:#D97757,stroke:#c4624a,color:#ffffff
    style Label fill:#D97757,stroke:#c4624a,color:#ffffff
    style Slack fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

1. **Déclencheur** : Webhook GitHub (nouvelle issue créée)
2. **HTTP Request** : Appeler BigMCP orchestrate pour analyser l'issue
3. **HTTP Request** : Appeler BigMCP pour ajouter des labels basés sur l'analyse
4. **HTTP Request** : Appeler BigMCP pour envoyer une notification Slack

### Génération de rapport quotidien

\`\`\`mermaid
flowchart LR
    Sched(["<b>Planifier</b><br/>9h"])
    BigMCP(["<b>BigMCP</b><br/>Composition"])
    Email(["<b>Email</b><br/>Envoyer"])

    Sched --> BigMCP --> Email

    style Sched fill:#ffffff,stroke:#d4d4d4,color:#262626
    style BigMCP fill:#D97757,stroke:#c4624a,color:#ffffff
    style Email fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

1. **Déclencheur planifié** : Tous les jours à 9h
2. **HTTP Request** : Exécuter la composition BigMCP pour le rapport
3. **Envoyer email** : Transmettre le rapport aux parties prenantes

### Pipeline support client

\`\`\`mermaid
flowchart LR
    ZD(["<b>Zendesk</b><br/>Nouveau ticket"])
    Cat(["<b>BigMCP</b><br/>Catégoriser"])
    Ctx(["<b>BigMCP</b><br/>Obtenir contexte"])
    Notion(["<b>Notion</b><br/>Logger"])

    ZD --> Cat --> Ctx --> Notion

    style ZD fill:#ffffff,stroke:#d4d4d4,color:#262626
    style Cat fill:#D97757,stroke:#c4624a,color:#ffffff
    style Ctx fill:#D97757,stroke:#c4624a,color:#ffffff
    style Notion fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

## Configuration de l'authentification

### Créer une clé API dédiée

1. Allez dans BigMCP **Paramètres** → **Clés API**
2. Créez une clé avec :
   - **Nom** : "Automatisation n8n"
   - **Scopes** : \`tools:execute\`
   - **Toolbox** : (Optionnel) Restreindre à des outils spécifiques
3. Stockez la clé dans les identifiants n8n

### Configuration des identifiants n8n

1. Dans n8n, allez dans **Paramètres** → **Identifiants**
2. Créez un nouvel identifiant **Header Auth** :
   - **Nom** : BigMCP API
   - **Nom de l'en-tête** : Authorization
   - **Valeur de l'en-tête** : Bearer mcphub_sk_votre_cle

## Bonnes pratiques

1. **Utilisez les Toolboxes** - Créez un groupe spécifique pour n8n avec uniquement les outils nécessaires
2. **Gérez les erreurs** - Ajoutez des nœuds de gestion d'erreur après les appels API
3. **Limitation de débit** - Ajoutez des délais entre les appels API rapides
4. **Logging** - Loggez les réponses BigMCP pour le débogage
5. **Clés séparées** - Utilisez différentes clés API pour différents workflows
6. **Utilisez les compositions** - Les séquences complexes doivent être des compositions BigMCP, pas des chaînes n8n
`,

  'custom-clients': `
# Clients personnalisés

Construisez vos propres applications utilisant la passerelle MCP BigMCP ou l'API REST.

## Deux approches d'intégration

| Approche | Cas d'usage | Protocole |
|----------|-------------|-----------|
| Passerelle MCP | Assistants IA, outils temps réel | SSE + JSON-RPC 2.0 |
| API REST | Automatisation, scripts, intégrations | HTTP REST |

## Intégration passerelle MCP

La passerelle MCP expose vos outils via le protocole MCP standard :

\`\`\`
Endpoint: https://bigmcp.cloud/mcp/sse
Protocole: Server-Sent Events (SSE)
Messages: JSON-RPC 2.0
Auth: Bearer token (clé API)
\`\`\`

### Client JavaScript/TypeScript

Utilisant le SDK MCP officiel :

\`\`\`typescript
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

// Initialiser le client
const client = new Client({
  name: 'mon-app',
  version: '1.0.0',
});

// Créer le transport SSE avec auth
const transport = new SSEClientTransport(
  new URL('https://bigmcp.cloud/mcp/sse'),
  {
    requestInit: {
      headers: {
        'Authorization': 'Bearer mcphub_sk_votre_cle',
      },
    },
  }
);

// Connexion
await client.connect(transport);

// Initialiser la session
await client.initialize();

// Lister les outils disponibles
const { tools } = await client.listTools();
console.log('Outils disponibles:', tools.map(t => t.name));

// Appeler un outil
const result = await client.callTool({
  name: 'github_create_issue',
  arguments: {
    repo: 'monorg/monrepo',
    title: 'Créé via MCP',
    body: 'Cette issue a été créée via le protocole MCP'
  },
});
console.log('Résultat:', result);
\`\`\`

### Client Python

Utilisant le SDK MCP Python :

\`\`\`python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    # Connexion avec authentification
    async with sse_client(
        "https://bigmcp.cloud/mcp/sse",
        headers={"Authorization": "Bearer mcphub_sk_votre_cle"}
    ) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialiser
            await session.initialize()

            # Lister les outils
            tools = await session.list_tools()
            print(f"Trouvé {len(tools.tools)} outils")

            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")

            # Appeler un outil
            result = await session.call_tool(
                "github_create_issue",
                {
                    "repo": "monorg/monrepo",
                    "title": "Créé via MCP Python",
                    "body": "Issue créée avec le SDK MCP Python"
                }
            )
            print(f"Résultat: {result}")

asyncio.run(main())
\`\`\`

## Intégration API REST

Pour des cas d'usage plus simples ou clients non-MCP :

### Exemples cURL

\`\`\`bash
# Lister les outils
curl https://bigmcp.cloud/api/v1/tools \\
  -H "Authorization: Bearer mcphub_sk_votre_cle"

# Exécuter un binding d'outil
curl -X POST https://bigmcp.cloud/api/v1/tool-bindings/{id}/execute \\
  -H "Authorization: Bearer mcphub_sk_votre_cle" \\
  -H "Content-Type: application/json" \\
  -d '{"parameters": {"title": "Bonjour le monde"}}'

# Orchestration IA
curl -X POST https://bigmcp.cloud/api/v1/orchestrate \\
  -H "Authorization: Bearer mcphub_sk_votre_cle" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "Créer une issue sur le bug de connexion",
    "execute": true
  }'

# Exécuter une composition
curl -X POST https://bigmcp.cloud/api/v1/compositions/{id}/execute \\
  -H "Authorization: Bearer mcphub_sk_votre_cle" \\
  -H "Content-Type: application/json" \\
  -d '{"parameters": {"issue_number": 42}}'
\`\`\`

### Python Requests

\`\`\`python
import requests

API_KEY = "mcphub_sk_votre_cle"
BASE_URL = "https://bigmcp.cloud"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Lister les outils
response = requests.get(f"{BASE_URL}/api/v1/tools", headers=headers)
tools = response.json()

# Exécuter un binding
response = requests.post(
    f"{BASE_URL}/api/v1/tool-bindings/{binding_id}/execute",
    headers=headers,
    json={"parameters": {"title": "Bonjour"}}
)
result = response.json()

# Orchestrer
response = requests.post(
    f"{BASE_URL}/api/v1/orchestrate",
    headers=headers,
    json={
        "query": "Envoyer un message Slack à #general",
        "execute": True
    }
)
orchestration = response.json()
\`\`\`

### JavaScript Fetch

\`\`\`javascript
const API_KEY = 'mcphub_sk_votre_cle';
const BASE_URL = 'https://bigmcp.cloud';

const headers = {
  'Authorization': \`Bearer \${API_KEY}\`,
  'Content-Type': 'application/json'
};

// Lister les outils
const tools = await fetch(\`\${BASE_URL}/api/v1/tools\`, { headers })
  .then(r => r.json());

// Exécuter un binding
const result = await fetch(
  \`\${BASE_URL}/api/v1/tool-bindings/\${bindingId}/execute\`,
  {
    method: 'POST',
    headers,
    body: JSON.stringify({ parameters: { title: 'Bonjour' } })
  }
).then(r => r.json());

// Orchestrer
const orchestration = await fetch(
  \`\${BASE_URL}/api/v1/orchestrate\`,
  {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query: 'Créer une page Notion avec les notes de réunion',
      execute: true
    })
  }
).then(r => r.json());
\`\`\`

## Filtrage par Toolbox

Quand votre clé API est liée à une Toolbox :

- **Passerelle MCP** : Seuls les outils du groupe sont listés et appelables
- **API REST** : Les bindings d'outils sont validés contre le groupe

Cela permet de construire des clients spécialisés avec des capacités limitées.

## SDKs & Bibliothèques

| Langage | SDK MCP | Client REST |
|---------|---------|-------------|
| JavaScript | [@modelcontextprotocol/sdk](https://www.npmjs.com/package/@modelcontextprotocol/sdk) | fetch / axios |
| Python | [mcp](https://pypi.org/project/mcp/) | requests / httpx |
| Go | Prévu | net/http |
| Rust | Prévu | reqwest |

## Ressources

- [Spécification MCP](https://spec.modelcontextprotocol.io)
- [SDK TypeScript MCP](https://github.com/modelcontextprotocol/typescript-sdk)
- [SDK Python MCP](https://github.com/modelcontextprotocol/python-sdk)
- [Référence API BigMCP](/docs/api/api-overview)
`,
}
