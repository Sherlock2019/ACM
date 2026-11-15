# Object model (generic)

All schemas are in `backend/app/domain/models.py`. Unknown fields are rejected. No executable code is stored in scenarios or accepted from an LLM.

## Object, relationship, evidence

`EnvObject`: `id, type, name, purpose, state, accepted_actions, outputs, behavior (plain-language reference; executable behavior lives in the adapter), constraints, evidence, last_observed, known_unknowns, untrusted_text`.

`Relationship`: `id, source, target, type, direction, description, evidence`.

| Evidence | Meaning |
|---|---|
| observed | returned by an adapter inspection or after an approved execution |
| configured | written explicitly in the scenario |
| inferred | suggested by the LLM or a prediction |
| unknown | not established (e.g. *Possible firewall*, *Possible ERP sync*) |

## Action, plan, goal

- `Action`: `action_id, actor, tool, operation, target_object_id, parameters, expected_preconditions, permission (always from configuration), purpose`.
- `Plan`: `plan_id, goal_id, title, actions[≥1], assumptions, known_limitations, proposed_by (deterministic_planner | llm | human)`.
- `GoalSpec`: `environment_id, text, supported, intent, parameters, success_criteria[{id, kind, params, description}], explanation, clarification_needed`, plus the R30 pre-check (`intended_benefits, potential_negative_effects, missing_information`). Criteria are fixed when the goal is interpreted (R26).

## Consequence

`step, affected_object_id, relationship_to_target, before, predicted_after, description, type (direct | connected), evidence_rule (e.g. PLAY-2, WEB-4, INV-5, CORE-1), assumptions, status (known_in_simulation | conditional | unknown), effect (benefit | neutral | warning, R29), observable (values the adapter can re-measure)`.

## Playgrounds

### Generic Object Playground (`object-playground`)

| Object | State |
|---|---|
| Object A (Input) | `value: 5` |
| Object B (Processor) | `input: 5, factor: 2, output: 10` |
| Object C (Display) | `shown: 10` |

A → B → C (`feeds`).

Rules:
- **PLAY-1** set_value sets A.
- **PLAY-2** B.output = A × 2.
- **PLAY-3** C shows B.output.

### Web application (`webapp-demo`)

Website users → Web server (listen 443, upstream 8000) → Python application (listening 8000) → Database (12,480 records). The Health monitor checks 8000. A possible firewall *may filter* the app (unknown).

Tools:
- `set_app_port`, `set_proxy_upstream`, `set_monitor_port`: approval required, reversible.
- `send_test_request`: read-only.
- `stop_service`, `delete_database_records`: prohibited.

Rules:
- **WEB-1..3** port changes.
- **WEB-4** users can reach the app iff upstream == listening port and both are running.
- **WEB-5** the monitor is healthy iff target == listening port.
- **WEB-6** the database does not depend on the app port.
- **WEB-7** test request.

### Inventory (`warehouse-demo`)

Widget A; Warehouse 1 / 2 with inventory 100 / 50; Order A needs 30 (from either warehouse); Order B needs 80 (Warehouse 1 only); a dashboard; a possible ERP sync (unknown).

Rules:
- **INV-1** reserve.
- **INV-2** order status.
- **INV-3** dashboard.
- **INV-4** reservation record.
- **INV-5** other orders' eligible stock.

## Use case

- `UseCase`: `usecase_id, title, rules_version, fields, extra_rules[{text, status (recorded | enforced | conflict), blocks_tool, explanation}], messages[{role, content, provider, labels, proposed_fields, suggested_questions, proposal_status}], run_ids`.
- `UseCaseFields`: role, purpose, environment (type, name, description, adapter), target (name, type, identifier, known info, proposed action), goal (outcome, success criteria, constraints, mode), evidence (untrusted).
