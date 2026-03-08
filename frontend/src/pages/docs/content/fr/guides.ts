/**
 * Documentation Guides - Contenu en français
 *
 * Guides pratiques pour les fonctionnalités BigMCP.
 */

export const guidesContent: Record<string, string> = {
  marketplace: `
# Découvrir les serveurs

Le Marketplace BigMCP est votre portail pour découvrir et connecter des serveurs MCP.

## Parcourir les serveurs

Le marketplace agrège les serveurs MCP depuis plusieurs sources :

- **Registre officiel** - Serveurs vérifiés et approuvés
- **Registre NPM** - Packages communautaires avec le préfixe \`@mcp/\`
- **GitHub** - Dépôts open source de serveurs MCP

### Catégories

Les serveurs sont organisés par catégorie :

- **Données & Analytique** - Connecteurs de bases de données, outils BI
- **Développement** - Git, CI/CD, analyse de code
- **Productivité** - Documents, calendriers, notes
- **Communication** - Email, messagerie, notifications
- **IA & ML** - APIs de modèles, embeddings, inférence
- **Autre** - Outils divers

### Recherche

Utilisez la barre de recherche pour trouver des serveurs par :
- Nom ou description
- Capacités (outils, ressources)
- Mots-clés et tags

## Connecter un serveur

### 1. Sélectionner un serveur

Cliquez sur une carte de serveur pour voir ses détails :
- Outils disponibles et leurs descriptions
- Identifiants requis
- Options de configuration

### 2. Configurer les identifiants

La plupart des serveurs nécessitent des identifiants pour fonctionner :

1. Cliquez sur **Connecter** sur la carte du serveur
2. Remplissez les identifiants requis (clés API, tokens, etc.)
3. Optionnellement, définissez un nom de connexion personnalisé
4. Cliquez sur **Connecter le serveur**

### 3. Vérifier la connexion

Une fois connecté, le serveur :
- Apparaît dans votre page **Services**
- Affiche le statut de connexion (Actif, API uniquement, En veille ou Désactivé)
- Liste tous les outils disponibles
`,

  'tool-groups': `
# Toolboxes

Les Toolboxes sont l'une des fonctionnalités les plus puissantes de BigMCP. Elles vous permettent de créer des **serveurs MCP spécialisés** en regroupant des outils spécifiques.

## Qu'est-ce qu'une Toolbox ?

Une Toolbox est une collection organisée d'outils qui peut être exposée comme un **serveur MCP dédié** via une clé API. Cela permet :

- **Agents spécialisés** - Créez des agents focalisés avec uniquement les outils pertinents
- **Contrôle d'accès** - Limitez les outils accessibles par une intégration
- **Sécurité** - Exposez des outils en lecture seule à certains clients, accès complet à d'autres
- **Organisation** - Regroupez les outils liés pour des cas d'usage spécifiques

## Comment fonctionnent les Toolboxes

\`\`\`mermaid
flowchart TB
    subgraph account [" "]
        SERVERS(["<b>Votre compte</b><br/>━━━━━━━━━━━━━<br/>GitHub · Notion · Slack · PostgreSQL<br/>45 outils au total"])
    end

    subgraph groups [" "]
        direction LR
        G1(["<b>Assistant Dev</b><br/>12 outils"])
        G2(["<b>Lecture seule</b><br/>20 outils"])
        G3(["<b>Agent Data</b><br/>8 outils"])
    end

    subgraph keys [" "]
        direction LR
        K1(["<b>Claude Dev</b><br/>→ 12 outils"])
        K2(["<b>Bot Public</b><br/>→ 20 outils"])
        K3(["<b>Analytics</b><br/>→ 8 outils"])
    end

    SERVERS --> G1 & G2 & G3
    G1 --> K1
    G2 --> K2
    G3 --> K3

    style account fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style groups fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style keys fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style SERVERS fill:#D97757,stroke:#c4624a,color:#ffffff
    style G1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style G2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style G3 fill:#f4e4df,stroke:#c4624a,color:#262626
    style K1 fill:#ffffff,stroke:#d4d4d4,color:#262626
    style K2 fill:#ffffff,stroke:#d4d4d4,color:#262626
    style K3 fill:#ffffff,stroke:#d4d4d4,color:#262626
\`\`\`

Quand vous créez une clé API liée à une Toolbox, cette clé **ne voit et ne peut exécuter que** les outils de ce groupe.

## Créer une Toolbox

### 1. Naviguer vers les Toolboxes

Allez dans **Services** → onglet **Toolboxes** → **Créer un groupe**

### 2. Configurer le groupe

- **Nom** : Nom descriptif (ex: "Agent Support Client")
- **Description** : À quoi sert ce groupe
- **Visibilité** :
  - Privé (vous seul)
  - Organisation (membres de l'équipe)
  - Public (découvrable)

### 3. Ajouter des outils

Sélectionnez les outils à inclure depuis vos serveurs connectés :

1. Parcourez les outils disponibles par serveur
2. Cochez les outils que vous souhaitez inclure
3. Optionnellement, réordonnez pour la priorité d'affichage
4. Cliquez sur **Enregistrer le groupe**

### 4. Ajouter des compositions (Optionnel)

Vous pouvez aussi ajouter des compositions sauvegardées (workflows) à une Toolbox. Elles apparaissent comme des outils \`workflow_*\` lors de l'accès via MCP.

## Lier une Toolbox à une clé API

C'est l'étape clé qui crée un serveur MCP spécialisé :

1. Allez dans la page **Clés API**
2. Cliquez sur **Créer une clé API**
3. Sélectionnez votre Toolbox dans le menu déroulant
4. Définissez les scopes appropriés (\`tools:read\`, \`tools:execute\`)
5. Copiez la clé générée

Maintenant, tout client MCP utilisant cette clé ne verra et n'accèdera qu'aux outils de ce groupe.

## Cas d'usage

### Agent d'analytique en lecture seule

Créez un groupe avec uniquement les outils \`list_*\`, \`get_*\`, \`read_*\` et \`query_*\`. Liez-le à une clé API pour un bot de reporting qui peut lire mais jamais modifier les données.

### Agent support client

Regroupez les outils pour :
- Lire les données client
- Consulter l'historique des commandes
- Créer des tickets de support
- Envoyer des notifications

Excluez les outils pour les remboursements, suppression de compte ou actions admin.

### Assistant développement

Incluez :
- GitHub : create_issue, list_prs, read_file
- Notion : search_docs, read_page
- Slack : send_message (vers le canal dev uniquement)

### Pipeline d'automatisation

Créez un groupe minimal pour une automatisation spécifique :
- Un outil de requête base de données
- Un outil de notification
- Un outil de logging

Cela limite les dégâts si l'automatisation est compromise.

## Bonnes pratiques

1. **Principe du moindre privilège** - N'incluez que les outils vraiment nécessaires
2. **Noms descriptifs** - Le but doit être clair dès le nom
3. **Documentez l'usage** - Utilisez le champ description pour expliquer l'utilisation prévue
4. **Révision régulière** - Vérifiez périodiquement si les outils sont toujours nécessaires
5. **Séparez les environnements** - Utilisez différents groupes pour dev/staging/prod

## Accéder aux Toolboxes via MCP

Une fois que vous avez une clé API liée à une Toolbox, configurez votre client MCP :

\`\`\`json
{
  "mcpServers": {
    "mon-agent-specialise": {
      "command": "npx",
      "args": [
        "-y", "@anthropic/mcp-proxy",
        "--endpoint", "https://bigmcp.cloud/mcp/sse",
        "--api-key", "mcphub_sk_votre_cle_ici"
      ]
    }
  }
}
\`\`\`

Le client ne verra que les outils de la Toolbox liée.
`,

  'api-keys': `
# Clés API

Les clés API fournissent un accès sécurisé et scopé aux fonctionnalités de BigMCP pour les intégrations externes.

## Vue d'ensemble

Les clés API permettent :
- **Accès à la passerelle MCP** - Connectez Claude Desktop, Cursor ou des clients personnalisés
- **Accès à l'API REST** - Exécutez des outils et compositions programmatiquement
- **Filtrage par Toolbox** - Exposez uniquement des outils spécifiques par clé
- **Piste d'audit** - Suivez l'utilisation par clé

## Format de clé

Les clés API BigMCP suivent ce format :

\`\`\`
mcphub_sk_<caracteres_aleatoires>
\`\`\`

Exemple : \`mcphub_sk_abc123def456ghi789jkl012mno345\`

## Créer une clé API

### 1. Naviguer vers les clés API

Allez dans **Paramètres** → **Clés API** → **Créer une clé**

### 2. Configurer la clé

| Champ | Description |
|-------|-------------|
| **Nom** | Nom descriptif (ex: "Claude Desktop - Travail") |
| **Description** | Notes optionnelles sur l'utilisation |
| **Scopes** | Permissions accordées (voir ci-dessous) |
| **Toolbox** | Optionnel - restreindre à des outils spécifiques |
| **Expiration** | Date d'expiration optionnelle |

### 3. Sélectionner les scopes

Scopes disponibles :

| Scope | Permission |
|-------|------------|
| \`tools:read\` | Lister et voir les métadonnées des outils |
| \`tools:execute\` | Exécuter les outils |
| \`credentials:read\` | Voir les métadonnées des identifiants |
| \`credentials:write\` | Créer/modifier des identifiants |
| \`servers:read\` | Voir les configurations serveur |
| \`servers:write\` | Gérer les serveurs |
| \`admin\` | Accès administrateur complet |

**Recommandé pour les clients MCP :** \`tools:read\` + \`tools:execute\`

### 4. Lier à une Toolbox (Optionnel mais recommandé)

Sélectionnez une Toolbox pour restreindre les outils accessibles avec cette clé :

- **Sans Toolbox** : La clé accède à TOUS vos outils
- **Avec Toolbox** : La clé n'accède qu'aux outils de ce groupe

C'est le mécanisme pour créer des agents spécialisés.

### 5. Enregistrer et copier

**Important** : La clé complète n'est affichée qu'une seule fois. Copiez-la immédiatement et stockez-la de manière sécurisée.

## Utiliser les clés API

### Passerelle MCP (SSE)

Pour les clients MCP comme Claude Desktop :

\`\`\`bash
# Se connecter à la passerelle MCP
GET https://bigmcp.cloud/mcp/sse
Authorization: Bearer mcphub_sk_votre_cle_ici
\`\`\`

### API REST

Pour les appels API HTTP :

\`\`\`bash
# Lister les outils disponibles
curl https://bigmcp.cloud/api/v1/tools \\
  -H "Authorization: Bearer mcphub_sk_votre_cle_ici"

# Exécuter un binding d'outil
curl -X POST https://bigmcp.cloud/api/v1/tool-bindings/{id}/execute \\
  -H "Authorization: Bearer mcphub_sk_votre_cle_ici" \\
  -H "Content-Type: application/json" \\
  -d '{"parameters": {"title": "Bonjour"}}'
\`\`\`

## Gérer les clés

### Voir toutes les clés

La page Clés API affiche :
- Nom et préfixe de la clé (8 premiers caractères)
- Toolbox associée (le cas échéant)
- Scopes accordés
- Date de création
- Dernière utilisation

### Révoquer une clé

1. Trouvez la clé dans la liste
2. Cliquez sur **Révoquer**
3. Confirmez l'action

Les clés révoquées cessent immédiatement de fonctionner. Cette action est irréversible.

### Faire tourner une clé

Pour la sécurité, faites tourner vos clés périodiquement :

1. Créez une nouvelle clé avec la même configuration
2. Mettez à jour vos intégrations pour utiliser la nouvelle clé
3. Vérifiez que tout fonctionne
4. Révoquez l'ancienne clé

## Bonnes pratiques de sécurité

1. **Activez la 2FA** - Protégez votre compte avec [l'authentification à deux facteurs](/docs/concepts/security)
2. **Une clé par intégration** - Ne partagez pas les clés entre différents usages
3. **Utilisez les Toolboxes** - Limitez l'accès aux outils nécessaires uniquement
4. **Scopes minimaux** - N'accordez que les permissions requises
5. **Définissez une expiration** - Pour les intégrations temporaires, fixez une date d'expiration
6. **Surveillez l'utilisation** - Vérifiez "dernière utilisation" pour détecter les accès non autorisés
7. **Rotation régulière** - Changez les clés périodiquement
8. **Jamais dans le code** - Gardez les clés hors du code source

## Clé API + Toolbox = Serveur spécialisé

La combinaison d'une clé API avec une Toolbox est puissante :

\`\`\`
Clé API : "Clé Bot Support"
├── Toolbox : "Support Client"
│   ├── get_customer_info
│   ├── list_orders
│   ├── create_ticket
│   └── send_notification
└── Exposé via : https://bigmcp.cloud/mcp/sse

Tout client utilisant cette clé ne voit QUE ces 4 outils,
comme si c'était un serveur MCP dédié au support.
\`\`\`

Cela permet :
- Différents profils Claude Desktop avec différentes capacités
- Multiples agents IA avec accès spécialisé
- Automatisation sécurisée avec permissions minimales
`,

  credentials: `
# Gérer les services

La page **Services** est votre tableau de bord central pour gérer tous les serveurs MCP connectés et leurs outils.

## Vue d'ensemble

Depuis la page Services, vous pouvez :
- Voir tous vos serveurs connectés
- Contrôler la visibilité des serveurs pour Claude
- Démarrer, arrêter et redémarrer les serveurs
- Supprimer les serveurs dont vous n'avez plus besoin
- Voir les outils disponibles de chaque serveur

## Organisation de la page Services

La page Services a deux vues principales :

### Onglet Serveurs
Affiche tous vos serveurs MCP connectés avec :
- Statut de connexion (Actif, API uniquement, En veille, Désactivé, Erreur)
- Nombre d'outils disponibles
- Toggle de visibilité pour Claude
- Contrôles serveur

### Onglet Toolboxes
Gérez les collections d'outils pour l'accès par clé API. Voir le [guide Toolboxes](/docs/guides/tool-groups) pour plus de détails.

## Statut des serveurs

Chaque serveur affiche l'un de ces statuts :

| Statut | Signification |
|--------|---------------|
| **Actif** | En cours d'exécution et visible pour Claude |
| **API uniquement** | En cours d'exécution mais masqué de Claude (API/Toolboxes uniquement) |
| **En veille** | Arrêté mais sera visible au démarrage |
| **Désactivé** | Arrêté et masqué |
| **Erreur** | Le serveur a rencontré un problème |

## Toggle de visibilité

Le toggle de visibilité contrôle si les outils d'un serveur sont disponibles pour Claude :

- **Visible (Activé)** - Claude peut voir et utiliser tous les outils de ce serveur
- **Masqué (Désactivé)** - Les outils sont masqués de Claude mais restent disponibles via clés API et Toolboxes

> **Astuce :** Masquez les serveurs dont vous n'avez besoin que pour les automatisations ou intégrations API spécifiques.

## Contrôles serveur

Pour chaque serveur connecté, vous pouvez :

| Action | Description |
|--------|-------------|
| **Démarrer** | Démarrer un serveur arrêté |
| **Arrêter** | Arrêter un serveur en cours d'exécution |
| **Redémarrer** | Redémarrer le serveur (utile après mise à jour des identifiants) |
| **Supprimer** | Supprimer le serveur et ses identifiants |

## Voir les outils

Cliquez sur la flèche d'expansion de n'importe quel serveur pour voir :
- Liste de tous les outils disponibles
- Descriptions des outils
- Date de création et horodatage de dernière utilisation

## Mettre à jour les identifiants

Pour mettre à jour les identifiants d'un serveur :
1. Supprimez la connexion actuelle du serveur
2. Reconnectez le serveur depuis le Marketplace
3. Entrez les nouveaux identifiants

> **Note :** L'édition directe des identifiants sera disponible dans une future mise à jour.

## Services d'équipe

Avec un **plan Team**, vous verrez un onglet supplémentaire "Serveurs d'équipe" avec les serveurs partagés par l'administrateur de votre organisation. Voir le [guide Services d'équipe](/docs/guides/team-services) pour plus de détails.

## Dépannage

### Le serveur affiche le statut "Erreur"
- Vérifiez que vos identifiants sont toujours valides
- Essayez de redémarrer le serveur
- Si persistant, supprimez et reconnectez avec de nouveaux identifiants

### Les outils n'apparaissent pas
- Assurez-vous que le serveur est en cours d'exécution (statut vert)
- Attendez quelques secondes pour la découverte des outils
- Vérifiez si le serveur expose effectivement des outils

### Le serveur ne démarre pas
- Vérifiez que vos identifiants sont corrects
- Vérifiez si le service externe est disponible
- Consultez les logs serveur pour des erreurs spécifiques
`,

  compositions: `
# Créer des compositions

Les compositions (aussi appelées Workflows) permettent de chaîner plusieurs outils ensemble en séquences automatisées réutilisables.

## Qu'est-ce qu'une composition ?

Une composition est une séquence sauvegardée d'appels d'outils qui :
- S'exécute dans l'ordre avec les données qui circulent entre les étapes
- Peut être déclenchée via API ou MCP
- Supporte les templates de paramètres et les mappings
- Suit l'historique d'exécution et les métriques

## Cycle de vie des compositions

\`\`\`mermaid
flowchart LR
    T(["<b>Temporaire</b><br/>Créé automatiquement"])
    V(["<b>Validé</b><br/>Testé et approuvé"])
    P(["<b>Production</b><br/>outils workflow_*"])

    T --> V --> P

    style T fill:#f4e4df,stroke:#c4624a,color:#262626
    style V fill:#f4e4df,stroke:#c4624a,color:#262626
    style P fill:#D97757,stroke:#c4624a,color:#ffffff
\`\`\`

1. **Temporaire** : Créé automatiquement depuis l'orchestration, expérimental
2. **Validé** : Testé et approuvé pour une utilisation régulière
3. **Production** : Stable, exposé comme outils \`workflow_*\` dans la passerelle MCP

## Convention de nommage des outils

Quand vous appelez \`list_tools\`, les outils sont retournés avec des **noms préfixés** pour l'unicité :

\`\`\`
Format : NomServeur__nom_outil_original

Exemples :
- Hostinger__list_organizations
- Grist__list_workspaces
- Notion__search_pages
- GitHub__create_issue
\`\`\`

**Utilisez toujours ces noms préfixés dans vos compositions.**

## Créer des compositions

### Via langage naturel (Recommandé)

1. Ouvrez le chat BigMCP ou connectez-vous via MCP
2. Décrivez ce que vous voulez accomplir
3. BigMCP analyse l'intention et suggère des outils
4. Exécutez la séquence
5. Si réussie, sauvegardez comme composition

### Via API

\`\`\`bash
POST /api/v1/compositions
{
  "name": "Triage Issues",
  "description": "Analyser et router les nouvelles issues",
  "steps": [
    {
      "id": "1",
      "tool": "GitHub__get_issue",
      "parameters": {"issue_number": "\${input.issue_number}"}
    },
    {
      "id": "2",
      "tool": "AI__analyze_text",
      "parameters": {"text": "\${step_1.body}"}
    },
    {
      "id": "3",
      "tool": "Slack__send_message",
      "parameters": {
        "channel": "#dev-alerts",
        "text": "Issue #\${input.issue_number}: \${step_2.summary}"
      }
    }
  ],
  "input_schema": {
    "type": "object",
    "properties": {
      "issue_number": {"type": "integer", "description": "Numéro d'issue GitHub"}
    },
    "required": ["issue_number"]
  }
}
\`\`\`

## Mappings de données - Syntaxe de référence

Les compositions supportent le flux de données entre étapes avec la syntaxe de template \`\${...}\` :

| Syntaxe | Description | Exemple |
|---------|-------------|---------|
| \`\${input.param}\` | Paramètre d'entrée | \`\${input.workspace_id}\` |
| \`\${step_X.field}\` | Champ du résultat de l'étape X | \`\${step_1.id}\` |
| \`\${step_X.path.to.value}\` | Champ imbriqué | \`\${step_1.data.items[0].name}\` |

### Extraction joker \`[*]\`

Extraire **toutes les valeurs** d'un tableau :

\`\`\`json
{
  "id": "2",
  "tool": "Grist__get_records",
  "parameters": {
    "doc_ids": "\${step_1.documents[*].id}"
  }
}
\`\`\`

Résultat : \`["doc1", "doc2", "doc3"]\` (liste aplatie)

**Jokers imbriqués** pour structures complexes :
\`\`\`
\${step_1.workspaces[*].docs[*].id}
\`\`\`
Extrait tous les IDs de documents de tous les espaces de travail (aplati automatiquement).

### Pattern Template/Map

Pour des transformations complexes avec contexte parent :

\`\`\`json
{
  "id": "3",
  "tool": "Notion__create_pages",
  "parameters": {
    "pages": {
      "_template": "\${step_1.workspaces[*].docs[*]}",
      "_map": {
        "doc_id": "\${_item.id}",
        "doc_title": "\${_item.title}",
        "workspace_id": "\${_parent.id}",
        "synced_at": "\${_now}"
      }
    }
  }
}
\`\`\`

**Variables disponibles dans \`_map\` :**

| Variable | Description |
|----------|-------------|
| \`\${_item}\` | Élément d'itération courant |
| \`\${_parent}\` | Objet parent (un niveau au-dessus) |
| \`\${_root}\` | Résultat original de l'étape |
| \`\${_index}\` | Index d'itération (0, 1, 2...) |
| \`\${_now}\` | Horodatage ISO |

## Exemple complet

\`\`\`json
{
  "name": "Sync Grist vers Notion",
  "description": "Synchroniser les tables Grist vers les pages Notion",
  "steps": [
    {
      "id": "1",
      "tool": "Grist__list_workspaces",
      "parameters": {}
    },
    {
      "id": "2",
      "tool": "Grist__list_docs",
      "parameters": {
        "workspace_id": "\${step_1.workspaces[0].id}"
      }
    },
    {
      "id": "3",
      "tool": "Notion__create_pages",
      "parameters": {
        "pages": {
          "_template": "\${step_2.docs[*]}",
          "_map": {
            "title": "\${_item.name}",
            "source_id": "\${_item.id}",
            "workspace": "\${step_1.workspaces[0].name}",
            "imported_at": "\${_now}"
          }
        }
      }
    }
  ],
  "input_schema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
\`\`\`

## Exécuter des compositions

### Via la passerelle MCP

Les compositions en production apparaissent comme des outils préfixés avec \`workflow_\` :

\`\`\`json
{
  "method": "tools/call",
  "params": {
    "name": "workflow_issue_triage",
    "arguments": {
      "issue_number": 123
    }
  }
}
\`\`\`

### Via l'API REST

\`\`\`bash
POST /api/v1/compositions/{composition_id}/execute
{
  "parameters": {
    "issue_number": 123
  }
}
\`\`\`

### Via l'endpoint Orchestrate

\`\`\`bash
POST /api/v1/orchestrate
{
  "query": "Trier l'issue #123",
  "execute": true
}
\`\`\`

BigMCP associera votre intention aux compositions existantes.

## Promouvoir des compositions

Pour passer une composition en production :

\`\`\`bash
POST /api/v1/compositions/{id}/promote
{
  "target_status": "production"
}
\`\`\`

Ou via l'interface : page Compositions → Sélectionner la composition → Promouvoir

## Ajouter aux Toolboxes

Les compositions en production peuvent être ajoutées aux Toolboxes :

1. Allez dans Toolboxes
2. Éditez votre groupe
3. Passez à l'onglet "Compositions"
4. Sélectionnez les compositions à inclure
5. Enregistrez

La composition apparaît alors comme un outil lors de l'accès à ce groupe via clé API.

## Monitoring

Consultez l'historique d'exécution des compositions :

- **Exécutions** : Nombre de succès/échecs
- **Durée** : Temps d'exécution moyen
- **Erreurs** : Échecs récents avec détails
- **Utilisation** : Quelles intégrations utilisent cette composition

## Bonnes pratiques

1. **Testez minutieusement** - Exécutez les compositions plusieurs fois avant de promouvoir
2. **Gérez les erreurs** - Considérez ce qui se passe si une étape échoue
3. **Noms descriptifs** - Le but doit être clair
4. **Documentez les paramètres** - Expliquez les entrées attendues
5. **Contrôle de version** - Notez les changements
6. **Surveillez la production** - Observez les échecs après promotion
`,

  'team-services': `
# Services d'équipe

Les Services d'équipe permettent aux administrateurs d'organisation de configurer des **serveurs MCP partagés** automatiquement disponibles pour tous les membres de l'équipe.

## Vue d'ensemble

Avec un **plan Team**, les administrateurs peuvent :
- Connecter des serveurs MCP au niveau de l'organisation
- Partager des identifiants de manière sécurisée entre tous les membres
- Assurer une disponibilité cohérente des outils pour toute l'équipe
- Gérer l'accès depuis un tableau de bord central

## Fonctionnement des Services d'équipe

\`\`\`
Administrateur de l'organisation
        │
        ▼
┌─────────────────────────────────────┐
│         Services d'équipe           │
│  ┌─────────┐ ┌─────────┐ ┌───────┐  │
│  │ GitHub  │ │  Slack  │ │ Jira  │  │
│  │ (org)   │ │  (org)  │ │ (org) │  │
│  └─────────┘ └─────────┘ └───────┘  │
└─────────────────────────────────────┘
        │
        ▼ (partagé automatiquement)
┌─────────────────────────────────────┐
│         Membres de l'équipe         │
│  👤 Alice  👤 Bob  👤 Charlie       │
│  (voit équipe + services perso)     │
└─────────────────────────────────────┘
\`\`\`

Les membres de l'équipe voient **les deux** :
- **Services d'équipe** : Gérés par l'administrateur
- **Services personnels** : Leurs propres serveurs connectés

## Configurer les Services d'équipe (Admin)

### 1. Accéder au panneau Admin

1. Connectez-vous en tant qu'administrateur de l'organisation
2. Allez dans **Paramètres** → **Organisation**
3. Sélectionnez l'onglet **Services d'équipe**

### 2. Connecter un serveur d'équipe

1. Cliquez sur **Ajouter un service d'équipe**
2. Parcourez le marketplace ou recherchez un serveur
3. Entrez les identifiants au niveau de l'organisation
4. Cliquez sur **Enregistrer**

Le serveur est maintenant disponible pour tous les membres de l'équipe.

### 3. Configurer la visibilité

Pour chaque service d'équipe, vous pouvez définir :

| Paramètre | Description |
|-----------|-------------|
| **Visible** | Les outils apparaissent dans la page Services des membres |
| **Masqué** | Disponible pour les compositions mais non affiché |
| **Désactivé** | Temporairement désactivé pour l'équipe |

## Expérience membre

Les membres de l'équipe voient les services d'équipe dans leur page **Services** avec un badge "Équipe". Ils peuvent :

- **Utiliser** tous les services d'équipe visibles
- **Créer des compositions** utilisant les services d'équipe
- **Masquer** les services d'équipe de leur vue personnelle

Les membres **ne peuvent pas** :
- Modifier les identifiants des services d'équipe
- Déconnecter les services d'équipe
- Changer les paramètres des services d'équipe

## Gestion des identifiants

### Identifiants d'organisation

Les identifiants des services d'équipe sont stockés au niveau de l'organisation :
- Chiffrés avec **AES-128** (Fernet)
- Accessibles uniquement aux admins pour édition
- Injectés automatiquement pour les membres de l'équipe

### Bonnes pratiques

1. **Utilisez des comptes de service** - Créez des comptes dédiés pour les services d'équipe
2. **Rotation régulière** - Mettez à jour les identifiants tous les 90 jours
3. **Documentez l'accès** - Notez quels identifiants ont un accès admin
4. **Auditez l'utilisation** - Vérifiez quels membres utilisent les services d'équipe

## Cas d'usage

### Équipe de développement

Connectez les outils de développement partagés :
- **GitHub** avec accès aux repos de l'organisation
- **Jira** pour le suivi de projet
- **Confluence** pour la documentation
- **SonarQube** pour la qualité du code

### Équipe succès client

Outils partagés orientés client :
- **Zendesk** pour les tickets de support
- **Salesforce** pour les données clients
- **Intercom** pour l'historique des conversations

### Équipe data

Infrastructure de données partagée :
- **PostgreSQL** base de production (lecture seule)
- **Metabase** pour les tableaux de bord
- **dbt** pour les transformations

## Différences : Services personnels vs équipe

| Aspect | Services personnels | Services d'équipe |
|--------|---------------------|-------------------|
| **Géré par** | Utilisateur individuel | Administrateur organisation |
| **Identifiants** | Propres à l'utilisateur | Niveau organisation |
| **Visibilité** | Utilisateur seul | Tous les membres de l'équipe |
| **Facturation** | Inclus dans le plan utilisateur | Inclus dans le plan Team |
| **Modifications** | Contrôle utilisateur | Contrôle admin |

## Prérequis de plan

| Fonctionnalité | Personnel | Team | Enterprise |
|----------------|----------|------|------------|
| Services personnels | ✅ | ✅ | ✅ |
| Services d'équipe | ❌ | ✅ | ✅ |
| Marketplace personnalisé | ❌ | ❌ | ✅ |

> **Note :** Les Services d'équipe nécessitent un plan **Team** ou **Enterprise**. [Mettez à jour votre plan](/pricing) pour activer cette fonctionnalité.
`,
}
