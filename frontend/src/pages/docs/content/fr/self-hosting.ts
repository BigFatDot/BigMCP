/**
 * Documentation Auto-hébergement - Contenu en français
 */

export const selfHostingContent: Record<string, string> = {
  'self-host-overview': `
# Vue d'ensemble de l'auto-hébergement

BigMCP peut être auto-hébergé pour un contrôle total sur vos données et votre infrastructure.

## Éditions

### Édition Community (Gratuite)
- Fonctionnalités complètes de la plateforme
- 1 utilisateur
- Choisissez votre fournisseur LLM
- Open source (Licence Elastic 2.0)

### Édition Enterprise
- Utilisateurs et équipes illimités
- Contrôle admin complet
- Support prioritaire
- Licence perpétuelle

## Prérequis

### Matériel minimum
- 2 cœurs CPU
- 4 Go RAM
- 20 Go stockage

### Recommandé
- 4 cœurs CPU
- 8 Go RAM
- 50 Go SSD

### Logiciels
- Docker 20.10+
- Docker Compose 2.0+
- Linux (Ubuntu 20.04+ recommandé)

## Architecture

\`\`\`mermaid
flowchart TB
    subgraph internet [" "]
        Users(["<b>Utilisateurs</b>"])
    end

    subgraph docker [" "]
        Nginx(["<b>Nginx</b><br/>Reverse Proxy"])

        subgraph apps [" "]
            direction LR
            Frontend(["<b>Frontend</b><br/>SPA React"])
            Backend(["<b>Backend</b><br/>FastAPI + MCP"])
        end

        subgraph data [" "]
            direction LR
            Postgres(["<b>PostgreSQL</b><br/>Données"])
            Qdrant(["<b>Qdrant</b><br/>Vecteurs"])
        end

        LLM(["<b>API LLM</b><br/>OpenAI / Anthropic"])
    end

    Users --> Nginx
    Nginx --> Frontend & Backend
    Backend --> Postgres & Qdrant & LLM

    style internet fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style docker fill:none,stroke:#c4624a,stroke-width:2px
    style apps fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style data fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style Users fill:#ffffff,stroke:#d4d4d4,color:#262626
    style Nginx fill:#D97757,stroke:#c4624a,color:#ffffff
    style Frontend fill:#f4e4df,stroke:#c4624a,color:#262626
    style Backend fill:#f4e4df,stroke:#c4624a,color:#262626
    style Postgres fill:#f4e4df,stroke:#c4624a,color:#262626
    style Qdrant fill:#f4e4df,stroke:#c4624a,color:#262626
    style LLM fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

## Démarrage rapide

\`\`\`bash
# Cloner le dépôt
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp

# Copier le template d'environnement
cp .env.example .env

# Éditer la configuration
nano .env

# Démarrer les services
docker compose up -d
\`\`\`

Visitez \`http://localhost:3000\` pour accéder à BigMCP.
`,

  'docker-setup': `
# Installation Docker

Déployez BigMCP avec Docker Compose.

## Prérequis

- Docker 20.10+
- Docker Compose 2.0+
- Nom de domaine (pour HTTPS)
- 4Go+ RAM

## Installation

### 1. Cloner le dépôt

\`\`\`bash
git clone https://github.com/bigfatdot/bigmcp.git
cd bigmcp
\`\`\`

### 2. Configurer l'environnement

\`\`\`bash
cp .env.example .env
\`\`\`

Éditez \`.env\` avec vos paramètres :

\`\`\`bash
# Requis
SECRET_KEY=votre-cle-secrete-ici
JWT_SECRET_KEY=votre-secret-jwt
ENCRYPTION_KEY=votre-cle-chiffrement
POSTGRES_PASSWORD=mot-de-passe-securise

# Configuration LLM (choisissez un)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Ou utilisez Anthropic
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=...

# Ou utilisez Ollama local
# LLM_PROVIDER=ollama
# OLLAMA_URL=http://localhost:11434
\`\`\`

### 3. Démarrer les services

\`\`\`bash
docker compose -f docker-compose.prod.yml up -d
\`\`\`

### 4. Vérifier l'installation

\`\`\`bash
# Vérifier les services
docker compose ps

# Voir les logs
docker compose logs -f
\`\`\`

## Configuration SSL/HTTPS

### Avec Let's Encrypt

La configuration nginx incluse supporte SSL automatique :

\`\`\`bash
# Éditer la config nginx
nano nginx/conf.d/bigmcp.conf

# Mettre à jour le domaine
server_name votre-domaine.com;

# Exécuter certbot
docker compose run --rm certbot certonly \\
  --webroot -w /var/www/certbot \\
  -d votre-domaine.com
\`\`\`

## Mise à jour

\`\`\`bash
# Tirer les derniers changements
git pull

# Reconstruire et redémarrer
docker compose -f docker-compose.prod.yml up -d --build
\`\`\`

## Dépannage

### Les services ne démarrent pas
\`\`\`bash
docker compose logs backend
docker compose logs postgres
\`\`\`

### Problèmes de base de données
\`\`\`bash
# Réinitialiser la base de données (attention: supprime les données)
docker compose down -v
docker compose up -d
\`\`\`
`,

  configuration: `
# Configuration

Variables d'environnement et paramètres pour BigMCP auto-hébergé.

## Variables requises

| Variable | Description | Exemple |
|----------|-------------|---------|
| SECRET_KEY | Clé secrète de l'app | 32+ caractères aléatoires |
| JWT_SECRET_KEY | Clé de signature JWT | 32+ caractères aléatoires |
| ENCRYPTION_KEY | Chiffrement des identifiants | Clé de 32 caractères |
| POSTGRES_PASSWORD | Mot de passe de la base | Mot de passe sécurisé |

## Configuration LLM

### OpenAI
\`\`\`bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
\`\`\`

### Anthropic
\`\`\`bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-20241022
\`\`\`

### Mistral
\`\`\`bash
LLM_PROVIDER=mistral
MISTRAL_API_KEY=...
LLM_MODEL=mistral-small-latest
EMBEDDING_MODEL=mistral-embed
\`\`\`

### Local (Ollama)
\`\`\`bash
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=llama2
EMBEDDING_MODEL=nomic-embed-text
\`\`\`

## Configuration base de données

\`\`\`bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/bigmcp
\`\`\`

## Flags de fonctionnalités

\`\`\`bash
# Activer/désactiver des fonctionnalités
ENABLE_MARKETPLACE=true
ENABLE_SEMANTIC_SEARCH=true
ENABLE_ORGANIZATIONS=true
ENABLE_OAUTH=false
\`\`\`

## Paramètres de sécurité

\`\`\`bash
# CORS
CORS_ORIGINS=https://votre-domaine.com

# Limitation de débit
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# Session
SESSION_EXPIRY_HOURS=24
\`\`\`
`,

  'llm-providers': `
# Fournisseurs LLM

Configurez votre backend IA pour BigMCP auto-hébergé.

## Fournisseurs supportés

| Fournisseur | Modèles | Support Embedding |
|-------------|---------|-------------------|
| OpenAI | GPT-4o, GPT-4, GPT-3.5 | Oui |
| Anthropic | Claude 3.5, Claude 3 | Non* |
| Mistral | Mistral Small/Large | Oui |
| Ollama | Tout modèle local | Dépend |

*Anthropic ne fournit pas d'API d'embedding; utilisez un fournisseur secondaire.

## Configuration OpenAI

\`\`\`bash
LLM_PROVIDER=openai
LLM_API_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
\`\`\`

### Azure OpenAI

\`\`\`bash
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://votre-ressource.openai.azure.com
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4o
\`\`\`

## Configuration Anthropic

\`\`\`bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-20241022

# Pour les embeddings, utilisez un fournisseur secondaire
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
\`\`\`

## Modèles locaux (Ollama)

### Installer Ollama

\`\`\`bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama2
ollama pull nomic-embed-text
\`\`\`

### Configurer BigMCP

\`\`\`bash
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=llama2
EMBEDDING_MODEL=nomic-embed-text
\`\`\`

## Choisir un fournisseur

| Cas d'usage | Recommandé |
|-------------|------------|
| Meilleure qualité | OpenAI GPT-4o ou Claude 3.5 |
| Économique | Mistral Small |
| Priorité confidentialité | Ollama + modèles locaux |
| Enterprise | Azure OpenAI |

## Conseils de performance

1. **Utilisez des modèles plus petits** pour les tâches simples
2. **Activez le cache** pour réduire les appels API
3. **Regroupez les embeddings** si possible
4. **Surveillez l'utilisation** pour contrôler les coûts
`,

  'custom-servers': `
# Serveurs MCP personnalisés

Ajoutez vos propres serveurs MCP privés ou internes à votre instance BigMCP auto-hébergée.

## Vue d'ensemble

L'édition Enterprise vous permet d'enregistrer des serveurs MCP personnalisés qui :
- Se connectent à des APIs et bases de données internes
- Utilisent des packages privés de votre registre
- Exécutent des conteneurs Docker avec des outils propriétaires
- Exécutent des scripts et binaires locaux

Cela permet un contrôle total sur les outils accessibles aux assistants IA de votre organisation.

## Types d'installation

BigMCP supporte plusieurs méthodes d'installation pour les serveurs personnalisés :

| Type | Cas d'usage | Exemple |
|------|-------------|---------|
| **NPM** | Packages Node.js | \`@company/mcp-server\` |
| **PIP** | Packages Python | \`internal-mcp-server\` |
| **GitHub** | Dépôts Git | \`https://github.com/org/repo\` |
| **Docker** | Images conteneur | \`registry.company.com/mcp:v1\` |
| **Local** | Scripts & binaires | \`/opt/mcp/server.py\` |

## Ajouter un serveur personnalisé

### Via API

\`\`\`bash
curl -X POST https://votre-bigmcp.com/api/v1/servers \\
  -H "Authorization: Bearer VOTRE_CLE_API" \\
  -H "Content-Type: application/json" \\
  -d '{
    "server_id": "crm-interne",
    "name": "CRM Interne",
    "install_type": "pip",
    "install_package": "internal-crm-mcp",
    "command": "python",
    "args": ["-m", "crm_mcp_server"],
    "env": {
      "CRM_API_KEY": "\${CRM_API_KEY}",
      "CRM_API_URL": "https://crm.internal.company.com/api"
    },
    "auto_start": true
  }'
\`\`\`

### Options de configuration

| Champ | Requis | Description |
|-------|--------|-------------|
| \`server_id\` | Oui | Identifiant unique (minuscules, tirets) |
| \`name\` | Oui | Nom d'affichage |
| \`install_type\` | Oui | \`npm\`, \`pip\`, \`github\`, \`docker\`, \`local\` |
| \`install_package\` | Oui | Nom du package, URL du repo ou chemin |
| \`command\` | Oui | Commande exécutable |
| \`args\` | Non | Tableau d'arguments |
| \`env\` | Non | Variables d'environnement |
| \`version\` | Non | Contrainte de version du package |
| \`auto_start\` | Non | Démarrer immédiatement après installation |

## Types d'installation en détail

### Package NPM

Pour les serveurs MCP Node.js publiés sur npm (registre public ou privé).

\`\`\`json
{
  "server_id": "docs-internes",
  "name": "Documentation Interne",
  "install_type": "npm",
  "install_package": "@company/mcp-server-docs",
  "command": "npx",
  "args": ["-y", "@company/mcp-server-docs"],
  "env": {
    "DOCS_API_KEY": "\${DOCS_API_KEY}"
  }
}
\`\`\`

Pour un registre npm privé :
\`\`\`bash
# Configurer le registre npm avant de démarrer BigMCP
npm config set @company:registry https://npm.company.com
\`\`\`

### Package Python

Pour les serveurs MCP Python depuis PyPI ou index privé.

\`\`\`json
{
  "server_id": "data-warehouse",
  "name": "Data Warehouse",
  "install_type": "pip",
  "install_package": "company-data-mcp",
  "command": "python",
  "args": ["-m", "data_mcp_server"],
  "env": {
    "DW_CONNECTION_STRING": "\${DW_CONNECTION_STRING}"
  }
}
\`\`\`

Pour un PyPI privé :
\`\`\`bash
# Configurer pip pour utiliser l'index privé
pip config set global.extra-index-url https://pypi.company.com/simple
\`\`\`

### Dépôt GitHub

Pour les serveurs hébergés dans des dépôts Git.

\`\`\`json
{
  "server_id": "analytics-custom",
  "name": "Analytics Personnalisé",
  "install_type": "github",
  "install_package": "https://github.com/company/mcp-analytics.git",
  "version": "v1.2.0",
  "command": "python",
  "args": ["-m", "analytics_server"]
}
\`\`\`

Les dépôts privés nécessitent une clé SSH ou un token :
\`\`\`bash
# Via SSH (recommandé)
install_package: "git@github.com:company/private-mcp.git"

# Via HTTPS avec token
install_package: "https://TOKEN@github.com/company/private-mcp.git"
\`\`\`

### Conteneur Docker

Pour les serveurs MCP conteneurisés.

\`\`\`json
{
  "server_id": "legacy-erp",
  "name": "Intégration ERP Legacy",
  "install_type": "docker",
  "install_package": "registry.company.com/mcp-erp:v2.1",
  "command": "docker",
  "args": ["run", "-i", "--rm", "registry.company.com/mcp-erp:v2.1"],
  "env": {
    "ERP_HOST": "\${ERP_HOST}",
    "ERP_API_KEY": "\${ERP_API_KEY}"
  }
}
\`\`\`

Authentification au registre Docker :
\`\`\`bash
docker login registry.company.com
\`\`\`

### Script local

Pour les scripts ou binaires locaux.

\`\`\`json
{
  "server_id": "outils-locaux",
  "name": "Outils Dev Locaux",
  "install_type": "local",
  "install_package": "/opt/mcp/dev-tools",
  "command": "/opt/mcp/dev-tools/server.py",
  "args": ["--port", "stdio"]
}
\`\`\`

## Gestion des identifiants

### Substitution de variables d'environnement

Utilisez la syntaxe \`\${VAR_NAME}\` pour l'injection d'identifiants :

\`\`\`json
{
  "env": {
    "API_KEY": "\${MY_API_KEY}",
    "DB_URL": "\${DATABASE_CONNECTION_STRING}"
  }
}
\`\`\`

### Ordre de résolution des identifiants

Quand un serveur démarre, les identifiants sont résolus hiérarchiquement :

1. **Identifiants utilisateur** - Secrets par utilisateur (priorité haute)
2. **Identifiants organisation** - Secrets d'équipe partagés
3. **Valeurs par défaut serveur** - Valeurs dans le champ \`env\`

### Ajouter des identifiants utilisateur

Les utilisateurs peuvent connecter votre serveur personnalisé via le marketplace ou ajouter des identifiants via la page Services :

1. Allez dans **Services**
2. Cliquez sur votre serveur personnalisé
3. Configurez les identifiants requis
4. Cliquez sur **Enregistrer**

## Cycle de vie des serveurs

### Démarrer un serveur

\`\`\`bash
curl -X POST https://votre-bigmcp.com/api/v1/servers/{server_id}/start \\
  -H "Authorization: Bearer VOTRE_CLE_API"
\`\`\`

### Arrêter un serveur

\`\`\`bash
curl -X POST https://votre-bigmcp.com/api/v1/servers/{server_id}/stop \\
  -H "Authorization: Bearer VOTRE_CLE_API"
\`\`\`

### Découverte des outils

Quand un serveur démarre, BigMCP automatiquement :
1. Envoie une requête MCP \`tools/list\`
2. Stocke les outils découverts en base de données
3. Rend les outils disponibles via la passerelle MCP

## Exemple : Serveur API interne

Exemple complet pour une intégration d'API interne :

### 1. Créer le package serveur MCP

\`\`\`python
# internal_api_mcp/server.py
from mcp.server import Server
from mcp.types import Tool

server = Server("internal-api")

@server.tool()
async def get_customer(customer_id: str) -> dict:
    """Obtenir les détails d'un client depuis le CRM interne."""
    # Votre implémentation
    pass

@server.tool()
async def create_ticket(title: str, description: str) -> dict:
    """Créer un ticket de support."""
    # Votre implémentation
    pass

if __name__ == "__main__":
    server.run()
\`\`\`

### 2. Publier sur le registre privé

\`\`\`bash
# Build et publier sur PyPI privé
python -m build
twine upload --repository company dist/*
\`\`\`

### 3. Enregistrer dans BigMCP

\`\`\`bash
curl -X POST https://votre-bigmcp.com/api/v1/servers \\
  -H "Authorization: Bearer CLE_API_ADMIN" \\
  -d '{
    "server_id": "api-interne",
    "name": "API Interne",
    "install_type": "pip",
    "install_package": "internal-api-mcp",
    "command": "python",
    "args": ["-m", "internal_api_mcp.server"],
    "env": {
      "INTERNAL_API_KEY": "\${INTERNAL_API_KEY}",
      "INTERNAL_API_URL": "https://api.internal.company.com"
    },
    "auto_start": true
  }'
\`\`\`

### 4. Configurer les identifiants utilisateur

Chaque utilisateur ajoute sa \`INTERNAL_API_KEY\` dans la page Services.

### 5. Utiliser dans Claude

\`\`\`
"Obtenir les détails du client pour l'ID 12345"
"Créer un ticket de support pour le problème de connexion"
\`\`\`

## Limites et quotas

| Ressource | Community | Enterprise |
|-----------|-----------|------------|
| Serveurs personnalisés | 1 | Illimité |
| Serveurs actifs | 3 | Illimité |
| Identifiants par serveur | 5 | Illimité |

## Dépannage

### Le serveur ne démarre pas

\`\`\`bash
# Vérifier les logs serveur
docker compose logs -f backend

# Problèmes courants :
# - Package non trouvé : vérifier install_package et accès au registre
# - Commande non trouvée : s'assurer que la commande est dans PATH
# - Permission refusée : vérifier les permissions fichier pour scripts locaux
\`\`\`

### Les outils n'apparaissent pas

1. Vérifier que le statut du serveur est "running"
2. Vérifier que le serveur implémente correctement MCP \`tools/list\`
3. Consulter les logs backend pour les erreurs de découverte

### Erreurs d'identifiants

1. Vérifier que les noms d'identifiants correspondent exactement (sensible à la casse)
2. Vérifier que l'utilisateur a ajouté les identifiants requis
3. S'assurer que les identifiants ont le bon format (pas d'espaces)

## Bonnes pratiques de sécurité

1. **Utilisez la gestion des secrets** - Stockez les valeurs sensibles dans un vault, injectez à l'exécution
2. **Permissions minimales** - N'accordez que l'accès requis aux systèmes internes
3. **Journalisation d'audit** - Surveillez quels utilisateurs accèdent à quels outils
4. **Épinglage de version** - Épinglez les versions de packages pour éviter les attaques supply chain
5. **Isolation réseau** - Exécutez les conteneurs dans des réseaux isolés si possible
`,
  scaling: `
# Scaling & Performance

Optimisez votre instance BigMCP auto-hebergee pour les charges de production.

## Utilisation des ressources

Chaque serveur MCP fonctionne comme un **processus OS separe** (subprocess Node.js ou Python). Quand un utilisateur se connecte via un client IA, BigMCP demarre les serveurs necessaires a la demande.

| Composant | Utilisation memoire |
|-----------|---------------------|
| Backend (processus de base) | ~200 Mo fixe |
| Chaque serveur MCP (Node.js) | ~27 Mo supplementaire |
| PostgreSQL | 45-256 Mo (configurable) |
| Redis (cache + rate limiting) | 3-50 Mo |
| Frontend + Nginx | ~15 Mo |

### Formule de capacite

\`\`\`
Subprocess max = (Limite memoire backend - 200 Mo) / 27 Mo

Utilisateurs simultanes max = Subprocess max / serveurs moyens par utilisateur
\`\`\`

**Exemple :** Avec une limite backend de 4 Go et une moyenne de 3 serveurs par utilisateur :
- Subprocess max = (4096 - 200) / 27 = ~144
- Utilisateurs simultanes max = 144 / 3 = **~48 utilisateurs**

## Isolation des ressources

BigMCP fournit une isolation multi-tenant complete :

1. **Isolation processus** — Chaque utilisateur dispose de ses propres processus MCP. Un crash d'un serveur d'un utilisateur ne peut pas affecter un autre utilisateur.
2. **Isolation des credentials** — Les identifiants sont resolus par utilisateur au demarrage de chaque serveur. Aucun utilisateur ne peut acceder aux secrets d'un autre.
3. **Isolation du rate limiting** — Chaque utilisateur a ses propres compteurs de limitation. L'activite d'un utilisateur ne peut pas epuiser le quota d'un autre.

## Variables de configuration

Tous les parametres de scaling sont configures via des variables d'environnement dans votre \`docker-compose.yml\` :

### Pool de serveurs

| Variable | Defaut | Description |
|----------|--------|-------------|
| \`POOL_MAX_SERVERS_PER_USER\` | 5 | Serveurs MCP simultanes max par utilisateur |
| \`POOL_MAX_TOTAL_SERVERS\` | 50 | Serveurs MCP max globalement |
| \`POOL_CLEANUP_TIMEOUT_MINUTES\` | 5 | Minutes d'inactivite avant arret d'un serveur |
| \`POOL_CLEANUP_INTERVAL_SECONDS\` | 30 | Frequence de verification du nettoyage |

### Limitation de debit

| Route | Requetes/min | Raison |
|-------|-------------|--------|
| \`/api/v1/api-keys/\` | 30 | Sensible — creation/revocation de cles |
| \`/api/v1/credentials/\` | 50 | Sensible — acces aux secrets |
| \`/api/v1/auth/\` | 100 | Login/register — rafales legitimes |
| \`/api/v1/marketplace/\` | 100 | Public — navigation marketplace |
| Toutes les autres routes | 200 | Defaut (configurable via \`RATE_LIMIT_DEFAULT\`) |

### Base de donnees

| Variable | Defaut | Description |
|----------|--------|-------------|
| Pool size | 5 | Connexions persistantes |
| Max overflow | 10 | Connexions supplementaires en charge (total max : 15) |
| Pool recycle | 300s | Intervalle de renouvellement des connexions |

## Profils de configuration

### Petit deploiement (< 10 utilisateurs)

Fonctionne avec les parametres par defaut. Prerequis minimum :

- 2 coeurs CPU, 4 Go RAM
- Limite memoire backend : 1 Go

\`\`\`yaml
environment:
  - POOL_MAX_SERVERS_PER_USER=5
  - POOL_MAX_TOTAL_SERVERS=50
  - POOL_CLEANUP_TIMEOUT_MINUTES=5
  - RATE_LIMIT_DEFAULT=200
\`\`\`

### Deploiement moyen (10-50 utilisateurs)

Prerequis : 4+ coeurs CPU, 16 Go RAM

\`\`\`yaml
# Service backend
deploy:
  resources:
    limits:
      memory: 8G
    reservations:
      memory: 2G

environment:
  - POOL_MAX_SERVERS_PER_USER=10
  - POOL_MAX_TOTAL_SERVERS=150
  - POOL_CLEANUP_TIMEOUT_MINUTES=3
  - RATE_LIMIT_DEFAULT=150

# Service PostgreSQL
deploy:
  resources:
    limits:
      memory: 512M
command:
  - postgres
  - -c
  - shared_buffers=128MB
  - -c
  - effective_cache_size=256MB
  - -c
  - work_mem=8MB
\`\`\`

### Grand deploiement (50-200 utilisateurs)

Prerequis : 8+ coeurs CPU, 32 Go RAM

\`\`\`yaml
# Service backend
deploy:
  resources:
    limits:
      memory: 20G
    reservations:
      memory: 4G

environment:
  - POOL_MAX_SERVERS_PER_USER=8
  - POOL_MAX_TOTAL_SERVERS=300
  - POOL_CLEANUP_TIMEOUT_MINUTES=2
  - RATE_LIMIT_DEFAULT=100

# Service PostgreSQL
deploy:
  resources:
    limits:
      memory: 1G
command:
  - postgres
  - -c
  - shared_buffers=256MB
  - -c
  - effective_cache_size=512MB
  - -c
  - work_mem=16MB
  - -c
  - max_connections=200
\`\`\`

## Checklist de production

### Memoire

- Definir la limite memoire du backend a au moins 4 Go
- Definir la limite memoire de PostgreSQL a au moins 256 Mo
- Ajouter un swap de securite (2 Go recommande)
- Verifier que \`POOL_MAX_TOTAL_SERVERS\` tient dans votre budget memoire

### Base de donnees

- Activer les TCP keepalives (evite les connexions mortes dans Docker)
- Definir \`idle_in_transaction_session_timeout\` pour eviter les fuites de connexion
- Augmenter \`shared_buffers\` proportionnellement a la memoire disponible

### Swap (filet de securite)

L'ajout de swap empeche le systeme de tuer des processus lors de pics de memoire temporaires :

\`\`\`bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl vm.swappiness=10
echo 'vm.swappiness=10' >> /etc/sysctl.conf
\`\`\`

Definir \`swappiness=10\` garantit que le swap n'est utilise qu'en dernier recours.

## Monitoring

### Endpoint Pool Stats

\`GET /api/v1/admin/pool-stats\` retourne l'utilisation des ressources en temps reel :

\`\`\`json
{
  "pool": {
    "total_users": 12,
    "total_servers": 35,
    "max_servers_per_user": 10,
    "max_total_servers": 150,
    "cleanup_timeout_minutes": 5,
    "servers_per_user": {"user1": 4, "user2": 3}
  },
  "cache": {
    "backend": "redis",
    "keys_count": 42,
    "hit_rate": "87.3%"
  },
  "redis_connected": true,
  "active_sse_sessions": 5
}
\`\`\`

### Metriques cles a surveiller

| Metrique | Seuil d'alerte | Action |
|----------|----------------|--------|
| Total serveurs / max | > 80% | Augmenter \`POOL_MAX_TOTAL_SERVERS\` ou la memoire backend |
| Memoire PostgreSQL | > 70% de la limite | Augmenter la limite memoire PostgreSQL |
| Memoire backend | > 85% de la limite | Augmenter la limite memoire backend |
| Taux de cache | < 50% | Verifier la connectivite Redis, parametres TTL |

### Monitoring Docker

\`\`\`bash
# Utilisation des ressources en direct
docker stats

# Details des processus backend
docker top votre-conteneur-gateway -o pid,rss,args

# Connexions PostgreSQL actives
docker exec votre-conteneur-postgres psql -U user -d bigmcp \
  -c "SELECT count(*) FROM pg_stat_activity;"
\`\`\`

## Architecture du cache

BigMCP utilise un cache distribue avec fallback automatique :

- **Redis** (production) — Partage entre les redemarrages, necessaire pour le multi-instance
- **In-Memory** (fallback) — Automatique si Redis indisponible, par instance uniquement

Le cache stocke les listes d'outils par utilisateur, permettant des reponses instantanees (< 5 ms) quand un client IA se connecte. Sans cache, la premiere connexion necessite le demarrage des serveurs MCP (30-60 secondes).

### Invalidation du cache

Les caches d'outils sont automatiquement invalides quand :
- La visibilite d'un serveur est modifiee depuis le panneau d'administration
- Un serveur est ajoute ou supprime
- Les identifiants d'un utilisateur sont mis a jour

Les clients IA connectes sont notifies en temps reel pour rafraichir leur liste d'outils.

### Configuration Redis

Redis est inclus dans la configuration Docker Compose avec des parametres adaptes :

\`\`\`yaml
redis:
  image: redis:7-alpine
  command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
\`\`\`

Si Redis devient indisponible, le systeme bascule automatiquement sur le cache en memoire sans erreur visible pour l'utilisateur.

## Eviction LRU

Quand les limites de ressources sont atteintes, BigMCP evince automatiquement les serveurs les moins recemment utilises :

1. **Limite par utilisateur** — Si un utilisateur atteint \`POOL_MAX_SERVERS_PER_USER\`, son serveur inactif le plus ancien est arrete avant d'en demarrer un nouveau.
2. **Limite globale** — Si le total atteint \`POOL_MAX_TOTAL_SERVERS\`, le serveur globalement le plus ancien est arrete (peut affecter n'importe quel utilisateur).

Cela garantit la stabilite du systeme sous charge tout en priorisant les activites en cours.
`,
  monitoring: `
# Monitoring

Gardez votre instance BigMCP en bonne santé grâce au monitoring intégré.

## Pourquoi monitorer ?

Le monitoring vous permet de :

- **Détecter les problèmes tôt** - Repérez les soucis avant que vos utilisateurs ne les remarquent
- **Planifier la capacité** - Sachez quand augmenter les ressources
- **Suivre l'utilisation** - Comprenez comment votre équipe utilise BigMCP
- **Diagnostiquer rapidement** - Trouvez la cause racine des incidents

## Comment ça fonctionne

\`\`\`mermaid
flowchart LR
    subgraph bigmcp [" "]
        APP(["<b>BigMCP</b><br/>endpoint /metrics"])
    end

    subgraph monitoring [" "]
        PROM(["<b>Prometheus</b><br/>Collecte les métriques"])
        GRAF(["<b>Grafana</b><br/>Visualise les données"])
    end

    subgraph you [" "]
        DASH(["<b>Vous</b><br/>Consultez les tableaux de bord"])
    end

    APP -->|"toutes les 15s"| PROM
    PROM --> GRAF
    GRAF --> DASH

    style bigmcp fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style monitoring fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style you fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style APP fill:#D97757,stroke:#c4624a,color:#ffffff
    style PROM fill:#f4e4df,stroke:#c4624a,color:#262626
    style GRAF fill:#f4e4df,stroke:#c4624a,color:#262626
    style DASH fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

BigMCP expose un endpoint \`/metrics\` que Prometheus interroge périodiquement. Vous visualisez ensuite les données dans des tableaux de bord Grafana.

## Démarrage rapide

### Étape 1 : Vérifiez que les métriques fonctionnent

Lancez cette commande pour vérifier que les métriques sont disponibles :

\`\`\`bash
curl http://localhost:8001/metrics
\`\`\`

Vous devriez voir une sortie comme :
\`\`\`
# HELP bigmcp_pool_servers_total Number of active MCP servers
# TYPE bigmcp_pool_servers_total gauge
bigmcp_pool_servers_total 5
...
\`\`\`

> **Astuce :** Si vous voyez des métriques s'afficher, le monitoring BigMCP est prêt à l'emploi !

### Étape 2 : Connectez Prometheus

Ajoutez BigMCP à votre configuration Prometheus :

\`\`\`yaml
# prometheus.yml
scrape_configs:
  - job_name: 'bigmcp'
    static_configs:
      - targets: ['localhost:8001']
    scrape_interval: 15s
\`\`\`

### Étape 3 : Visualisez dans Grafana

Une fois que Prometheus collecte les données, vous pouvez :
1. Ouvrir Grafana (généralement sur \`http://localhost:3001\`)
2. Ajouter Prometheus comme source de données
3. Créer des tableaux de bord ou importer nos panels recommandés

## Que pouvez-vous surveiller ?

### Métriques essentielles

| Quoi surveiller | Métrique | Pourquoi c'est important |
|-----------------|----------|--------------------------|
| Serveurs actifs | \`bigmcp_pool_servers_total\` | Montre la charge actuelle |
| Utilisateurs actifs | \`bigmcp_pool_users_total\` | Suit l'utilisation simultanée |
| Taux de requêtes | \`bigmcp_http_requests_total\` | Comprendre les patterns de trafic |
| Temps de réponse | \`bigmcp_http_request_duration_seconds\` | Détecter les ralentissements |
| Efficacité du cache | \`bigmcp_cache_hits_total\` | Optimiser les performances |

### Panels de tableau de bord recommandés

Construisez un tableau de bord avec ces vues essentielles :

1. **Utilisateurs & Serveurs actifs** - Approchez-vous de la capacité ?
2. **Taux de requêtes** - Trafic au fil du temps
3. **Taux d'erreurs** - Pourcentage de requêtes échouées
4. **Temps de réponse** - Latence P50, P95, P99
5. **Taux de hit cache** - Le cache fonctionne-t-il efficacement ?

## Configurer des alertes

Soyez notifié quand quelque chose nécessite votre attention. Voici une alerte simple pour un taux d'erreur élevé :

\`\`\`yaml
# Dans vos règles d'alerte Prometheus
groups:
  - name: bigmcp-alerts
    rules:
      - alert: TauxErreurEleve
        expr: |
          sum(rate(bigmcp_http_requests_total{status=~"5.."}[5m]))
          / sum(rate(bigmcp_http_requests_total[5m])) > 0.05
        for: 5m
        annotations:
          summary: "Le taux d'erreur BigMCP dépasse 5%"
\`\`\`

> **Note :** Cette alerte se déclenche quand plus de 5% des requêtes échouent sur une période de 5 minutes.

## Ajouter Prometheus & Grafana

Vous n'avez pas encore d'infrastructure de monitoring ? Ajoutez-la à votre Docker Compose :

\`\`\`yaml
services:
  prometheus:
    image: prom/prometheus:v2.47.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.1.0
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
\`\`\`

Accédez à Grafana sur \`http://localhost:3001\` (identifiants : admin / admin).

## Considérations de sécurité

L'endpoint \`/metrics\` est ouvert par défaut pour la compatibilité Prometheus. En production, protégez-le en :

1. **Isolation réseau** - Exposez uniquement sur votre réseau de monitoring interne
2. **Authentification via reverse proxy** - Ajoutez une authentification via Nginx
3. **Règles de firewall** - Bloquez l'accès externe au port 8001

## Dépannage

### Pas de données dans Grafana ?

1. Vérifiez que BigMCP tourne : \`docker ps | grep backend\`
2. Vérifiez que Prometheus peut joindre BigMCP : \`curl http://localhost:8001/metrics\`
3. Vérifiez que la configuration Prometheus pointe vers le bon hôte

### Les métriques semblent obsolètes ?

Vérifiez les cibles Prometheus sur \`http://localhost:9090/targets\` - BigMCP devrait être marqué "UP".

## Prochaines étapes

- Configurez [Sauvegarde & Restauration](/docs/self-hosting/backup) pour protéger vos données
- Consultez [Scaling & Performance](/docs/self-hosting/scaling) pour la planification de capacité
`,
  backup: `
# Sauvegarde & Restauration

Protégez vos données BigMCP avec des sauvegardes régulières. Ce guide vous montre comment créer des sauvegardes et les restaurer en cas de besoin.

## Pourquoi sauvegarder ?

Les sauvegardes sont votre filet de sécurité. Elles vous protègent contre :

- **Pannes matérielles** - Les serveurs peuvent tomber en panne de façon inattendue
- **Erreurs humaines** - Les suppressions accidentelles arrivent
- **Corruption de données** - Bugs logiciels ou coupures de courant
- **Incidents de sécurité** - Récupération rapide en cas de compromission

> **Bonne nouvelle :** BigMCP simplifie les sauvegardes avec des scripts fournis. Configurez une fois, et vos données sont protégées automatiquement.

## Comment ça fonctionne

\`\`\`mermaid
flowchart LR
    subgraph bigmcp [" "]
        DB(["<b>PostgreSQL</b><br/>Vos données"])
        ENV(["<b>Fichier .env</b><br/>Votre config"])
    end

    subgraph backup [" "]
        SCRIPT(["<b>Script de sauvegarde</b><br/>Automatisé quotidiennement"])
    end

    subgraph storage [" "]
        REMOTE(["<b>Stockage distant</b><br/>Sécurisé & chiffré"])
    end

    DB -->|"pg_dump"| SCRIPT
    ENV -->|"copie"| SCRIPT
    SCRIPT -->|"chiffré"| REMOTE

    style bigmcp fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style backup fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style storage fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style DB fill:#D97757,stroke:#c4624a,color:#ffffff
    style ENV fill:#f4e4df,stroke:#c4624a,color:#262626
    style SCRIPT fill:#f4e4df,stroke:#c4624a,color:#262626
    style REMOTE fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

## Ce qui est sauvegardé

| Composant | Priorité | Pourquoi |
|-----------|----------|----------|
| **Base PostgreSQL** | Critique | Tous vos utilisateurs, identifiants et paramètres |
| **Fichier \`.env\`** | Critique | Vos clés de chiffrement et configuration |
| Vecteurs Qdrant | Optionnel | Peuvent être régénérés depuis les données |
| Logs applicatifs | Optionnel | Uniquement pour le débogage |

> **Important :** Sauvegardez toujours la base de données ET le fichier \`.env\`. Sans les clés de chiffrement du \`.env\`, les identifiants chiffrés ne peuvent pas être récupérés.

## Créer votre première sauvegarde

### Étape 1 : Lancez le script de sauvegarde

Nous fournissons un script prêt à l'emploi :

\`\`\`bash
./scripts/ops/backup.sh
\`\`\`

Ceci crée un fichier de sauvegarde compressé comme \`bigmcp_20260218_120000.sql.gz\` dans le dossier \`./backups/\`.

### Étape 2 : Transférez vers un stockage sécurisé

Ne gardez jamais les sauvegardes uniquement sur le même serveur ! Copiez vers un stockage distant :

\`\`\`bash
scp ./backups/bigmcp_*.sql.gz user@backup-server:/backups/
\`\`\`

### Étape 3 : Supprimez la copie locale

Pour la sécurité, supprimez la sauvegarde locale après la copie :

\`\`\`bash
rm ./backups/bigmcp_*.sql.gz
\`\`\`

> **Astuce :** Vous voulez sauvegarder dans un dossier personnalisé ? Ajoutez simplement le chemin : \`./scripts/ops/backup.sh /mon/dossier/backups\`

## Restaurer depuis une sauvegarde

### Quand restaurer

- Le matériel du serveur a lâché et vous en avez configuré un nouveau
- La base de données est corrompue
- Quelqu'un a accidentellement supprimé des données importantes
- Vous voulez migrer vers un serveur différent

### Étape 1 : Récupérez votre fichier de sauvegarde

Copiez la sauvegarde depuis votre stockage distant :

\`\`\`bash
scp user@backup-server:/backups/bigmcp_20260218.sql.gz ./
\`\`\`

### Étape 2 : Lancez le script de restauration

\`\`\`bash
./scripts/ops/restore.sh ./bigmcp_20260218.sql.gz
\`\`\`

Le script demandera une confirmation avant de continuer (il écrasera votre base de données actuelle).

### Étape 3 : Vérifiez que tout fonctionne

\`\`\`bash
curl http://localhost:8001/health
\`\`\`

Vous devriez voir une réponse saine. Essayez de vous connecter à BigMCP pour confirmer que vos données sont restaurées.

## Configurer les sauvegardes automatiques

Ne comptez pas sur les sauvegardes manuelles ! Planifiez-les automatiquement avec cron.

### Choisissez votre fréquence

| Taille de l'équipe | Fréquence recommandée | Conserver pendant |
|--------------------|-----------------------|-------------------|
| Petite équipe (<50 utilisateurs) | Quotidienne | 7 jours |
| Équipe moyenne (50-500) | Toutes les 12 heures | 14 jours |
| Grande équipe (500+) | Toutes les 6 heures | 30 jours |

### Ajoutez au crontab

Éditez votre crontab avec \`crontab -e\` et ajoutez :

\`\`\`bash
# Sauvegarde tous les jours à 3h du matin
0 3 * * * cd /opt/bigmcp && ./scripts/ops/backup.sh >> /var/log/bigmcp-backup.log 2>&1

# Nettoyage des anciennes sauvegardes chaque dimanche (garder 7 jours)
0 4 * * 0 find /opt/bigmcp/backups -name "*.sql.gz" -mtime +7 -delete
\`\`\`

> **Conseil de pro :** Après la configuration, attendez la première sauvegarde automatique, puis vérifiez \`/var/log/bigmcp-backup.log\` pour vous assurer que ça a fonctionné.

## Bonnes pratiques de sécurité

### À faire ✓

- **Stockez les sauvegardes à distance** - Serveur différent ou stockage cloud
- **Chiffrez avant d'envoyer** - Utilisez le chiffrement GPG
- **Testez la restauration régulièrement** - Au moins une fois par mois
- **Documentez votre processus** - Pour que n'importe qui dans l'équipe puisse le faire

### À éviter ✗

- Garder les sauvegardes uniquement sur le serveur de production
- Stocker des sauvegardes non chiffrées dans le cloud
- Partager les sauvegardes par email ou chat
- Oublier de sauvegarder le fichier \`.env\`

### Chiffrer vos sauvegardes

Avant d'envoyer vers le stockage cloud, chiffrez votre sauvegarde :

\`\`\`bash
# Chiffrer la sauvegarde
gpg --encrypt --recipient votre-cle-gpg backup.sql.gz

# Pour restaurer, d'abord déchiffrer
gpg --decrypt backup.sql.gz.gpg > backup.sql.gz
\`\`\`

## Scénarios de reprise après sinistre

### "Mon serveur est complètement mort"

1. Configurez un nouveau serveur avec Docker
2. Clonez le dépôt BigMCP
3. Restaurez votre fichier \`.env\` depuis la sauvegarde sécurisée
4. Démarrez les services : \`docker-compose up -d\`
5. Attendez que PostgreSQL démarre
6. Restaurez la base : \`./scripts/ops/restore.sh backup.sql.gz\`
7. Vérifiez : \`curl http://localhost:8001/health\`

### "La base de données est corrompue"

1. Arrêtez le backend : \`docker stop bigmcp-backend\`
2. Trouvez votre sauvegarde valide la plus récente
3. Restaurez : \`./scripts/ops/restore.sh backup.sql.gz\`
4. Redémarrez : \`docker start bigmcp-backend\`

### "Quelqu'un a supprimé des données importantes"

Identique à la corruption de base de données - restaurez depuis la sauvegarde la plus récente avant la suppression.

## Dépannage

### Le script de sauvegarde dit "conteneur non démarré"

Vérifiez si PostgreSQL tourne :

\`\`\`bash
docker ps | grep postgres
\`\`\`

S'il ne tourne pas, démarrez-le :

\`\`\`bash
docker-compose up -d postgres
\`\`\`

### La restauration échoue avec "permission refusée"

Vérifiez que l'utilisateur de la base existe :

\`\`\`bash
docker exec bigmcp-postgres psql -U bigmcp -c "\\du"
\`\`\`

### Le fichier de sauvegarde est très volumineux

Vérifiez la taille réelle :

\`\`\`bash
gunzip -l backup.sql.gz
\`\`\`

Pour les très grandes bases (>10 Go), envisagez des stratégies de sauvegarde incrémentale.

## Prochaines étapes

- Configurez le [Monitoring](/docs/self-hosting/monitoring) pour détecter les problèmes avant qu'ils ne deviennent des catastrophes
- Consultez [Scaling & Performance](/docs/self-hosting/scaling) pour la planification de capacité
`,
}
