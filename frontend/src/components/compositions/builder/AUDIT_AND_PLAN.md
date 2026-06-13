# AUDIT_AND_PLAN — Mini-builder visuel compositions

> Audit factuel de l'existant avant code. Aucun `.tsx` / `.ts` créé.

## 2.1 Inventaire de l'existant

| Fichier | Responsabilité actuelle | L. | Verdict | Raison |
|---|---|---:|---|---|
| `components/compositions/DynamicInputForm.tsx` | Form fields générés depuis `InputSchema` (string/num/bool/enum/array/obj). Utilisé par `ExecuteModal` (runner) pour saisir `inputs`. | 290 | **Réutiliser tel quel** | Couvre tout le primitif JSON Schema; sera porté côté `wait_callback.expected_schema` & `approval.response_schema`. |
| `components/compositions/ElicitForm.tsx` | Form du **résumeur** côté ExecutionDetail (B-1). Coercion num, label/title/format, JSON fallback pour array/obj. | 270 | **Ne pas toucher** | Sert au resume, pas à l'édition. |
| `components/compositions/ExecutionResultDisplay.tsx` | Banner statut + timeline `StepResult[]` + smarts foreach/transform. | 307 | **Réutiliser tel quel** | Bouton "Test run" du builder. |
| `components/compositions/index.ts` | Barrel exports. | 5 | **Étendre** | Ajouter `CompositionBuilder`. |
| `pages/compositions/CompositionsPage.tsx` | God-component : Card, `ExecuteModal` (runner), `ProposeCompositionModal` (LLM + Advanced JSON paste + templates). | 1256 | **Refactor minimal** | Ajouter un 3e onglet `build` dans `ProposeCompositionModal` (pattern `mode: 'llm' \| 'advanced'` déjà là → naturel). |
| `pages/compositions/ExecutionDetailPage.tsx` | UI resume par step type (elicit/wait_until/wait_callback/subcomposition/approval). | 712 | **Pas modifier** | Référence canonique des labels/payloads à respecter dans le builder. |
| `pages/compositions/ExecutionsListPage.tsx` | Liste + filtres. Importe `SUSPENSION_BADGES`. | 408 | **Pas modifier** | Hors scope. |
| `pages/compositions/PendingApprovalsPage.tsx` | Inbox approvals. | 137 | **Pas modifier** | Hors scope. |
| `services/compositionExecutions.ts` | `executionsApi.*` + `SUSPENSION_BADGES` (source de vérité step-type → label/couleurs). | 229 | **Réutiliser** `SUSPENSION_BADGES` | Cohérence picker ↔ list/detail. |
| `services/marketplace.ts` (l. 1429-1700) | Types `Composition`/`CreateCompositionRequest`/`InputSchema` + `compositionsApi.create/update/list/listTemplates`. | extrait | **Réutiliser tel quel** | Aucune nouvelle route ; backend accepte les 5 step types tels quels. |
| `pages/admin/CompositionMetricsPage.tsx` | Telemetry admin. | 280 | **Pas modifier** | Hors scope. |
| `pages/admin/CompositionsReviewPage.tsx` | Queue review share org. | 230 | **Pas modifier** | Hors scope. |
| `components/ui/*` (`Button`, `Modal`, `Card`, `Badge`, `Input`, `ConfirmDialog`/`useConfirm`, `EmptyState`, `ErrorState`, `Spinner`, `Alert`, `Toast`) | UI primitives. | — | **Consommer obligatoirement** | Règle anti-doublons. |
| `components/ui/ConfirmDialog.tsx` | `useConfirm({ requireText? })` typed-confirm. | 134 | **Réutiliser** | Delete step / discard draft. |

## 2.2 Mapping besoins → existant

| Besoin builder | Existant ? | Verdict | Plan |
|---|---|---|---|
| Form pour valeurs d'un schéma (input_schema, sous-schemas) | `DynamicInputForm.tsx` | reuse | Utilisé pour preview + test run. |
| Form elicit | `DynamicInputForm` (schema), `Input`/textarea | compose | `forms/ElicitStepForm.tsx`. |
| Form wait_until | rien | **créer** (pilote) | `forms/WaitUntilStepForm.tsx` — radio mutex `wait_seconds \| resume_at`. |
| Form wait_callback | `DynamicInputForm` (expected_schema) | compose | `forms/WaitCallbackStepForm.tsx`. |
| Form subcomposition | `compositionsApi.list({status:'production'})` | créer | `forms/SubcompositionStepForm.tsx`. |
| Form approval | `DynamicInputForm` (response_schema), `Badge` (chips roles) | créer | `forms/ApprovalStepForm.tsx`. |
| Picker step type | `SUSPENSION_BADGES` (label+couleurs) + Heroicons | créer | `StepTypePicker.tsx` (Modal). |
| State machine builder | rien | créer | `CompositionBuilder.tsx` (`useReducer`). |
| Sérialise → `CreateCompositionRequest` | type existe | créer fonction pure | `serialize.ts`. |
| Validation client | `validate_config` backend autoritatif | créer mince | `validate.ts` — UX only ; 422 backend surfacé via Alert. |
| StepCard wrapper édition | `ExecutionResultDisplay.StepCard` read-only seulement | créer (distinct) | `StepCard.tsx` (dispatch `STEP_TYPE_FORMS`). |
| Confirm destructif | `useConfirm` | reuse | — |
| Toast | `react-hot-toast` | reuse | — |
| Modal | `Modal` UI | reuse | Picker. |
| Test run result | `ExecutionResultDisplay` | reuse | — |
| API client | `compositionsApi` | reuse | `create({...serialize(state), status:'temporary'})`. |
| Select target subcomp | `compositionsApi.list` | reuse | Lazy-load prod compositions. |

## 2.3 Architecture proposée

```
ProposeCompositionModal (CompositionsPage.tsx)
└─ mode toggle: [llm | advanced | build]   ← +1 onglet
   └─ <CompositionBuilder onSaved={onSaved}/>
       ├─ header: name / description (<Input>)
       ├─ input_schema editor (JSON textarea — B-1.0)*
       ├─ <StepList>
       │   └─ <StepCard step onChange onDelete onMove/>
       │       └─ STEP_TYPE_FORMS[s.type]  ← registry
       ├─ <Button>+ Add step</Button> → <StepTypePicker isOpen/>  (Modal UI)
       └─ footer: Test run → <ExecutionResultDisplay/> ; Save draft → compositionsApi.create(serialize)
```

\* Schema-editor visuel pour `input_schema` lui-même = scope ultérieur (JSON textarea acceptée pour B-1.0, pattern déjà toléré par les users en mode Advanced).

**État** : `useReducer` (anticipe move/duplicate/undo plus tard) :

```ts
type StepDraft = {
  step_id: string                        // auto: step_1, step_2...
  type: 'elicit'|'wait_until'|'wait_callback'|'subcomposition'|'approval'
  optional?: boolean
  elicit?: { message; schema; ttl_seconds? }
  wait_until?: { wait_seconds? | resume_at? }
  wait_callback?: { expected_schema?; ttl_seconds? }
  subcomposition?: { composition_id; inputs? }
  approval?: { message; approver_user_ids?; allowed_roles?; response_schema?; ttl_seconds?; allow_self_approval? }
}
```
Actions : `ADD_STEP | UPDATE_STEP | DELETE_STEP | MOVE_STEP | SET_HEADER | SET_INPUT_SCHEMA`.

**Contrat StepForm** (les 5 forms le respectent) :
```ts
interface StepFormProps<T> { value: T; onChange: (next: T) => void; disabled?: boolean }
```
Chaque form émet exactement la shape attendue par `validate_config` Python correspondant. Pas de wrapper, pas de step_id (géré par le builder).

**Sérialisation** (`serialize.ts`) — fonction pure : strip empty, coerce ttl en int, emit 1 seule clé éponyme par step selon `s.type`, default `status:'temporary'` + `visibility:'private'`.

## 2.4 Plan de fan-out (Sprint 2.1 — 4 agents, après pilote)

| Step | Form | Config backend (validate_config) | Champs UI minimum | Réuse |
|---|---|---|---|---|
| elicit | `forms/ElicitStepForm.tsx` | `message:str≠"" + schema:object(type) + ttl:1..86400` | Textarea msg, JSON textarea schema, num ttl | Input, pattern advancedJson |
| wait_callback | `forms/WaitCallbackStepForm.tsx` | `expected_schema?:object + ttl:1..86400` | Collapsible expected_schema (JSON textarea), num ttl (default 86400) | idem |
| subcomposition | `forms/SubcompositionStepForm.tsx` | `composition_id:UUID + inputs?:object` | Select compos prod + JSON textarea inputs map | compositionsApi.list, EmptyState si 0 prod |
| approval | `forms/ApprovalStepForm.tsx` | `message + ≥1(approver_user_ids[] OR allowed_roles[]∈{owner,admin,member,viewer}) + response_schema? + ttl? + allow_self_approval?` | Textarea msg, multi-select roles (Badge chips), textarea user UUIDs (newline-sep), collapsible response_schema, checkbox self-approval (`useConfirm` danger), num ttl | Badge, DynamicInputForm |

**Pilote Sprint 2.0** : `forms/WaitUntilStepForm.tsx` — radio mutex `wait_seconds | resume_at` (`<input type=number>` ou `<input type=datetime-local>`). Schéma minimal, isolation max.

## 2.5 Anti-doublons explicites

Je **NE crée PAS** :
- ❌ Form generator JSON Schema → `DynamicInputForm` couvre.
- ❌ ConfirmDialog → `useConfirm({ danger, requireText })`.
- ❌ Modal wrapper → `Modal` primitive.
- ❌ Client API compositions → `compositionsApi` (services/marketplace.ts) & `executionsApi` (services/compositionExecutions.ts).
- ❌ StatusBadge/SuspensionBadge → `SUSPENSION_BADGES` du service.
- ❌ Toast wrapper → `react-hot-toast` direct.
- ❌ "Résultat d'exécution" → `ExecutionResultDisplay` pour le test-run.
- ❌ ElicitForm (côté builder) — il reste le **résumeur** côté receveur ; le builder produit la config, jamais l'UI de réponse.
- ❌ Nouvelle page : tout vit dans `ProposeCompositionModal` (sans renommage pour ne pas casser les imports).
- ❌ Client `compositionTemplates` → `compositionsApi.listTemplates()` existe.
- ❌ Schema-editor visuel pour `input_schema` → JSON textarea pour B-1.0 (pattern déjà toléré).

---

## STOP

Aucun fichier `.tsx`/`.ts` créé. J'attends validation avant d'attaquer le squelette + pilote `WaitUntilStepForm`.
