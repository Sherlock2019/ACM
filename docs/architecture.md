# Architecture

```
frontend (React + Vite, :5530) ──/api proxy──► backend (FastAPI, :8530)

api/routes.py         typed requests; errors as {"error": {code, message}}; no stack traces or secrets
engine/  (GENERIC CORE: no domain terms, enforced by tests/test_generic.py)
  service.py          AFMService: one Runtime (adapter + store) per environment; assess, review, decide,
                      execute-once, observe; backend approval gate
  simulator.py        copy state → adapter.simulate_action per step → adapter.connected_effects →
                      CORE-1 unknown-dependency consequences; read-only tools must not change state
  checks.py           A capability · B permission · C rules · D goal · E review; plan hash
  planner.py          LLM/human proposal gate (schema, registered tools, prohibited, rule-change and
                      executable-content rejection); recommendation (R12 fewer warnings → fewer changed
                      objects → R27 reversible → fewer actions)
  environment.py      EnvState (copy, fingerprint) and EnvironmentStore (version, persist, reset)
  usecases.py         use-case builder: fields, rule narrowing/conflicts, chat with pending proposals,
                      prepare (assess or honest "not connected")
adapters/  (ENVIRONMENT-SPECIFIC)
  base.py             EnvironmentAdapter interface + AdapterError
  playground/ webapp/ inventory/   scenario.json (data) + adapter.py (behavior)
  registry.py         implemented adapters + FUTURE_ADAPTERS (not implemented / not connected)
  llm.py              LLM tool interface, MockLLM, provider placeholder
  claude_provider.py  Claude via the official SDK (explain, propose, chat; structured outputs)
domain/  models.py (schemas) · profile.py · conduct.py (pinned rules of conduct) · errors.py
storage/db.py         SQLite: environment state per adapter, runs, use cases
```

## What belongs where

| Generic core | Environment adapter |
|---|---|
| Copying state, ordering steps, error capture | How an action changes objects (simulation rules) |
| Tool registry, permission classes, prohibited tools | Which tools exist, their parameters, permission, reversibility |
| The five checks and statuses | Environment rules (`rule_checks`), which errors violate which rule |
| Goal evaluation flow | Goal parsing, success criteria, R30 pre-check content |
| Unknown-dependency reporting (CORE-1) | Which relationships exist and their evidence |
| Approval binding, stale detection, execute once | Whether execute is supported (`capabilities`) |
| Observation comparison | How to re-measure derived values (`measure`) |

## Adapter interface (`adapters/base.py`)

| Member | Purpose |
|---|---|
| `describe_environment()`, `rules()`, `tools()`, `demo_goals()`, `definitions()`, `limitations()`, `layout()` | static description, mostly from `scenario.json` |
| `initial_state()` | objects and relationships for a new or reset environment |
| `capabilities` | `{"inspect", "simulate", "execute"}`; the core refuses unsupported operations |
| `interpret_goal(text, state)` | `GoalSpec` with criteria and pre-check, or unsupported plus clarification |
| `propose_plans(goal, state)` | deterministic candidate plans |
| `simulate_action(action, state, step)` | apply one action to the copy, return consequences, or raise `AdapterError` |
| `connected_effects(before, after, plan, step)` | effects on the final state (e.g. reachability) |
| `evaluate_criterion(criterion, predicted)` | PASS / FAIL / UNKNOWN plus detail |
| `rule_checks(plan, sim, predicted)` | environment rule results (PASS / FLAG = REVIEW REQUIRED / FAIL) |
| `error_rules` | error code → violated rule (definite FAIL; other errors → UNKNOWN) |
| `measure(state, object_id, key)` | re-measure observable predictions after execution |

The playground adapter is about 150 lines, which makes it a good template.

## 16-step workflow and Win (current)

1 Task goal → 2 purpose/rules/permissions (standing context) → 3 environment → 4 target & missing info → 5 objects → 6 inspect (+LLM) → 7 actions/tools → 8 plans → **9 pre-check** (`AFMService._assess_plan`: capability and permission are checked first; failing plans get `rejected_before_prediction` and are never simulated) → 10 predict → 11 compare/recommend → 12 review (`decide`, with optional `criteria_agreed`) → **13 recheck** (approval, plan hash, environment fingerprint, **policy version**, re-simulation) and execute once → 14 observe (`Observation.method/source/simulated/snapshot`) → 15 compare (MATCH / MISMATCH / NOT VERIFIED, with `required` vs informational items) → **16 Win** (`engine/win.py`: prediction accuracy, task goal on the observed snapshot, rule compliance; human judgments via `verify`).

`policy_version` hashes the rules of conduct, profile tools, the adapter's rules and tools, and use-case blocked tools. Any change invalidates an approval (`policy_changed`). Stored runs with the old `DIFFERENCE` result are read as `MISMATCH`. Saved 15-step simulations migrate to 16 steps (`steps_version` 4), keeping the human's edited notes.

## Run lifecycle

1. **assess(env, goal)**: snapshot (version, fingerprint) → load the rules of conduct (version recorded) and the environment rules → adapter interprets the goal (unsupported → stop with explanation) → adapter proposes plans → simulate and check each → ask the LLM for proposals, validate them, simulate the valid ones → recommend, or report "no viable plan".
2. **decide**: refused on a plan-hash mismatch, a changed environment, a non-approvable plan, an existing decision for that plan (R28), or another plan already approved.
3. **execute**: run-once → active approval for this plan → hash matches → adapter supports execute → environment unchanged → re-simulate with the same blocked tools, still approvable, identical prediction → commit (version + 1) → mark approval used → observe → save.

## API (main routes)

| Route | Purpose |
|---|---|
| `GET /api/profile` | identity, generic tools, rules of conduct, rules version |
| `GET /api/environments` | adapter descriptions + future adapters |
| `GET /api/environments/{env}` · `/view` · `/objects/{id}` · `/relationships` | inspect |
| `POST /api/environments/{env}/reset` · `/goals/interpret` · `/simulate` | reset, goal, ad-hoc plan |
| `POST /api/assessments {environment_id, goal_text}` | run the loop |
| `GET /api/runs` · `/runs/{id}` · `/runs/{id}/review/{plan}` · `/runs/{id}/comparison` | history, review, comparison |
| `POST /api/runs/{id}/decision` · `/execute` | approve or reject; execute once |
| `GET /api/llm/status` · `POST /api/llm/object-type` | provider + privacy; explain an object type |
| `GET/POST /api/usecases`, `GET/PUT/DELETE /api/usecases/{id}` | use cases |
| `GET /api/usecases/{id}/summary` · `POST /chat` · `POST /proposals/{i}` · `POST /prepare` | builder |
