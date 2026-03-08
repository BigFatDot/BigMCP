/**
 * Documentation Concepts fondamentaux - Contenu en français
 */

export const conceptsContent: Record<string, string> = {
  'mcp-overview': `
# Protocole MCP

Le **Model Context Protocol (MCP)** est un standard ouvert développé par Anthropic qui permet aux assistants IA de se connecter de manière sécurisée à des outils et sources de données externes.

## Fonctionnement de MCP

\`\`\`mermaid
sequenceDiagram
    participant C as Claude (Client)
    participant S as Serveur MCP

    C->>S: Connexion via SSE
    S-->>C: Annonce des capacités
    C->>S: tools/list
    S-->>C: Outils disponibles
    C->>S: tools/call (exécuter)
    S-->>C: Résultat de l'outil

    Note over C,S: JSON-RPC 2.0 sur Server-Sent Events
\`\`\`

1. **Client** (Claude) se connecte à un serveur MCP
2. **Serveur** annonce les outils et ressources disponibles
3. **Client** demande l'exécution d'outils si nécessaire
4. **Serveur** exécute et retourne les résultats

## Composants du protocole

### Outils
Fonctions que l'IA peut exécuter. Chaque outil a :
- Un nom unique
- Un schéma d'entrée (JSON Schema)
- Une description pour l'IA

### Ressources
Données que l'IA peut lire et référencer :
- Fichiers et documents
- Enregistrements de base de données
- Réponses d'API

### Prompts
Templates prédéfinis :
- Prompts système
- Templates de messages utilisateur
- Initiateurs de conversations multi-tours

## Rôle de BigMCP

BigMCP agit comme une **passerelle** entre Claude et vos serveurs MCP :

\`\`\`mermaid
flowchart LR
    CLAUDE(["<b>Claude</b>"])

    subgraph gateway [" "]
        direction TB
        GW(["<b>Passerelle BigMCP</b>"])
        subgraph features [" "]
            direction LR
            F1(["Identifiants"])
            F2(["Contrôle d'accès"])
            F3(["Monitoring"])
        end
    end

    subgraph servers [" "]
        direction TB
        S1(["GitHub"])
        S2(["Slack"])
        S3(["Base de données"])
    end

    CLAUDE --> GW
    GW --> S1 & S2 & S3

    style gateway fill:none,stroke:#c4624a,stroke-width:2px
    style features fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style servers fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style CLAUDE fill:#ffffff,stroke:#d4d4d4,color:#262626
    style GW fill:#D97757,stroke:#c4624a,color:#ffffff
    style F1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style F2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style F3 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S3 fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

## En savoir plus

- [Documentation officielle MCP](https://modelcontextprotocol.io)
- [Spécification MCP](https://spec.modelcontextprotocol.io)
- [Dépôt GitHub MCP](https://github.com/modelcontextprotocol)
`,

  servers: `
# Serveurs MCP

Les serveurs MCP sont des programmes qui exposent des **outils** et des **ressources** aux assistants IA via le Model Context Protocol.

## Qu'est-ce qu'un serveur MCP ?

Un serveur MCP est un processus qui :
1. Écoute les connexions des clients MCP (comme Claude)
2. Annonce ses capacités (outils, ressources, prompts)
3. Exécute les demandes d'outils et retourne les résultats

## Types de serveurs

### Serveurs officiels
Maintenus par l'équipe MCP :
- \`@modelcontextprotocol/server-filesystem\` - Opérations sur fichiers
- \`@modelcontextprotocol/server-github\` - API GitHub
- \`@modelcontextprotocol/server-slack\` - Intégration Slack

### Serveurs communautaires
Créés par la communauté :
- Connecteurs de bases de données (PostgreSQL, MongoDB)
- APIs tierces (Notion, Airtable)
- Outils spécialisés (web scraping, traitement d'images)

## Cycle de vie des serveurs

### Installation
\`\`\`bash
# Serveurs npm
npx @modelcontextprotocol/server-filesystem

# Serveurs Python
uvx mcp-server-sqlite

# Serveurs Docker
docker run bigmcp/server-custom
\`\`\`

### Connexion
BigMCP gère le cycle de vie des serveurs :
1. Démarre le processus serveur
2. Établit la connexion MCP
3. Surveille l'état de santé
4. Redémarre en cas d'échec

### Identifiants
Beaucoup de serveurs nécessitent des identifiants :
- Clés API pour les services externes
- Tokens OAuth pour les données utilisateur
- Chemins pour les ressources locales

## Dans BigMCP

### Marketplace
Parcourez plus de 100 serveurs avec :
- Descriptions et capacités
- Identifiants requis
- Statut de vérification
- Scores de popularité

### Statut de connexion
- 🟢 **Connecté** - Serveur en cours d'exécution et en bonne santé
- 🔴 **Déconnecté** - Échec de connexion
- ⚪ **Inactif** - Désactivé manuellement

### Gestion des serveurs
Depuis la page **Services** :
- Voir les serveurs connectés et leurs outils
- Basculer la visibilité (afficher/masquer pour Claude)
- Démarrer, arrêter et redémarrer les serveurs
- Supprimer des serveurs
`,

  tools: `
# Outils

Les outils sont le principal moyen pour les serveurs MCP de fournir des fonctionnalités aux assistants IA.

## Qu'est-ce qu'un outil ?

Un outil est une fonction qui :
- A un **nom** unique au sein de son serveur
- Accepte une **entrée** structurée (JSON Schema)
- Retourne une **sortie** structurée
- Inclut une **description** pour l'IA

## Exemple d'outil

\`\`\`json
{
  "name": "read_file",
  "description": "Lire le contenu d'un fichier au chemin spécifié",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Chemin vers le fichier à lire"
      }
    },
    "required": ["path"]
  }
}
\`\`\`

## Visibilité des outils

Dans BigMCP, vous pouvez contrôler quels outils sont disponibles :

### Afficher/Masquer les outils
- Basculer la visibilité par outil
- Les outils masqués n'apparaissent pas dans le contexte de Claude
- Utile pour réduire le bruit

### Toolboxes
Regroupez les outils liés :
- Groupe "Développement" avec GitHub + Jira
- Groupe "Recherche" avec Search + Wikipedia
- Assignez des groupes aux clés API

## Exécution des outils

Quand Claude utilise un outil :

1. Claude génère une demande d'appel d'outil
2. BigMCP valide la demande
3. BigMCP transmet au serveur MCP
4. Le serveur exécute et retourne le résultat
5. BigMCP envoie le résultat à Claude

## Bonnes pratiques

### Pour les utilisateurs OAuth (Claude, Mistral)

Les connexions OAuth exposent **tous les services visibles** à l'assistant IA. Pour optimiser votre expérience :

1. **Utilisez les compositions** - Créez des outils personnalisés en chaînant plusieurs services. Cela vous permet d'exposer un seul outil adapté à vos besoins au lieu de nombreux outils bruts.

2. **Masquez les services, affichez les compositions** - Définissez les services sur "Masqué" dans la page Services. L'IA ne verra que vos compositions qui peuvent toujours utiliser les services masqués en arrière-plan.

3. **Restez focalisé** - Moins d'outils = meilleures performances de l'IA. N'activez que ce dont vous avez vraiment besoin.

### Pour les utilisateurs de clés API

Les clés API offrent plus de contrôle via les Toolboxes :

1. **Créez des Toolboxes** - Regroupez les outils liés pour des cas d'usage spécifiques
2. **Restreignez par clé API** - Chaque clé peut être limitée à des groupes spécifiques
3. **Séparez les préoccupations** - Différentes clés pour différents workflows
`,

  security: `
# Modèle de sécurité

BigMCP implémente un modèle de sécurité complet pour protéger vos identifiants et données.

## Types d'identifiants

| Type | Exemple | Cas d'usage |
|------|---------|-------------|
| Clé API | \`sk-abc123...\` | La plupart des APIs |
| Token OAuth | Access + Refresh | Données utilisateur |
| Auth basique | Nom d'utilisateur/Mot de passe | Systèmes legacy |
| Chemin | \`/home/user/docs\` | Fichiers locaux |
| Chaîne de connexion | \`postgres://...\` | Bases de données |

## Modèle de sécurité

### Chiffrement
Tous les identifiants sont chiffrés :
- Chiffrement AES-128 au repos (Fernet)
- TLS 1.3 en transit
- Clés de chiffrement par utilisateur

### Contrôle d'accès
- Les identifiants sont scopés par utilisateur
- Les identifiants d'équipe nécessitent un plan Team
- Pas de partage d'identifiants par défaut

### Piste d'audit
- Tous les accès sont journalisés
- Utilisation des identifiants suivie
- Alertes pour activité suspecte

## Gestion des identifiants

### Ajouter des identifiants
1. Connectez un serveur depuis le marketplace
2. Entrez les valeurs requises
3. Les identifiants sont chiffrés et stockés

### Mettre à jour les identifiants
Pour mettre à jour les identifiants d'un serveur :
1. Supprimez la connexion actuelle
2. Reconnectez depuis le Marketplace
3. Entrez les nouveaux identifiants

### Rotation des identifiants
La bonne pratique est de faire une rotation régulière :
1. Générez de nouveaux identifiants chez le fournisseur
2. Reconnectez le serveur dans BigMCP avec les nouveaux identifiants
3. Vérifiez que la connexion fonctionne
4. Révoquez les anciens identifiants chez le fournisseur

## Identifiants d'équipe

Avec un plan Team :
- Partagez les identifiants dans l'organisation
- Définissez des permissions par identifiant
- Gestion centralisée des identifiants

> **Note :** Les identifiants d'équipe ne sont disponibles que sur les plans Team et Enterprise.

## Authentification à deux facteurs (2FA)

Protégez votre compte avec une couche de sécurité supplémentaire grâce à l'authentification TOTP.

### Comment activer la 2FA

1. Allez dans **Paramètres → Compte**
2. Trouvez la section **Authentification à deux facteurs**
3. Cliquez sur **Activer 2FA**
4. Scannez le QR code avec votre application d'authentification (Google Authenticator, Authy, 1Password, etc.)
5. Sauvegardez les **codes de secours** en lieu sûr
6. Entrez un code de vérification pour confirmer

### Codes de secours

Quand vous activez la 2FA, vous recevez 10 codes de secours :
- Chaque code ne peut être utilisé qu'**une seule fois**
- Conservez-les dans un endroit sécurisé (gestionnaire de mots de passe, coffre-fort)
- Utilisez un code de secours si vous perdez l'accès à votre application d'authentification

### Connexion avec la 2FA

1. Entrez votre email et mot de passe
2. Quand demandé, entrez le code à 6 chiffres de votre application
3. Ou utilisez un code de secours si nécessaire

### Désactiver la 2FA

Pour désactiver la 2FA, allez dans **Paramètres → Compte** et cliquez sur **Désactiver 2FA**. Vous devrez entrer un code valide pour confirmer.

> **Conseil de sécurité :** Gardez la 2FA activée pour une protection maximale de votre compte. Si vous perdez votre appareil, utilisez un code de secours pour récupérer l'accès.
`,
}
