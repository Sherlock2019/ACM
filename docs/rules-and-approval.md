# Rules, permissions and approval

## Three levels of rules

1. **Rules of conduct (R01–R32):** global, permanent. Stored in `config/conduct_rules.json` and pinned by `CONDUCT_SHA256` in `domain/conduct.py`. At startup the backend checks the IDs (R01..R32 in order), the `permanent` flag and the hash. Any mismatch raises `ConductIntegrityError`, and AFM refuses to start. Each rule carries `enforcement` (enforced / partial) and `how`. Runs and use cases record the `rules_version` (`conduct-<hash prefix>`).
2. **Environment rules:** from the adapter's `scenario.json`, checked by the adapter (`rule_checks`, `error_rules`) and by tool permissions.
3. **Use-case rules:** may only narrow:
   - *enforced:* the rule names a state-changing tool or its target type plus a change verb. The tool is blocked (`prohibited`) for that use case's assessments and recheck.
   - *recorded:* shown in the assessment, but not automatically checked.
   - *conflict:* the rule would weaken global rules (skip/bypass/ignore approval or rules, "you may", "auto-approve", …). *Prepare assessment* is refused until it is removed.

Nothing in a goal, chat message, LLM answer or environment content can change any rule. Changing rules of conduct is a two-step human edit (file + pin). Changing environment rules is an edit of the adapter's scenario.

**Security note.** A local, pinned file is enough for a single-user prototype. A multi-user system would need authenticated users, server-side authorization per action, protected and audited configuration, and tamper-evident logs. None of these are in this MVP.

## Permission classes

| Class | Meaning |
|---|---|
| allowed | read-only or on a copy; no approval |
| requires_approval | changes state; needs explicit approval of the exact plan |
| prohibited | never executable, even with approval (R24) |

## The five checks

| Check | Statuses |
|---|---|
| A. Capability: tool registered in this environment, executable, right operation | PASS / FAIL |
| B. Permission | PASS / FAIL (prohibited) / UNKNOWN |
| C. Rules: rules of conduct + environment rules; FLAG items (e.g. W3 port mismatch) | PASS / REVIEW REQUIRED / FAIL / UNKNOWN |
| D. Goal: adapter evaluates each criterion on the predicted state | PASS / FAIL / UNKNOWN |
| E. Human review | REVIEW REQUIRED if any action changes state |

A plan is **approvable** only if it is feasible and A–C contain no FAIL or UNKNOWN (R20). It is **recommended** only if D also passes. Among those, the recommendation prefers fewer warnings, then fewer changed objects (R12), then reversible plans (R27). If none qualifies, AFM says so instead of inventing a plan.

## Approval and execution

An approval records the plan hash (plan id, goal id, ordered actions and every parameter), environment version and fingerprint, reviewer, note and time.

Execution checks, in order:
1. Not already executed.
2. Active approval for this run and plan.
3. Hash matches (also for a submitted plan).
4. Adapter supports execute.
5. Environment unchanged.
6. Re-simulate with the same blocked tools: still approvable, identical prediction.
7. Commit once, mark the approval used, observe and compare.

Any change invalidates the approval (R13). A rejected plan can never be approved or executed in that run (R28).

## Untrusted content and the LLM

- Free text in objects (Order B's customer note, the app's code comment) is shown as data and flagged as ignored (R22).
- LLM proposals with `command`/`shell`/`sql`/`code`/`script` are rejected as executable content. Proposals with `skip_approval`/`auto_approve`/`rule_changes`/`permissions`/`new_rules` are rejected under R10. Unknown or other-environment tools, prohibited tools and malformed plans are rejected too. An accepted LLM action always gets its permission from AFM's configuration.
- Chat proposals for use-case fields stay *pending* until the human accepts or edits them. An invented adapter ID is dropped.

This approval flow is a local prototype workflow without login. It is not production-grade authentication or authorization.
