# BigMCP — Roadmap Access Control

> Document interne d'architecture. Plan séquentiel pour amener BigMCP à un niveau de contrôle d'accès déployable par toute organisation (Cerema-type comme exemple générique). État au 2026-05-13.

## Cadre stratégique

Le contrôle d'accès s'articule sur **5 dimensions indépendantes**, qui doivent toutes pouvoir être combinées dans des règles :

| Axe | Question | Levier |
|---|---|---|
| **Identité** | Qui est cet humain ou ce service ? | SSO, MFA, password local, API key |
| **Client** | Depuis quel logiciel agit-il ? | Claude Desktop, Cursor, scripts, agents custom |
| **Origine** | D'où arrive la requête sur le réseau ? | IP source, géographie |
| **Ressource** | À quoi tente-t-il d'accéder ? | MCP server, tool group, credential, composition |
| **Opération** | Que veut-il faire ? | Lire, exécuter, configurer, administrer |

### Principe de stratification monotone

```
Instance (DSI / admin instance)   — plancher dur, non-négociable
    ↓ peut être resserré, jamais relâché
Org / Team (chef d'équipe)         — politique locale
    ↓ peut être resserré, jamais relâché
Ressource (tool group, credential) — règles propres
    ↓
API key / OAuth client             — restrictions de la session
    ↓
User self-control                  — révocation de ses propres sessions
```

**Règle d'or** : chaque niveau ne peut que **restreindre** ce que le niveau supérieur autorise. Implémenté dans un `PolicyResolver` (Niveau 1).

## Audit factuel — état au 2026-05-13 (v2.2.0)

Score global : **2.3 / 5** — non-deployable Cerema sans niveau 0+1.

| Axe | Score | État |
|---|---|---|
| Identité fédérée (SAML/OIDC/SCIM) | 0/5 | Stubs enum, zéro implémentation |
| Lifecycle utilisateur | 3/5 | Invitations + JWT revoke OK ; pas de suspension, offboarding cross-surface manuel |
| Audit accessibilité | 1/5 | Table immuable HMAC OK ; aucune API de lecture, aucune UI, aucun audit des actions OAuth |
| Tool groups | 3/5 | Visibility PRIVATE/ORGANIZATION/PUBLIC ; pas de granularité par rôle |
| MCP servers | 2.5/5 | Ownership org-level ; pas de filtrage par rôle à l'exécution |
| Credentials | 4/5 | Séparation user/org + chiffrage + admin-only creation ; `CREDENTIAL_ACCESS` jamais émis |
| Compositions | 5/5 | RBAC `allowed_roles` enforce à l'exécution — référence à généraliser |
| Scopes API key | 2/5 | Définis mais jamais enforce — **faille active** |
| RBAC org | 2.5/5 | MEMBER/VIEWER strict ; OWNER/ADMIN indifférenciés en pratique |
| Stratification policy | 0/5 | Pas de PolicyResolver, instance et org sont des tracks séparés |

### Trois failles graves à fermer en priorité

1. **Scopes API key jamais enforce** : `require_scope` défini dans `dependencies.py:210` mais **aucun usage dans les routers**. Une API key avec scope `tools:read` peut exécuter. **Vulnérabilité active.**
2. **OAuth/auth jamais audités** : `oauth.py` et `auth.py` n'ont **aucun appel** à `AuditService.log_action()`. Login, register, consent, token grant, refresh — silence radio. Bloquant conformité RGPD/ISO27001.
3. **Aucune stratification instance→org** : l'instance admin (DSI) ne peut **pas** imposer de politique aux orgs (chefs d'équipe). Aucun PolicyResolver.

### Acquis solides

- `tokens_revoked_at` câblé sur JWT decode ([auth_service.py:376-384](mcp-registry/app/services/auth_service.py#L376-L384))
- AuditLog immuable HMAC SHA-256 + event listeners `before_update`/`before_delete` ([audit_log.py:174-269](mcp-registry/app/models/audit_log.py#L174-L269))
- `PermissionService.can_execute_composition` enforce `allowed_roles` ([permission_service.py:77-92](mcp-registry/app/services/permission_service.py#L77-L92)) — **pattern à généraliser**
- Modèle `Invitation` complet (token, expiration, acceptance/decline)
- `AuditService` existe et fonctionne — il suffit de l'appeler depuis `oauth.py` et `auth.py`

## Roadmap sequential — 4 niveaux

L'ordre est dicté par **dépendances structurelles**, pas préférences. Le client control N2 dépend du PolicyResolver N1. Le PolicyResolver dépend de l'audit observable. L'audit dépend des scopes enforce. D'où l'ordre.

### Niveau 0 — Fermer les failles (1-2 semaines)

**Tenants** : ne pas construire sur un système qui ignore ses propres événements et n'enforce pas ses propres permissions.

**Aboutissants** : l'instance est observable (audit) et sécurisée (scopes enforce).

**Chantiers** :
1. **Enforce scopes API key** sur ~30 endpoints sensibles, mode `log_only` d'abord (shadow then enforce)
2. **Audit OAuth + auth** : ~10 appels `AuditService.log_action()` dans `oauth.py` et `auth.py`
3. **Fix bug `primary_organization_id`** ([admin.py:323](mcp-registry/app/api/v1/admin.py#L323))

**Critère de sortie** : tests `pytest -k scope` passent ; entrées `auth.login_success`, `oauth.token_grant` apparaissent dans l'audit log.

### Niveau 1 — Fondations Cerema (1-2 mois)

**Tenants** : sans gouvernance instance→org, le DSI n'a aucun levier. Sans audit observable, l'instance est aveugle.

**Aboutissants** : l'instance est gouvernable. Seuil de viabilité Cerema atteint.

**Chantiers** :
1. **PolicyResolver + InstanceSettings** : nouvelle table singleton JSON `instance_settings` + defaults env vars (`DEFAULT_DCR_POLICY`, `GLOBAL_TRUSTED_CIMD_URLS`, etc.). Composition monotone décroissante (org ⊆ instance).
2. **API audit + UI navigable** : endpoints `/api/v1/admin/audit-logs` + page React `AuditLogsPage.tsx` avec filtres (user, org, action, période, IP, client), pagination, export CSV. **Préalable** : créer `frontend/src/services/api.ts` (axios instance + interceptor JWT).
3. **Kill switch offboarding cross-surface** : étendre `tokens_revoked_at` aux RefreshToken + API keys + OAuth grants. Endpoint `POST /admin/users/{id}/revoke-all`. Uniformiser APIKey sur le pattern `RefreshToken.revoke()` (ajouter `revoked_at`, `revoked_reason`).
4. **Suspension non-destructive** : champ `status` enum (active / suspended / deleted) + `status_changed_at` + `deleted_at` (soft-delete RGPD). Endpoints suspend / reactivate / soft-delete.

**Critère de sortie** : test e2e « DSI active require_cimd au niveau instance → chef d'équipe ne peut plus créer un OAuthClient sans CIMD ». UI audit affiche les 1000 dernières entrées avec filtres. Offboarding < 1 sec.

### Niveau 2 — Capacités Enterprise (3-4 mois)

**Tenants** : SSO = barrière #1 d'adoption Enterprise. Client control = différenciation produit. Granularité ressources = sécurité réelle.

**Aboutissants** : Cerema-ready en production.

**Chantiers** :
1. **SAML 2.0 + OIDC** via Authlib (à ajouter en dépendance). Refactor `auth.py` pour dispatcher par `AuthProvider`. Endpoints `/auth/saml/sso/{idp}` et `/auth/oidc/{provider}`. JIT user+org provisioning. Estimation : 6-8 semaines.
2. **Client control** (plan détaillé v3) : migration `OAuthClient` (organization_id, approval_status, registration_method, cimd_*) + endpoints admin/org/user + service CIMD (SEP-991) + extension consent screen Jinja2.
3. **MCP server `allowed_roles`** : généraliser le pattern Composition. Convention : empty = all except viewer ; `["admin"]` = ADMIN+OWNER seulement.
4. **Audit `CREDENTIAL_ACCESS`** : émettre à chaque déchiffrement de credential.

**Critère de sortie** : agent se logue via SSO ADFS → atterrit dans BigMCP avec rôle hérité. Tentative DCR sans CIMD depuis domaine non-whitelisté refusée. MCP server `allowed_roles=["admin"]` invisible aux MEMBER.

### Niveau 3 — Industrialisation (4-6 mois cumulés)

- SCIM 2.0 provisioning auto depuis AD
- OWNER vs ADMIN différenciés (transfert ownership, suppression org)
- Permissions granulaires au-delà des 4 rôles si retour terrain
- Délégation temporaire

## Décisions techniques arbitrées

| # | Décision | Optimum | Justification |
|---|---|---|---|
| 1 | Mode scopes API key | log_only puis enforce | Shadow-then-enforce standard, zéro régression silencieuse |
| 2 | Bootstrap admin Enterprise | Auto-promote (Community) + script CLI `scripts/promote_admin.py` (Enterprise) | Quickstart conservé, déploiement contrôlé possible |
| 3 | Stockage policy instance | Mix env vars defaults + table singleton override | Bootstrap sécurisé + surcharge à chaud (pattern Kubernetes values) |
| 4 | Champ lifecycle user | `status` enum + `status_changed_at` + `deleted_at` | RGPD soft-delete complet |
| 5 | Kill switch | Combiné `tokens_revoked_at` étendu + endpoint admin + uniformiser APIKey sur pattern RefreshToken | Sécurité immédiate + traçabilité complète |
| 6 | Audit UI | API REST + page React + `services/api.ts` partagé (dette payée) | Couvre SIEM-ready et UX DSI |
| 7 | SSO | SAML + OIDC via Authlib | Marché fragmenté ; Authlib couvre les deux |
| 8 | Client control | Avec CIMD (SEP-991) | Alignement spec MCP 2025-11-25, différenciateur |
| 9 | MCP server allowed_roles | `allowed_roles` seul (comme Composition) | Cohérence sequential ; `allowed_user_ids` en N3 sur les deux modèles |
| A | Création orgs | Auto-service par défaut + endpoint admin top-down | Couvre PME agiles et structures corporate |
| B | Signup utilisateur | Configurable par env (`SIGNUP_MODE=open\|whitelist_domain\|invitation_only`) | Une variable, trois modes |
| C | SSO coexistence | Configurable (`SSO_REQUIRED_FOR_NEW_USERS`) | Évite lock-out des users existants |
| D | Communication | Roadmap N2/N3 publique post-N0 ; N0/N1 traités en interne | Transparence sans inviter exploitation |
| E | Versionning | v2.3.0 (N0+N1), v3.0.0 (N2) | SemVer strict |
| F | Pilote | Démarcher fin N1 avec démo gouvernance fonctionnelle | Crédibilité + validation produit |

## Zones grises à vérifier en cours d'implémentation

- **Migrations historiques** `oauth_clients` et `api_keys` : pas trouvées dans les 5 dernières. Vérifier `alembic history` avant la 1re migration N1 ; créer migration de réconciliation si divergence schema vs ORM.
- **Estimation SSO 6-8 semaines** : à valider par POC court (1 semaine OIDC vers Keycloak local) avant engagement complet.
- **Bug `primary_organization_id`** ([admin.py:323](mcp-registry/app/api/v1/admin.py#L323)) : élargir le grep pour tracer toutes les utilisations avant fix.
- **Licence AGPLv3** : clarifier les contraintes éventuelles avant publication de roadmap publique (#D).

## Critères transverses — produit générique conforme

Toutes les recommandations suivent 5 principes :

1. **Defaults sécurisés** : à l'install, l'instance est restrictive ; l'admin doit explicitement ouvrir
2. **Configurabilité** : tout ce qui dépend de la culture org est paramétrable (signup, SSO, IdP, policy)
3. **Conformité par construction** : RGPD (soft-delete), ISO27001 (audit complet), spec MCP (CIMD)
4. **Standards industriels** : SemVer, SAML+OIDC, CLI bootstrap, shadow-then-enforce
5. **Defense in depth** : sécurité immédiate **et** traçabilité **et** stratification — pas l'un ou l'autre

C'est ce qui rend BigMCP déployable chez n'importe quelle organisation sans modification de code.
