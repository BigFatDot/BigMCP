/**
 * Documentation Premiers Pas - Contenu en français
 */

export const gettingStartedContent: Record<string, string> = {
  introduction: `
# Introduction

BigMCP est une **plateforme centralisée de gestion MCP** qui connecte vos assistants IA (Claude, Mistral Le Chat, etc.) et vos outils d'automatisation (n8n, Make) à un écosystème unifié de services et d'outils.

## Comment ça marche

\`\`\`mermaid
flowchart TB
    subgraph top [" "]
        direction LR
        CLAUDE(["<b>Claude</b><br/>Desktop & Mobile"])
        MISTRAL(["<b>Mistral</b><br/>Le Chat"])
        N8N(["<b>n8n</b><br/>Automation"])
    end

    GATEWAY(["<b>BigMCP</b><br/>━━━━━━━━━━━━━<br/>Passerelle MCP unifiée<br/>OAuth 2.0 · Clés API"])

    subgraph bottom [" "]
        direction LR
        S1(["GitHub"])
        S2(["Slack"])
        S3(["Drive"])
        S4(["100+ autres..."])
    end

    CLAUDE & MISTRAL & N8N --> GATEWAY
    GATEWAY --> S1 & S2 & S3 & S4

    style top fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style bottom fill:none,stroke:#e5e5e5,stroke-dasharray:5
    style CLAUDE fill:#ffffff,stroke:#d4d4d4,color:#262626
    style MISTRAL fill:#ffffff,stroke:#d4d4d4,color:#262626
    style N8N fill:#ffffff,stroke:#d4d4d4,color:#262626
    style GATEWAY fill:#D97757,stroke:#c4624a,color:#ffffff
    style S1 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S2 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S3 fill:#f4e4df,stroke:#c4624a,color:#262626
    style S4 fill:#f4e4df,stroke:#c4624a,color:#262626
\`\`\`

**BigMCP agit comme un hub central** : vos assistants IA et outils d'automatisation se connectent à BigMCP, qui gère ensuite les connexions vers tous vos services (GitHub, Slack, bases de données, etc.).

## Qu'est-ce que MCP ?

Le [Model Context Protocol (MCP)](https://modelcontextprotocol.io) est un standard ouvert qui permet aux assistants IA d'accéder de manière sécurisée à des outils et sources de données externes :

- **Outils** - Fonctions exécutables par l'IA (lire des fichiers, interroger des bases de données, envoyer des messages)
- **Ressources** - Données accessibles (documents, APIs, bases de connaissances)
- **Prompts** - Modèles prédéfinis pour les tâches courantes

## Pourquoi BigMCP ?

| Problème | Solution BigMCP |
|----------|-----------------|
| Configuration complexe | Connexion OAuth en un clic, pas de fichiers de config |
| Gestion des identifiants | Coffre-fort chiffré AES-128 (Fernet), partage sécurisé |
| Contrôle d'accès | Toolboxes pour restreindre par contexte |
| Support multi-clients | Un seul compte pour Claude, Mistral, n8n... |
| Shadow AI en entreprise | Piste d'audit, identifiants centralisés, gouvernance |

## Méthodes de connexion

### OAuth 2.0 + PKCE (Recommandé)
La méthode la plus simple pour les assistants IA compatibles :
- **Pas de configuration de fichiers** - Connectez-vous directement depuis Claude ou Mistral
- **Sécurisé** - Authentification standard avec tokens révocables
- **Expérience fluide** - Connectez-vous une fois, accès immédiat à tous vos outils

### Clé API
Pour les cas d'usage avancés :
- **Automatisation** - Scripts, CI/CD, workflows n8n
- **Restriction par Toolbox** - Limitez l'accès à un sous-ensemble d'outils
- **Longue durée** - Tokens non-expirables pour les intégrations permanentes

### API REST
Pour les intégrations programmatiques :
- **n8n, Make, Zapier** - Utilisez vos outils BigMCP dans des workflows
- **Applications personnalisées** - Créez vos propres intégrations
- **Traitement par lots** - Exécutez des outils en masse

## Toolboxes : Contrôle et Contexte

Les Toolboxes sont au cœur de BigMCP, avec deux objectifs :

### 1. Contrôle d'accès
Restreignez les outils accessibles par clé API :
- Créez un groupe "Production" avec uniquement les outils validés
- Générez une clé API liée à ce groupe
- La clé API ne peut accéder qu'aux outils de ce groupe

### 2. Contexte pour les agents IA
Organisez vos outils par cas d'usage :
- **"Outils Dev"** : GitHub, GitLab, Jira, CI/CD
- **"Communication"** : Slack, Email, Discord
- **"Analyse de données"** : PostgreSQL, BigQuery, Sheets

Vos agents IA ne voient que les outils pertinents pour leur contexte.

## Cas d'usage

### Personnel
- Connectez Claude Desktop à tous vos services depuis une interface unique
- Gérez vos clés API et identifiants en un seul endroit
- Créez des compositions d'outils pour automatiser des tâches complexes

### Équipe
- Partagez des identifiants sécurisés entre membres (Services d'équipe)
- Définissez des rôles et permissions (RBAC)
- Standardisez les configurations d'outils dans votre organisation

### Entreprise
- **Gouvernance Shadow AI** : Centralisez l'accès IA aux données sensibles
- **Piste d'audit** : Tracez chaque utilisation d'outil
- **Marketplace privé** : Ajoutez vos propres serveurs MCP
- **Identifiants centralisés** : Plus de secrets dans les configs individuelles

## Prochaines étapes

Prêt à commencer ? Continuez vers le [Démarrage rapide](/docs/getting-started/quickstart) pour configurer votre compte en 5 minutes.
`,

  quickstart: `
# Démarrage rapide

Soyez opérationnel avec BigMCP en 5 minutes.

## Étape 1 : Créer un compte

1. Visitez [bigmcp.cloud](https://bigmcp.cloud)
2. Cliquez sur **Démarrer l'essai gratuit**
3. Entrez votre email et créez un mot de passe
4. Vérifiez votre adresse email (consultez votre boîte de réception)

> **Note :** Tous les nouveaux comptes incluent un essai gratuit de 15 jours avec accès complet à toutes les fonctionnalités.

## Étape 2 : Explorer le Marketplace

Une fois connecté, vous arriverez sur le **Marketplace**. Ici vous pouvez :

- Parcourir les serveurs par catégorie
- Rechercher des outils spécifiques
- Voir les détails des serveurs et les identifiants requis

## Étape 3 : Connecter votre premier serveur

Connectons le serveur **Fetch** comme exemple (aucun identifiant requis) :

1. Trouvez "Fetch" dans le marketplace
2. Cliquez sur **Connecter**
3. Cliquez sur **Enregistrer** (pas d'identifiants nécessaires pour ce serveur)

Le serveur Fetch fournit un seul outil pour récupérer du contenu web - parfait pour tester !

> **Astuce :** Pour les serveurs nécessitant des identifiants (comme GitHub), vous devrez fournir une clé API ou un token.

## Étape 4 : Voir vos services

Naviguez vers **Services** pour voir :

- Vos serveurs connectés
- Les outils disponibles de chaque serveur
- Le statut de connexion (vert = connecté)

## Étape 5 : Connecter un client IA

BigMCP fonctionne avec tout client compatible MCP. Le plus simple pour commencer :

1. Ouvrez votre client IA (Claude Desktop, Mistral Le Chat, Cursor, etc.)
2. Allez dans les paramètres MCP / connecteurs
3. Ajoutez un nouveau serveur MCP avec l'URL de votre instance :

\`\`\`
https://bigmcp.cloud
\`\`\`

4. Connectez-vous avec vos **identifiants BigMCP** (email et mot de passe)
5. Vos outils apparaissent automatiquement dans le client

> Pour les clients qui ne supportent pas la connexion par URL, consultez la section [Intégrations](/docs/integrations/claude-desktop) pour la configuration manuelle via clé API.

## Et ensuite ?

- [Connectez plus de serveurs](/docs/getting-started/first-server) depuis le marketplace
- [Apprenez-en plus sur les outils](/docs/concepts/tools) et leur fonctionnement
- [Créez des groupes d'outils](/docs/guides/tool-groups) pour organiser votre configuration
`,

  'first-server': `
# Connecter votre premier serveur

Ce guide vous accompagne dans la connexion d'un serveur MCP à BigMCP.

## Prérequis

- Un compte BigMCP ([inscrivez-vous ici](/signup))
- Les identifiants pour le serveur que vous souhaitez connecter (clés API, tokens, etc.)

## Trouver des serveurs

### Parcourir par catégorie

Le marketplace organise les serveurs en catégories :

- **Données & Bases de données** - PostgreSQL, MongoDB, Airtable
- **Documents & Fichiers** - Filesystem, Google Drive, Dropbox
- **Communication** - Slack, Discord, Email
- **Développement** - GitHub, GitLab, Jira
- **Recherche & Connaissances** - Brave Search, Wikipedia
- **IA & ML** - OpenAI, Hugging Face

### Recherche

Utilisez la barre de recherche pour trouver des serveurs spécifiques par nom ou fonctionnalité.

## Connecter un serveur

### Étape 1 : Sélectionner le serveur

Cliquez sur n'importe quelle carte de serveur pour voir ses détails :

- Description et capacités
- Identifiants requis
- Outils disponibles
- Source et statut de vérification

### Étape 2 : Entrer les identifiants

Chaque serveur requiert différents identifiants. Types courants :

| Type | Exemple |
|------|---------|
| Clé API | \`sk-abc123...\` |
| OAuth | Connexion avec Google/GitHub |
| Token | Token d'accès personnel |
| Chemin | Chemin de répertoire sur votre système |

### Étape 3 : Enregistrer et vérifier

Cliquez sur **Enregistrer les identifiants** pour :

1. Chiffrer et stocker vos identifiants
2. Vérifier que la connexion fonctionne
3. Récupérer les outils disponibles

> **Sécurité :** Tous les identifiants sont chiffrés avec AES-128 (Fernet) avant stockage.

## Gérer les connexions

### Voir le statut

Dans la page **Services**, chaque serveur affiche :

- 🟢 Connecté - Le serveur est actif et fonctionne
- 🔴 Déconnecté - Problème de connexion (vérifiez les identifiants)
- ⚪ Inactif - Serveur désactivé manuellement

### Mettre à jour les identifiants

1. Cliquez sur le serveur dans **Services**
2. Cliquez sur l'icône de modification
3. Mettez à jour les identifiants
4. Enregistrez les modifications

### Supprimer un serveur

1. Cliquez sur le serveur dans **Services**
2. Cliquez sur l'icône de corbeille
3. Confirmez la suppression

> **Note :** Supprimer un serveur efface ses identifiants mais n'affecte pas le serveur lui-même.

## Dépannage

### "Échec de connexion"

- Vérifiez que vos identifiants sont corrects
- Vérifiez si le service externe est disponible
- Essayez de vous déconnecter et reconnecter

### "Identifiants invalides"

- Régénérez votre clé API depuis le fournisseur
- Vérifiez les dates d'expiration
- Assurez-vous d'avoir les permissions requises

## Prochaines étapes

- Apprenez-en plus sur les [Serveurs MCP](/docs/concepts/servers)
- Organisez les serveurs avec les [Toolboxes](/docs/guides/tool-groups)
- Configurez les [Clés API](/docs/guides/api-keys) pour l'accès externe
`,
}
