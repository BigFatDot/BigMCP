# AUDIT_AND_PLAN — Sprint 3

Date: 2026-06-13 — toutes les références de lignes sont des extraits réels, pas des estimations.
Règle cardinale tenue : **vérifier l'existant, jamais dupliquer, étendre/corriger avant de créer**.

---

## Phase 1 — Inventaire de l'existant

| Fichier | Responsabilité | Verdict | Raison |
|---|---|---|---|
| `frontend/src/pages/auth/LoginPage.tsx` (L91–99) | Capture l'erreur de `login()` via `err instanceof Error ? err.message` | **refactor mineur** | Le message vient déjà du throw côté `AuthContext.login`, mais le `detail` array (Pydantic 422) est stringifié `[object Object]` parce que `AuthContext.login` fait `throw new Error(data.detail \|\| HTTP X)` sans aplatir l'array |
| `frontend/src/pages/auth/SignupPage.tsx` (L67–79) | Idem (capture + display) | **refactor mineur** | Même bug exact que `LoginPage` — pas de parser pour l'array Pydantic |
| `frontend/src/contexts/AuthContext.tsx` (L242–356) | `login()` / `signup()` font des `fetch` directs et `throw new Error(data.detail \|\| 'HTTP X')` | **étendre** | C'est ici qu'il faut appeler le helper `extractApiError` (qui existe déjà — voir ci-dessous) au lieu de `data.detail` brut |
| `frontend/src/services/marketplace.ts` (L305–322) | **`extractApiError(error, fallback)` EXISTE DÉJÀ et gère explicitement l'array Pydantic 422 (`d.msg`)** | **réutiliser tel quel** | Pas besoin d'inventer un nouveau parser. À déplacer vers `services/api.ts` ou `lib/` pour le rendre indépendant de marketplace, mais la logique est bonne |
| `frontend/src/services/api.ts` (L20–51) | apiClient axios partagé, pas de helper exporté | **étendre** | Ré-exporter `extractApiError` depuis ici pour qu'il soit l'API publique d'erreur de tout `services/*` |
| `frontend/src/pages/settings/TeamPage.tsx` (L187–222) | **switch-organization déjà appelé** via `fetch(/auth/switch-organization?organization_id=…)` puis `localStorage.setItem` + `window.location.reload()` | **extraire** | Toute la logique de switch existe — il faut la sortir de TeamPage pour la rendre réutilisable depuis le Navbar |
| `frontend/src/hooks/useAuth.ts` (`useOrganization`, L88–111) | Expose `organization`, `organizationName`, `organizationId`, `isAdmin`. Pas de `memberships`, pas de `switchTo()` | **étendre** | Ajouter `memberships` (déjà dans `user.organization_memberships`) et exposer un `switchOrganization(id)` qui factorise le pattern TeamPage |
| `mcp-registry/app/api/v1/auth.py` (L46–239 `register`) | **Crée DÉJÀ l'org perso + membership ADMIN inline** dans le handler | **réutiliser tel quel** | Le finding #3 ne vient PAS de signup normal — sont concernés les users HÉRITÉS (avant cette logique) ou les users SSO/OIDC |
| `mcp-registry/app/services/oidc_service.py` (L452, L521) | SSO crée AUSSI une org perso + membership pour les nouveaux users SSO | **réutiliser tel quel** | Couvert |
| `mcp-registry/app/api/v1/auth.py` (`/auth/login` L348–361) | Si pas de membership → 500 "User has no organization" | **étendre** | Self-heal : si user actif sans org → créer une org perso à la volée (idempotent) au lieu de 500. C'est le vrai fix de #3 |
| `mcp-registry/app/api/v1/auth.py` (`/auth/switch-organization` L770–850) | Endpoint fonctionnel, contrat `POST?organization_id=…` (query param, pas body) | **réutiliser tel quel** | Le pattern TeamPage utilise déjà le bon contrat |
| `mcp-registry/app/api/v1/auth.py` (`/auth/organizations` L853–884) | Liste les orgs de l'utilisateur courant | **réutiliser tel quel** | Suffisant pour alimenter le switcher |
| `frontend/src/components/layout/Navbar.tsx` (L94–286) | Dropdown user-menu — **pas de zone "Organisation actuelle"**, juste un lien `Organization` qui mène à TeamPage | **étendre** | Ajouter une zone OrgSwitcher (pill ou sous-menu) avant le menu déroulant ou en encart du dropdown — pas de nouveau Navbar |
| `frontend/src/components/compositions/builder/StepTypePicker.tsx` (L59–63) | onClick fait **DÉJÀ** `onPick(stepType) ; onClose()` | **vérifier finding** | Le picker DEVRAIT se fermer. Source du #7 = soit `pickerOpen` est re-mis à `true` par un effect, soit le Modal interne ignore `onClose`. À vérifier au runtime, mais correctif probable : déplacer la fermeture côté parent (`onPick` → `setPickerOpen(false)`) dans `CompositionBuilder.tsx` (L394–399) |
| `frontend/src/components/compositions/builder/CompositionBuilder.tsx` (L394–399) | `<StepTypePicker isOpen={pickerOpen} onClose={() => setPickerOpen(false)} onPick={(t) => dispatch({ type: 'ADD_STEP', stepType: t })} />` | **modifier 1 ligne** | `onPick` doit déclencher AUSSI `setPickerOpen(false)` ; aujourd'hui c'est le picker qui gère, mais visiblement le state du parent reste `true` (peut-être à cause d'un re-render trop tôt) |
| `frontend/src/components/compositions/builder/forms/WaitUntilStepForm.tsx` (L125–151) | Input `type="number" min={1}` — **pas de `max` du tout** | **modifier 1 ligne** | Ajouter `max={86400}` (cohérent avec ElicitStepForm L60 et ApprovalStepForm L107). Le finding `valuemax=0` est probablement une lecture chrome-devtools d'un attribut absent rapporté comme 0 |
| `frontend/src/components/ui/Input.tsx` | Composant générique passe `min/max` au DOM input | **réutiliser tel quel** | Pas de bug dans Input |
| `frontend/public/locales/en/dashboard.json` (L354) | `"steps": "{{count}} steps"` (pas de `_one`) | **corriger 1 clé** | Renommer en `"steps_one": "{{count}} step"` + `"steps_other": "{{count}} steps"`. Idem L365 `parameters`, L404 `executingSteps` |
| `frontend/public/locales/en/dashboard.json` (L394–397) | Empty state compositions : mentionne UNIQUEMENT "Use the AI assistant" | **corriger 1 clé** | Réécrire pour mentionner aussi le builder visuel ("…or build a workflow visually from a step type") |
| `frontend/public/locales/en/compositions.json` (L19–24) | Utilise déjà `count` + `count_other` (pattern correct i18next v21) | **réutiliser tel quel** | Sert de référence pour fixer dashboard.json |
| `frontend/public/locales/fr/dashboard.json` (L354) | `"steps": "{{count}} étapes"` (même pattern cassé) | **corriger** | Idem |
| `frontend/public/locales/fr/compositions.json` (L21–22) | Utilise `count` + `count_other` correctement | **réutiliser tel quel** | OK |
| `frontend/src/pages/compositions/CompositionsPage.tsx` (L192, L205, L1239–1244) | Appelle `t('compositions.steps', { count })`, `t('compositions.empty.description')` | **réutiliser tel quel** | Côté code rien à faire — fix dans le locale fichier |
| `frontend/src/pages/compositions/CompositionsPage.tsx` (L1194–1226) | Combobox filter `<select>` avec `title=` (lu comme accessible name par défaut) | **étendre** | Ajouter un `<label>` masqué (sr-only) ou `aria-labelledby` pointant un span associé, et garder `title` comme helper distinct |
| `frontend/src/components/compositions/builder/forms/SubcompositionStepForm.tsx` (L78–81) | `useQuery` sans `refetchInterval` ni `refetchOnWindowFocus` | **étendre** | Ajouter `refetchOnWindowFocus: true` + `staleTime: 30_000`. Le commentaire L29–31 le mentionne explicitement comme "out of scope" — Sprint 3 le rend in-scope |
| `frontend/src/components/onboarding/OnboardingWizard.tsx` (L62–650) | Importe `useTranslation('common')` mais **0 appel à `t(…)`** — tout est EN hardcodé | **étendre** | Extraire toutes les strings vers `locales/{en,fr}/common.json` sous `onboarding.*` |
| `frontend/src/pages/auth/SignupPage.tsx` (L46–49) | Validation password = `length < 8` seulement | **étendre** | Ajouter une jauge de force visible. Pas de lib `zxcvbn` ni de helper `passwordStrength` dans le repo (vérifié grep — 0 résultat) → **créer** un helper `passwordStrength.ts` (heuristique custom 10 lignes, pas de lib externe) + un composant léger `<PasswordStrengthMeter>` |
| `frontend/src/services/auth*` ou `lib/auth*` | **N'existe pas** | **créer** | Pas de service auth dédié — toute l'auth vit dans `AuthContext`. Pour Sprint 3 on garde ce pattern, on ne refactor pas |
| `frontend/src/components/auth/SsoButtons.tsx` | Boutons SSO existants déjà sur LoginPage | **réutiliser tel quel** | OK |

### Bilan Phase 1

5 trésors trouvés (à RÉUTILISER) :
1. `extractApiError(error, fallback)` dans `marketplace.ts:311` — gère l'array Pydantic 422.
2. `/auth/register` backend crée DÉJÀ l'org perso (L117–133 auth.py).
3. `/auth/switch-organization` + `/auth/organizations` backend complets et fonctionnels.
4. Pattern switch dans `TeamPage.tsx:187–222` (POST + setItem + reload) prêt à factoriser.
5. `oidc_service.py:452,521` couvre déjà le cas SSO → org auto.

3 vrais trous :
- Pas d'OrgSwitcher dans le Navbar (et `useOrganization` n'expose ni `memberships` ni `switchTo`).
- Pas de helper `passwordStrength` ni `<PasswordStrengthMeter>` côté frontend.
- OnboardingWizard 100% EN hardcodé malgré `useTranslation('common')`.

---

## Phase 2 — Mapping besoin → existant

| # | Besoin | Existant (fichier:lignes) | Verdict | Plan concret |
|---|---|---|---|---|
| **#1** | Erreur login affichée correctement (pas `[object Object]`) | `extractApiError` dans `services/marketplace.ts:311–322` | **réutiliser** | Promouvoir `extractApiError` vers `services/api.ts` (export public) + faire que `AuthContext.login/signup` (L264, L331) appelle `extractApiError(data, fallback)` à la place de `data.detail \|\| 'HTTP X'` |
| **#2** | Parser Pydantic 422 array | `extractApiError` couvre déjà `Array.isArray(detail)` L316–319 | **réutiliser** | Identique au #1, c'est le même fix |
| **#3** | User créé sans org → 500 "User has no organization" | `register` crée bien l'org (auth.py:117–133), `oidc_service` aussi. Le bug ne touche que les users hérités | **étendre** | 2 actions :<br>1. **Backend** : dans `/auth/login` (auth.py:357–361) remplacer le `500` par un self-heal qui crée une org perso à la volée (idempotent via `select … for update`).<br>2. **Migration Alembic** ponctuelle pour réparer les comptes orphelins existants (1 revision read-only data migration) |
| **#4** | OrgSwitcher visible + indicateur de l'org courante | Backend prêt, `TeamPage` a la logique de switch, `useOrganization` partiel | **extraire + créer 1 composant** | Étapes :<br>1. Étendre `useOrganization` (hooks/useAuth.ts:88) → expose `memberships`, `switchOrganization(id)` qui factorise le pattern TeamPage.<br>2. Créer **1 seul nouveau fichier** `components/layout/OrgSwitcher.tsx` (pill avec org-name + dropdown).<br>3. Monter dans `Navbar.tsx:94` à gauche du user-menu (entre les nav-links et le user-menu).<br>4. Refactor TeamPage pour utiliser le même `switchOrganization` du hook (pas de duplication) |
| **#5** | Combobox filter accessible (pas `aria-label` = verbose) | Combobox = 3× `<select>` dans CompositionsPage L1194–1226 avec juste `title=` | **étendre** | Ajouter un `<label class="sr-only">` au-dessus de chaque select + `id` matching. Conserver `title` comme tooltip explicatif distinct |
| **#6** | Empty state Compositions mentionne le builder visuel | `dashboard.json:396` mentionne uniquement "AI assistant" | **corriger 1 string locale** | Réécrire `compositions.empty.description` en EN+FR pour ajouter "…or click *Add a step* to build one visually". 0 changement de code. |
| **#7** | StepTypePicker se ferme auto après sélection | `StepTypePicker.tsx:62` fait DÉJÀ `onClose()` après `onPick` | **modifier 1 ligne dans le parent** | Dans `CompositionBuilder.tsx:397` faire `onPick={(t) => { dispatch({ type: 'ADD_STEP', stepType: t }); setPickerOpen(false); }}`. La double fermeture est sans risque (idempotent) et garantit que même si le Modal interne perd `onClose` à cause d'un re-render, le state du parent passe à `false`. |
| **#8** | `valuemax` cohérent sur wait_seconds | `WaitUntilStepForm.tsx:127` a `min={1}` mais pas de `max` | **modifier 1 ligne** | Ajouter `max={86400}` (24h, cohérent avec elicit/approval TTLs). 1 ligne. |
| **#9** | "1 steps" — pluralization | `dashboard.json:354` `"steps": "{{count}} steps"` sans variante singulière | **corriger 3 clés locale** | Renommer en `"steps_one"` / `"steps_other"` (idem `parameters` L365 et `executingSteps` L404) dans EN+FR. i18next v21+ gère nativement. 0 changement de code (CompositionsPage utilise déjà `t('…steps', { count })`). |
| **#10** | Auto-refresh sub-compositions promotion | `SubcompositionStepForm.tsx:78–81` `useQuery` sans refetch dynamique | **étendre 2 lignes** | Ajouter `refetchOnWindowFocus: true` + `staleTime: 30_000`. Couvre le cas "autre tab promote → on revient ici". Pas besoin de WebSocket. |
| **Multi-tenant** | OrgSwitcher (= #4) | Voir #4 | — | (regroupé avec #4 — sous-sprint 3.B) |
| **Signup demo** | Lever le blocage "verify email" pour la démo SaaS | `register` SaaS renvoie 202 + `requires_verification` (auth.py:194–210) | **décision UX** | Option A (magic-link auto-login après verify : déjà l'état actuel — l'utilisateur clique le lien dans son inbox). Option B (preview mode : routes lecture-seule sans auth). Voir Phase 4 — décision pendante. **Sans validation user, on ne touche pas.** |
| **OnboardingWizard i18n** | Toutes les strings | `OnboardingWizard.tsx:62` importe `useTranslation('common')` mais ~50 strings hardcodées | **étendre** | Extraire vers `locales/{en,fr}/common.json` sous le préfixe `onboarding.*`. Pattern existant (cf. `nav.*`, `menu.*`). |
| **Password meter** | Jauge visuelle force password sur signup | Rien (grep `zxcvbn` + `passwordStrength` = 0 résultat) | **créer** | 2 fichiers minimaux : `utils/passwordStrength.ts` (heuristique 10 lignes : longueur, classes char) + `components/auth/PasswordStrengthMeter.tsx` (barre visuelle + label). Monté dans `SignupPage.tsx` sous l'input password (~ après L183). Pas de lib externe. |

---

## Phase 3 — Plan de fan-out

Recommandation séquencement : **3.A et 3.C en PARALLÈLE** (pas de collision de fichiers), **3.B après 3.A** (parce que `useOrganization` étendu est utilisé par 3.B et est touché en 3.A pour cohérence d'export). Une seule itération de relecture finale ensuite.

### 3.A — Auth UX fix (findings #1, #2, #3, #6, signup polish)

#### Fichiers cibles

| Fichier | Type d'opération |
|---|---|
| `frontend/src/services/api.ts` | **étendre** : ré-exporter `extractApiError` (le déplacer depuis marketplace.ts OU laisser dans marketplace.ts et juste ré-exporter — au choix de l'agent, ne pas le réécrire) |
| `frontend/src/services/marketplace.ts` | **inchangé** sauf si l'agent décide de déplacer la fonction (alors mettre un re-export) |
| `frontend/src/contexts/AuthContext.tsx` (L264, L331, L228–230) | **modifier 3 sites** : remplacer `data.detail \|\| 'HTTP X'` par `extractApiError({ response: { data } }, 'HTTP X')` (l'helper attend une AxiosError-like — adapter le shape) |
| `frontend/src/pages/auth/LoginPage.tsx` (L98) | **inchangé** une fois AuthContext fixé (le message remontera proprement) |
| `frontend/src/pages/auth/SignupPage.tsx` (L76, L46–49) | **étendre** : (a) idem, message remonte propre ; (b) ajouter `<PasswordStrengthMeter>` |
| `frontend/src/utils/passwordStrength.ts` | **CRÉER** (10 lignes, heuristique : score 0–4 selon longueur ≥8/12/16 + classes char) |
| `frontend/src/components/auth/PasswordStrengthMeter.tsx` | **CRÉER** (composant léger ; pas de modal, juste 4 segments + label `t('signup.password.strength.{weak\|fair\|strong}')`) |
| `frontend/src/components/auth/index.ts` | **étendre** : ajouter export `PasswordStrengthMeter` |
| `frontend/public/locales/{en,fr}/dashboard.json` (L394–397) | **modifier 1 string** : `compositions.empty.description` (mention builder visuel) |
| `frontend/public/locales/{en,fr}/auth.json` | **ajouter clés** : `signup.password.strength.{weak\|fair\|strong\|veryStrong}` + texte d'aide |
| `frontend/public/locales/{en,fr}/common.json` | **ajouter section** `onboarding.*` (~50 clés extraites de OnboardingWizard) |
| `frontend/src/components/onboarding/OnboardingWizard.tsx` | **étendre** : remplacer toutes les strings hardcodées par `t('onboarding.…')` |
| `mcp-registry/app/api/v1/auth.py` (L348–361 `login` endpoint) | **étendre** : remplacer le 500 par un self-heal — si user actif sans membership → créer Organization + OrganizationMember(role=ADMIN) à la volée, puis poursuivre |
| `mcp-registry/alembic/versions/` | **CRÉER 1 revision** : data migration qui scanne `users WHERE NOT EXISTS (SELECT 1 FROM organization_members WHERE user_id = users.id)` et crée org+membership pour chacun. Idempotente. |
| `mcp-registry/tests/test_authentication.py` | **étendre** : test "login fixes orphan users" + test "Pydantic 422 detail surfaced" |

#### Anti-doublons explicites

- **NE PAS créer** de second `parseApiError` — utiliser `extractApiError` qui existe déjà.
- **NE PAS créer** de `useLogin`/`useSignup` hooks — `AuthContext` les fournit déjà.
- **NE PAS** ajouter `zxcvbn` à `package.json` — heuristique custom dans `utils/passwordStrength.ts`.
- **NE PAS** créer un nouveau composant Alert — `<Alert>` et `text-red-800` block existent déjà dans LoginPage/SignupPage.
- **NE PAS** dupliquer la logique d'org-creation dans `/auth/login` — appeler une fonction privée partagée avec `/auth/register` (extraire `_ensure_personal_organization(db, user)`).

#### Pattern à imposer

- **Erreur** : un seul helper `extractApiError`, consommé par `AuthContext` (pas par les pages directement).
- **Silent on success** (cf. contrat Sprint 2) : signup réussi → navigate, pas de toast intermédiaire.
- **Conversion typée** : `passwordStrength(password: string): { score: 0|1|2|3|4, label: 'weak'|'fair'|'strong'|'veryStrong' }`.
- **i18n onboarding** : préfixer toutes les clés sous `common.json:onboarding.welcome.*`, `onboarding.chooseServers.*`, `onboarding.connect.*` — pas de dispersion.
- **Backend self-heal** : idempotent + audit log `ACCOUNT_RECOVERY` (ou créer une nouvelle enum) pour tracer.

#### Effort estimé

~6 h-h (1.5 backend + 1 alembic + 2 frontend i18n + 1.5 polish auth/UX).

---

### 3.B — Multi-tenant visible (finding #4)

#### Fichiers cibles

| Fichier | Type d'opération |
|---|---|
| `frontend/src/hooks/useAuth.ts` (`useOrganization` L88–111) | **étendre** : exposer `memberships` (depuis `user.organization_memberships`) + `switchOrganization(orgId)` (factorise TeamPage:187–222) |
| `frontend/src/components/layout/OrgSwitcher.tsx` | **CRÉER 1 seul fichier** : pill compact avec org courante + chevron + dropdown listant les memberships ; appelle `switchOrganization` du hook ; loading state pendant le switch |
| `frontend/src/components/layout/Navbar.tsx` (L84–96) | **étendre** : monter `<OrgSwitcher />` entre la zone nav-links et le user-menu, n'apparaît que si `isAuthenticated && memberships.length > 1` (sinon = pas de switcher, juste un libellé non interactif si `memberships.length === 1`) |
| `frontend/src/pages/settings/TeamPage.tsx` (L187–222) | **refactor** : supprimer la logique inline, appeler `switchOrganization` du hook |
| `frontend/public/locales/{en,fr}/common.json` | **ajouter** clés `orgSwitcher.title`, `orgSwitcher.switchTo`, `orgSwitcher.switching`, `orgSwitcher.errorFallback` |
| `mcp-registry/app/api/v1/auth.py` (L770–850 `/switch-organization`) | **inchangé** — contrat OK |
| `mcp-registry/tests/test_authentication.py` | **étendre 1 test** : "switch-organization preserves request audit context" (déjà sans doute couvert, vérifier) |

#### Anti-doublons explicites

- **NE PAS créer** un endpoint backend en plus — `/auth/switch-organization` + `/auth/organizations` existent.
- **NE PAS créer** un store/context séparé pour le current-org — `useAuth()` est la seule source de vérité (organisation est déjà dans `AuthContext`).
- **NE PAS** dupliquer la logique de save tokens — `switchOrganization` du hook fait `setItem + reload` (réutilise pattern TeamPage), comme aujourd'hui.
- **NE PAS** monter `<OrgSwitcher />` dans une page settings autre que TeamPage (qui sera nettoyée).

#### Pattern à imposer

- **State local séparé** : `OrgSwitcher` gère son propre `isSwitching` (mais l'action vit dans le hook).
- **Silent on success** : pas de toast à l'arrivée, juste reload. Toast d'erreur uniquement si le `fetch` échoue.
- **a11y** : `<button aria-haspopup="menu" aria-expanded={isOpen}>` + `role="menu"` sur le dropdown + chaque item `role="menuitem"`.
- **Zero double-source** : `organizations[]` vient de `/auth/organizations` (fetch on mount, cached avec react-query si présent) ; l'org **active** vient de `user.organization_memberships` + `AuthContext.organization`.

#### Effort estimé

~3 h-h (2 frontend + 1 refactor TeamPage + tests).

---

### 3.C — Compositions polish (findings #5, #7, #8, #9, #10)

#### Fichiers cibles

| Fichier | Type d'opération |
|---|---|
| `frontend/src/components/compositions/builder/CompositionBuilder.tsx` (L394–399) | **modifier** : `onPick` ferme aussi le picker via `setPickerOpen(false)` |
| `frontend/src/components/compositions/builder/StepTypePicker.tsx` (L59–63) | **inchangé** (laisse le `onClose()` interne — double sécurité OK) |
| `frontend/src/components/compositions/builder/forms/WaitUntilStepForm.tsx` (L127) | **modifier** : ajouter `max={86400}` sur l'Input wait_seconds |
| `frontend/src/components/compositions/builder/forms/SubcompositionStepForm.tsx` (L78–81) | **étendre** : ajouter `refetchOnWindowFocus: true` + `staleTime: 30_000` à `useQuery` |
| `frontend/src/pages/compositions/CompositionsPage.tsx` (L1194–1226) | **étendre** : ajouter un `<label className="sr-only" htmlFor="filter-kind">` + `id="filter-kind"` sur chaque select. Idem pour `filter-status`, `filter-visibility`. Garder `title=` comme tooltip. |
| `frontend/public/locales/{en,fr}/dashboard.json` (L354, L365, L404) | **renommer 3 clés** : `steps` → `steps_one` + `steps_other` (idem `parameters` et `executingSteps`) |
| `frontend/public/locales/{en,fr}/dashboard.json` (L388–393) | **ajouter** clés a11y pour les filter labels : `compositions.filters.kindLabel`, `statusLabel`, `visibilityLabel` |
| `frontend/src/components/compositions/builder/AUDIT_AND_PLAN.md` (existant Sprint 2) | **inchangé** — référence historique |

#### Anti-doublons explicites

- **NE PAS** créer un wrapper Select accessible — utiliser `<label className="sr-only">` + `htmlFor` (pattern HTML standard, déjà utilisé ailleurs dans le code).
- **NE PAS** refactor `useQuery` en custom hook — modification 2 lignes inline suffit.
- **NE PAS** créer de namespace i18n séparé `pluralization.json` — la clé reste dans `dashboard.json` à sa place.

#### Pattern à imposer

- **i18next plurals natifs** : suffixe `_one` / `_other` reconnu automatiquement par i18next quand on passe `{ count }`. Pas de logique JS, pas de Intl.PluralRules manuel.
- **a11y silencieux** : `sr-only` ne déplace pas le layout, donc 0 collision visuelle.
- **react-query default sane** : `refetchOnWindowFocus: true` + `staleTime: 30_000` = pattern utilisé par d'autres queries du projet (vérifier qu'on ne casse pas `ToolsWorkspace.tsx:127` qui dépend d'un `currentOrgId`).

#### Effort estimé

~2 h-h (très majoritairement des 1-liners + 6 clés locale).

---

## Phase 4 — Décisions à trancher avant coding

1. **Signup demo (SaaS)** : on garde le flow actuel (verify-email → magic-link auto-login dans /auth/verify-email) OU on ajoute un **preview mode** (catalog/docs lisibles sans auth, avec banner "Sign up to execute") ? Recommandation : le flow magic-link actuel est déjà ergonomique → ne RIEN faire côté preview, mais améliorer la copy de `VerifyEmailPendingPage` pour rassurer.

2. **Auto-org name** : la convention actuelle (`{name}'s Organization` ou `{email}'s Organization`) est-elle la bonne pour Cerema-ready ? Alternative : `"Personal"` (court + neutre). Recommandation : garder `"{name}'s Organization"` pour la cohérence avec les users existants ; pas de rename rétroactif.

3. **OrgSwitcher position** : dropdown style (compact, dans le user-menu existant) OU pill autonome (entre nav-links et user-menu) ? Recommandation : **pill autonome** parce que le finding parle d'un indicateur visible, pas caché dans un sous-menu (cf. session handoff Cerema dry-run qui flaggue "no current-org indicator dans user-menu").

4. **Password meter** : custom heuristique 10 lignes (rapide, suffisant, 0 KB) OU `zxcvbn` (lib ~30 KB gzip, scoring linguistique) ? Recommandation : **custom** — pas besoin de scoring fin pour un signup demo open-source ; cohérent avec la posture "no commercial offer / sober".

5. **Empty state Build** : remplacer la mention "AI assistant" par "or build visually" OU **ajouter** "or build visually" en gardant l'IA ? Recommandation : **ajouter**, parce que l'AI assistant marche toujours — on documente juste qu'il y a maintenant 2 chemins.

6. **Self-heal `/auth/login` (#3)** : créer l'org perso à la volée OU rediriger l'utilisateur vers une page `/onboarding/missing-org` pour qu'il la nomme ? Recommandation : **self-heal silent** — le user voulait juste se connecter, pas configurer une org. Audit log capture l'événement.

7. **Sprint 3 commit pace** : 3 sous-sprints = 3 PRs distinctes OU 1 PR monolithique ? Recommandation : **3 PRs** (3.A, 3.B, 3.C), mergées en série dans l'ordre A → C → B (parce que B dépend du hook étendu de A pour cohérence, mais C est totalement indépendant et peut shipper même si A est en review).

---

## STOP

Aucun `.ts` / `.tsx` / `.py` créé. Aucun fichier modifié hors ce `AUDIT_AND_PLAN.md`.
J'attends ta validation sur les 7 décisions Phase 4 avant de fan-outer les agents de coding.
