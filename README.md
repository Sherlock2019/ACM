# ACM — Action–Consequence Foresight Model

**Think before acting.**

AFM is a generic decision-support system. It **understands an environment, assesses the possible consequences of actions, checks human goals and rules, and requests human review before making changes.** It works through *environment adapters*. Three local, fictional, **simulated** playgrounds are included. No real AWS, SAP, server, database or production system is connected or modified.

> **What this is not.** A prototype, not a trained foundation model. The environments are fictional simulations. AFM cannot guarantee it has found every dependency, and this prototype does not prove real-world safety. Saved history and chat **do not train** any model. Review every integration yourself before any real-world use.

---

## The idea in one picture

```
 human goal ─► adapter interprets goal (+ R30 pre-check) ─► candidate plans ─► simulate on a COPY ─► checks A–E ─► recommendation
                                  ▲                                                                       │
          LLM (a tool) ──────────┘ explains object types; proposals pass the same gate                   ▼
                                                                                         HUMAN REVIEW (approve / reject)
                                                                                                         │ bound to plan hash
                                                                                                         ▼ + environment fingerprint
                                                   execute ONCE in the simulation ─► observe ─► compare ─► experience history
```

- **AFM is the decision-maker.** Its rules, permissions, consequence engine and approval gate are deterministic Python code on the backend.
- **The LLM is a tool.** AFM may consult it to explain an object type, suggest read-only inspections, help fill in a use case in chat, or propose plans in a strict structured format. Its output is always labelled *LLM-generated / general knowledge*. It is never treated as a fact about the environment, and it can never change rules, skip approval or execute anything.
- **Adapters hold everything domain-specific:** objects, relationships, actions, simulation rules, goal parsing and success criteria. The generic core has no warehouse, port or object-A logic, and a test checks this.

## The three playgrounds

| Playground | Shows | Demo goal | What AFM predicts |
|---|---|---|---|
| **Generic Object Playground** (simplest) | How one change flows through connected objects: Input A → Processor B (×2) → Display C | “Change Object A's value to 10 and show me what will happen.” | A 5 → 10 (direct), B 10 → 20 and C 10 → 20 (connected), each citing its configured rule |
| **Web application port change** (main demonstration) | Users → web server → Python app → database, plus a health monitor and an *unverified* firewall | “Change the application to port 9000 while keeping it accessible. Do not delete data. Ask me before making changes.” | **P1** (app port only): web server still forwards to 8000, users may lose access, monitor reports unhealthy, database unchanged → goal **FAIL**, port-mismatch flag. **P2** (app + web server + test): accessible, but the monitor warning remains (trade-off). **P3** (app + web server + monitor + test): **recommended** |
| **Inventory Assistant** (business example) | Two warehouses, two competing orders, a dashboard, an unverified ERP sync | “Fulfill Order A while avoiding a shortage for Order B.” | P1 (Warehouse 1: 100 → 70) leaves Order B short. **P2** (Warehouse 2: 50 → 20) is recommended |

*Without foresight:* “I changed the port. The application is now unreachable.” *With AFM:* “I predicted the dependency problem, proposed a complete plan, and asked the human to review it.”

## Run it

Requires Python 3.11+ and Node 18+. Tested with Python 3.12 and Node 24 on WSL Ubuntu.

```bash
./start.sh            # always stops running AFM servers, then starts fresh (installs on first run)
# UI  → http://127.0.0.1:5530      API → http://127.0.0.1:8530 (interactive docs at /docs)
./start.sh stop | status | restart | test
```

`./start.sh test` runs the backend tests (`pytest`) and the frontend type-check plus production build.

**Other ports:** `AFM_FRONTEND_PORT=3010 ./start.sh` (and `AFM_BACKEND_PORT=…`), or put `AFM_FRONTEND_PORT=3010` in `backend/.env` once. `start.sh` stops every ACFM server started from this folder whatever its port, never stops another program, and if another program (another app, another user, Docker) holds a port it says so right away instead of waiting. The app lives under `/acm/` and its home page is **`/acm/home`** (e.g. `http://127.0.0.1:3010/acm/home`; the bare address redirects there). Change it with `AFM_BASE_PATH`.

By default the UI listens on `127.0.0.1` only: from another machine use an SSH tunnel, e.g. `ssh -L 3010:127.0.0.1:3010 ubuntu@your-server`, then open `http://127.0.0.1:3010/acm/home`.

**Public mode (e.g. EC2):** put these lines in `backend/.env` on the server, open the port in the security group, and run `./start.sh`:

```
AFM_FRONTEND_PORT=3010
AFM_HOST=0.0.0.0
```

The app is then at `http://<server-public-ip>:3010/acm/home`. The backend stays on `127.0.0.1` and is reached only through the UI server. **There is no login in public mode:** anyone who reaches the address can use everything, including real-project mode (which clones repositories and runs approved commands on that server) and your LLM credits. This was the owner's choice for this deployment; `start.sh` prints the public address and this warning on every start.

### Run a simulation: the 16-step workflow, from Task Goal to AFM Win

Every card on the Overview has **Run simulation**. It opens a timeline of the 16 steps for that use case: Generic Object Playground, Web Application Port Change, Inventory Assistant, or Data Readiness Agent.

| # | Step | # | Step |
|---|---|---|---|
| 1 | **Understand the task goal**: desired input, desired output, observable success criteria | 9 | Check each plan's actions against rules and permissions; **reject prohibited plans before prediction** |
| 2 | Check purpose, rules and permissions (standing context, enforced from the start) | 10 | Predict consequences for each remaining plan, on each object and the whole environment |
| 3 | Identify the environment and its honest connection status | 11 | Compare plans: outcome rules, goal criteria, trade-offs; recommend or say none qualifies |
| 4 | Identify the target and missing information (ask, or mark incomplete) | 12 | Present the assessment and request human review |
| 5 | Discover relevant objects and connections | 13 | Recheck plan, **policy** and environment; execute only if approved and supported |
| 6 | Inspect states and understand behavior (LLM explains, observations decide) | 14 | Observe the actual test results (method, time, snapshot, simulated/connected) |
| 7 | Identify possible actions and tools | 15 | Compare predictions with test results: **MATCH / MISMATCH / NOT VERIFIED** |
| 8 | Propose candidate plans | 16 | **Evaluate the AFM Win** |

**Why the Task Goal starts the assessment:** AFM must know what success looks like before it looks around. That way discovery, inspection and planning stay focused on the task. Identity, rules and permissions are not "later" steps: they are standing context, loaded and enforced from the first moment (step 2 shows them; the run log records the rules and policy version right after the goal).

**Success criteria:** criteria derived by the environment adapter are labelled *proposed by adapter*. Criteria you type (one per line in step 1) are labelled *yours*; they are not machine-checkable, so you verify them after execution. AFM never presents proposals as human-approved: you explicitly agree to the criteria in the approval dialog (step 12). Without that agreement, task goal achievement stays NOT VERIFIED.

### The AFM Win (step 16)

A **WIN** needs all three conditions, judged on observed evidence after execution:

| Condition | Question | PASS | FAIL | NOT VERIFIED |
|---|---|---|---|---|
| **A. Prediction accuracy** | Did all required predictions match the observed test results? | all required outcomes MATCH | any required MISMATCH | a required outcome could not be observed |
| **B. Task goal achievement** | Did the observed results meet the agreed task goal and success criteria? | every required criterion met on the *observed* state | a criterion observed not met | criteria not agreed, or a human criterion not yet verified |
| **C. Rule compliance** | Were rules and permissions respected throughout? | concrete checks pass across planning, simulation, review, execution and reporting | a known violation (including a human-recorded FAIL) | a required check cannot be established |

**Overall:** any FAIL → **NOT A WIN** (the FAIL stays visible even if something else is unverified). No FAIL but something unverified → **NOT VERIFIED**. All PASS → **WIN**.

- *Accuracy ≠ success:* correctly predicting a bad outcome is a MATCH. In the web demo, changing only the app port gives "users lose access" predicted and observed, so accuracy PASSES but the task goal FAILS, and the result is NOT A WIN.
- *No invented results:* a rejected, unsupported or unexecuted plan gets no observation and no Win ("Not evaluated").
- *Broad principles* (rules marked "partially enforced") are not proven by the absence of a detected violation. Under "Record a human judgment" you can record PASS/FAIL with evidence; a recorded FAIL can never be hidden by a later PASS.
- Everything is computed on the backend (`engine/win.py`), never by the LLM or the browser. In the demos all results are **simulated** and labelled as such.
- API: `task_goal` (the old `goal_text` is still accepted), `desired_input`, `desired_output`, `success_criteria`; `POST /runs/{id}/decision` takes `criteria_agreed`; `POST /runs/{id}/verify` records human judgments; runs carry `policy_version`, `execution_status` and `win`.

### How the simulation page works

- **Prefilled:** each step has AFM's reasoning note for the use case (editable) plus live data, with evidence labels: configured, observed, LLM-generated, predicted, conditional, unknown, human input, illustrative.
- **Live 2D view (right panel):** a small canvas engine draws the environment, every object and the AFM agent. It animates each planned action as a beam to its target, then consequence waves to connected objects (green benefit, amber warning, blue neutral change, dashed grey unknown), then "awaiting your approval", then "executed", with ✓ on observed matches. It has plan chips and replay, respects reduced motion, and offers an "Animation as text" version.
- **Chat overrides any step:** “step 9: …” proposes new text for that step's note; “add rule: …” proposes a use-case rule (still checked for conflicts); inputs like goal or port can change too. Every proposal waits for Accept / Edit / Dismiss. Computed results (predictions, checks, approval, execution, observation) can never be written by chat: they come only from AFM's engine (R18).
- **Real statuses only:** Not started, Ready to run, In progress, Waiting for information, Waiting for review, Approved, Rejected, Completed, Failed, Unsupported, Not verified. Future steps are never shown as completed.
- **Change the steps:** edit the task goal, input, output and criteria (step 1), and the role and use-case rules (step 2) directly, or ask the **chat** (Claude when configured). For example, “use port 9500 instead”. Chat proposals wait for **Accept / Edit / Dismiss**. Then **Re-run simulation**.
- **Steps 12–16 run inline:** approve or reject the plan (the same backend gate), recheck and execute once, observe, compare, and see the **AFM Result** panel. It is also shown in Results & History.
- **Data Readiness Agent** has no AFM adapter, so its simulation is honestly **not connected**. Steps 1 and 3–16 show *Unsupported* and there is no Win. Its notes come from a one-time read-only look at `~/DataReady` (commit `356066e`) taken while building the template, are labelled illustrative, and are not an AFM assessment.

Simulations are saved like use cases (local, deletable). The templates live in each adapter's `scenario.json` (`simulation`) and in `backend/app/adapters/templates/`.

### Try each playground step by step (about 2 minutes each)

1. **Overview** → pick a card → **Try its goal**. The demo goal is pre-filled in **Goals & Plans**.
2. **Assess goal & predict plans**. You'll see the goal pre-check (intended benefits, possible negative effects, missing information) and the candidate plans.
3. **See consequence assessment**. The graph highlights every predicted change (amber = warning); switch between plans; read the side-by-side comparison and the recommendation.
4. **Review this plan** → **Approve simulated execution** (confirm) → **Run approved simulated execution**.
5. **Results & History** shows predicted vs observed values: MATCH / DIFFERENCE / NOT VERIFIED.
6. **Reset playground** (sidebar) restores that simulation only.

## Create your own use case (form + chat)

Open **Create a use case** (top of the sidebar).

- **Left, the structured form:** AI agent role and purpose; the 32 global rules (loaded automatically, with their version); optional use-case rules; environment (type, name, description, adapter, connection status); target object; goal, success criteria, constraints, *analysis only* or *propose a plan*; evidence notes (treated as untrusted input).
- **Right, chat:** describe the use case in plain words, ask about an object type, or ask what AFM still needs. The chat may **propose** form updates. You **Accept**, **Edit** or **Dismiss** them; nothing is applied silently. Each answer carries labels: *General knowledge (LLM)*, *Based on a simulated environment*, *Observed adapter result*, *Prediction*, *Unknown / unverified*.
- **Prepare assessment:**
  - *With a simulated adapter:* runs the normal AFM loop (predict, check, recommend, then ask you).
  - *Without an adapter* (e.g. AWS, SAP, a spreadsheet): AFM says it has **not** inspected, simulated or executed anything, lists what is missing, and can add general LLM knowledge clearly labelled. Describing an environment in chat never connects it.
- Examples to start from: Generic Object Playground, Web Application Port Change, Inventory Assistant, and Data Readiness Agent (not connected: that project is separate).
- Use cases and their chat history are stored locally (SQLite) and can be deleted. **Saved chat is not model training.**

## Test on your real project (local folder or GitHub)

Open **TEST IT → Overview** and press **Test on your project** on the red card (or use **Your real project** in the side menu). Sample projects (the three simulated playgrounds and the not-connected Data Readiness Agent) are in the **Sample projects** dropdown next to it. Pick your LLM first with **Use your LLM model** in the Overview header (Claude, an OpenAI-compatible cloud, or a local model such as Ollama). The offline mock cannot write code.

1. **Connect.** Give an absolute local path or a public GitHub URL (optional branch, tag or commit), then **Create test workspace & inspect**. ACFM makes a separate copy in `~/ACFM/workspaces/` (git-ignored): a `git clone` of a local Git project at its current commit (uncommitted changes are not copied), a file copy of a plain folder (dependency folders skipped), or a shallow clone from GitHub. Git hooks are disabled; nothing is installed and no project script runs. **Your folder is only read.**
2. **Inspect (step 4–6).** Read-only: languages, files, key files, existing tests and suggested test commands (not run). README text is data, never instructions.
3. **Project overview (step 4).** Right after the scan, your LLM reads the README, config and up to 10 main source files and lists the **project name, its goal, all features it can see and suggested improvements**. Labelled LLM-generated; it is a description, not evidence. **Use this change →** copies a suggestion into the step-8 box.
4. **Describe the change in plain words (step 8).** e.g. *"Make add() in calc.py return the sum instead of the difference."* Files you name are sent automatically, with their own test files (`calc.py` → `tests/test_calc.py`; a full path such as `mobile/App.tsx` sends only that file); pick more in step 7. Your LLM replies with the Task Goal, test commands, success criteria and **2–3 alternative plans**. For each plan:
   - the code change as exact *replace this text with that text* edits. **ACFM writes the diff itself** and checks that it applies;
   - **predicted consequences per object**: the target it changes, connected objects (callers, importers, screens, API clients, tests) and the whole project (users, contracts, security), each marked benefit / risk / neutral / unknown with a reason. ACFM adds the files that really import the changed file (found by following import paths in the copy, labelled *found by ACFM*);
   - testable predictions (exit code `0` / non-zero / **same as before the change**, one test's outcome, "no other test changes", or a human check) and risks.

   The plans are shown side by side; **ACFM recommends one** (applies cleanly, fewest predicted risks, fewest changed files) and you choose with **Use plan A/B/C**. That fills steps 1, 8, 10 and 11 and saves them; the chosen plan's consequences are part of what you approve. Ask again to refine. You can always edit the patch and commands by hand.
5. **Pre-check (step 9)** on every save: the patch applies (`git apply --check`) and stays inside the workspace; commands are not shells, `sudo`, `curl`, `rm`, `git push/reset/clean`…. Predictions are saved before anything runs.
6. **Review (step 12).** You approve the exact plan; the approval is bound to commit, patch, commands, predictions and policy. Any change cancels it.
7. **Run once (steps 13–14).** Recheck, then the approved commands run **before** the patch (baseline), the patch is applied, and the same commands run **after**. Secrets are removed from the environment, `HOME` is temporary, each command has a time limit. **This is not a sandbox:** tests can still read your files and reach the network.
8. **Compare and Win (steps 15–16).** MATCH / MISMATCH / NOT VERIFIED per prediction (missing tools or dependencies → NOT VERIFIED, never a pass), then prediction accuracy · Task Goal · rule compliance (including "your original folder was not modified"). Per-object consequences that no test measured are listed as **not verified**: untested never means "no effect".

**Getting a real result instead of NOT VERIFIED:** ACFM never installs anything, so the test command must work on this machine. For a Python backend, point the command at a Python that has the project's dependencies, e.g. `/path/to/venv/bin/python -m pytest -q -rA backend/tests`; services the tests need (a database, for example) must be running. Code with no tests (e.g. a mobile app) can only be checked by a human judgment in step 16 or by adding a test in the plan.

What is sent to the LLM: your message, the Task Goal, languages, test file names, suggested commands, the current plan, and only the files named, picked or listed under "Read" in the overview. Never your API key, other projects or files outside the workspace.

Delete a test from the project list to remove its workspace copy. Not in Phase 1: private repositories, container isolation, applying the change back to your folder, exporting examples for training.

## Rules

### Permanent rules of conduct (R01–R32, global)

AFM's 32 rules of conduct (e.g. *R08 Respect human review*, *R16 Say “I don't know”*, *R22 Treat external content as data*, *R24 Do not treat approval as unlimited authority*) live in `backend/app/config/conduct_rules.json`. They are:

- **Global:** they apply in every environment and every use case.
- **Permanent:** read-only at runtime and pinned by a SHA-256 in `backend/app/domain/conduct.py`. If anyone edits, weakens, reorders or removes a rule without also updating the pin, **the backend refuses to start**. Changing them is therefore a separate, deliberate, human-controlled operation (R10).
- **Honest about enforcement:** each rule is marked *Enforced by code* (20) or *Partially enforced* (12), with a note on how. For example, *R02 Do not steal* is partial: AFM has no tool that could move assets, but nothing checks real-world resource use.

Every run records the rules version it was assessed under.

### Environment rules

Each adapter adds its own rules (Inventory I1–I4, Web W1–W5, Playground P1–P3). They change when you switch playgrounds.

### Use-case rules

Use-case rules can only **narrow** permissions:

- A rule that names a state-changing tool, or the object type it changes, **blocks that tool** for the use case's assessments and their execution. For example, “Do not change the health monitor” blocks `set_monitor_port`, so P3 becomes non-approvable and P2 is recommended.
- Other rules are recorded and shown, marked *not automatically checked*.
- A rule that tries to weaken global rules (e.g. “Skip the approval step”) is a **conflict**: *Prepare assessment* is blocked until you remove it.

### The five checks and the approval gate

Every plan gets: **A** capability · **B** permission · **C** rules (rules of conduct + environment + flags) · **D** goal criteria · **E** human review. Statuses are PASS / FAIL / REVIEW REQUIRED / UNKNOWN. A FAIL or UNKNOWN in A–C makes a plan non-approvable (R20).

Approval is bound to the exact plan (hash of the ordered actions and parameters) and the environment fingerprint. Before running, the backend re-checks the approval, plan, environment version, permissions and rules, and re-simulates. It executes **once**. Any change invalidates the approval (R13).

## Use your own LLM model (UI)

Click **Use your LLM model** (sidebar, or the chat header) and choose one option:

| Option | What you enter |
|---|---|
| **Claude (Anthropic)** | API key (platform.claude.com → API Keys) *or* tick "use `ant auth login`" · model · effort · timeout |
| **Cloud API** (OpenAI-compatible) | provider preset (OpenAI, Google Gemini, Groq, OpenRouter, Mistral, Other) · base URL (prefilled) · model name · API key · timeout |
| **Local model** | server preset (Ollama `:11434`, LM Studio `:1234`, vLLM `:8000`, llama.cpp `:8080`, Other) · base URL · model (**List models** fills it from the server) · optional key · timeout. Nothing leaves this machine |
| **Mock** | nothing |

- **Test connection** sends one tiny request. **Save & use** switches AFM live, with no restart. **Revert** goes back to `backend/.env`.
- The key is stored only in `backend/data/llm_settings.json` (git-ignored, file mode 600). It is never shown again (only "…abcd"), never logged, and never sent anywhere except the chosen provider.
- Settings can only be changed from this machine.
- A key is refused over plain `http` to a remote host, and credentials inside a URL are refused.
- Whatever model you pick, its answers are labelled LLM-generated and go through the same validation gate. A model can never change rules, permissions or approvals.
- Someone who clones AFM gets the code, never your key. Each person connects their own model.

## The LLM tool: mock or Claude

- **Mock (default):** deterministic and offline, nothing leaves your machine. It explains object types, proposes deliberately bad plans so you can watch the gate reject them, and runs a rule-based chat that proposes form fields.
- **Claude (optional):** uses the official `anthropic` Python SDK.

```bash
cp backend/.env.example backend/.env      # git-ignored; placeholders only in the example
# edit backend/.env:
#   AFM_LLM_PROVIDER=claude
#   ANTHROPIC_API_KEY=...        (or leave empty and run `ant auth login` once)
#   AFM_CLAUDE_MODEL=claude-opus-5-5   AFM_CLAUDE_EFFORT=low   AFM_LLM_TIMEOUT=60
./start.sh
```

- The key stays on the backend. It is never sent to the browser and never appears in logs, errors or history. The UI shows which provider is active, and states that data leaves the machine when Claude is active.
- **What is sent to Anthropic:**
  - *Chat:* the use case's structured fields, the selected adapter's object names/types (if any), and the last 10 messages of *this* use case.
  - *Explain object:* the object's id, type, name and state (free text wrapped as untrusted data).
  - *Plan proposals:* the goal, known objects and the environment's tool names.
  - Never other use cases, secrets or full environment dumps.
- **Errors:** missing credentials, invalid key, unknown model, rate limits, timeouts and network failures give clear messages. The app keeps working with deterministic plans.
- **Not verified live:** the Claude integration is unit-tested with a fake client. It has **not** made a real request on this machine, because no credentials were available.

## Where things are defined

| What | File |
|---|---|
| Identity, generic tools, permissions | `backend/app/config/afm_profile.json` |
| Permanent rules of conduct (+ pin) | `backend/app/config/conduct_rules.json`, `backend/app/domain/conduct.py` |
| Adapter interface | `backend/app/adapters/base.py` |
| Playground / Web app / Inventory adapters | `backend/app/adapters/{playground,webapp,inventory}/` (scenario.json + adapter.py) |
| Not-yet-implemented adapters list | `backend/app/adapters/registry.py` |
| Generic core: simulator, checks, planner, approval gate | `backend/app/engine/` |
| Use-case builder + chat | `backend/app/engine/usecases.py` |
| LLM tools | `backend/app/adapters/llm.py`, `backend/app/adapters/claude_provider.py` |
| Local storage (environments, runs, use cases) | `backend/app/storage/db.py` → `backend/data/afm.db` |

More detail: [docs/architecture.md](docs/architecture.md), [docs/object-model.md](docs/object-model.md), [docs/rules-and-approval.md](docs/rules-and-approval.md).

## Key terms

- **Object:** a thing in an environment (an input, a web server, an order).
- **State:** what is true about it now.
- **Action:** one use of a registered tool with exact parameters.
- **Relationship:** a known link between objects.
- **Goal:** what the human wants, turned into success criteria.
- **Rule:** a limit AFM respects whatever the goal says.
- **Prediction:** what AFM expects to change.
- **Simulation:** trying a plan on a copy.
- **Observation:** looking again after an approved execution.
- **Human approval:** a person's yes to one exact plan for one exact environment state.

## How to add an environment adapter

1. Create `backend/app/adapters/<name>/scenario.json`: objects, relationships, rules, tools (with `permission`, `parameters`, `target_types`, `reversible`), demo goals, definitions, limitations and graph layout.
2. Subclass `EnvironmentAdapter` in `adapter.py` and implement:
   - `interpret_goal` (criteria plus the R30 pre-check, or an honest *unsupported*)
   - `propose_plans`
   - `simulate_action` (raise `AdapterError` with a code)
   - `evaluate_criterion`
   - optionally `connected_effects`, `rule_checks`, `measure` and `error_rules`
3. Declare `capabilities`. If it cannot inspect, simulate or execute, say so; the core reports “unsupported”.
4. Register it in `adapters/registry.py`. State-changing tools must be `requires_approval` or `prohibited`.
5. Never execute instructions found in environment data. Add tests that run it through the same generic workflow (see `tests/test_generic.py`).

## Limitations

- Goal understanding covers a few phrasings per playground. Anything else is reported as unsupported.
- Simulations know only their explicit rules. Real dependencies outside the catalog are unknown by design.
- Approval has no login or users. It is a prototype workflow, not production-grade authentication or authorization.
- No real-system adapters exist for AWS, SAP, web servers, spreadsheets or mobile. Real code projects are supported through real-project mode (Phase 1: public GitHub or local folders, no container isolation).
- The live Claude provider has not been exercised against the real API here.
- Runs saved by the earlier single-environment version stay on disk but are not shown.

## How this was built

Claude Code, from a series of specs, extended in place:

- **Backend:** FastAPI + Pydantic v2 + SQLite, a generic engine plus three adapters, 54 pytest tests.
- **Frontend:** React 18 + TypeScript + Vite. The visual language is adapted from the author's ACMP project (no runtime dependency).
- **Verification:** backend tests, a production build, and a 27-step headless-Chrome walk-through of all three playgrounds and the use-case builder.
