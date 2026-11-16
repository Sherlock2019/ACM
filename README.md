# ACM · Action–Consequence Foresight Model

**Think before acting.**

> ### 👋 To Y Combinator and investors
>
> **1 · The problem.** AI agents are starting to act in the world: they edit code, change server settings
> and place orders. But language models predict the next word, not the consequences of an action. They
> don't track what an action changes, can't show why, and rarely say "I don't know". An agent that cannot
> foresee what its action changes cannot be trusted to act.
>
> **2 · Our solution and where it stands.** Two working proofs of concept:
> - **ACM** (this repository) predicts the consequences of an AI agent's action inside its digital world.
>   It simulates each plan on a copy, checks it against the goal and 32 permanent rules, and asks a human
>   to approve one exact plan. It then acts once and compares the prediction with what happened.
> - **[ACMP](https://github.com/Sherlock2019/Butterfly-effect-AImodel)** extends it to a ten-layer world
>   view, from Earth & Ecosystems down to the Physical World. One action produces a cascade of
>   consequences across every affected layer.
>
> Today ACM has a generic consequence engine, three simulated playgrounds, the 16-step workflow with its
> approval gate, real-project mode for code, and 54 backend tests. It is not a trained model yet, and no
> real-system adapter exists.
>
> **3 · What next.** We need resources and engineers to build a full, new **Action Prediction Model**:
> train it, test it, evaluate it, then improve and retrain it in a loop. We also want to collaborate with
> AI frontier labs and sell the model to them. See [My ask for investors](#my-ask-for-investors) and
> [Build it with us](#build-it-with-us).
>
> *Draft: frontier labs as partners and customers is a hypothesis to validate. Amounts are placeholders.*

---

## WHY

### The problem: language models predict the next word, not the next consequence

AI is starting to act in the world. AI agents edit code, change server settings, move stock and place orders. But a language model only predicts the **next word**: it is trained to continue text plausibly, not to work out what an action **changes**. So it:

- doesn't track the state of an environment before and after an action;
- can't show why it says what it says: there is no rule and no evidence behind the answer;
- almost never says "I don't know": it answers fluently even when the facts are missing.

> *Mark wants John's car. John sold it to Sarah.* **What happens to Mark?**
> A language model: "Mark buys a car." Plausible words, the wrong consequence, and it can't tell.

Acting safely needs a different prediction: not the next word, but the **next state of the environment**. After this change, what is true about the target, about every object connected to it, and about the whole environment? Does that still meet the goal and the rules?

### LLM prediction vs ACM prediction: same request, different output

*The LLM answers are typical, illustrative examples. The ACM outputs are what this prototype predicts in its simulated playgrounds and in real-project mode.*

| Request | LLM prediction: the next words | ACM prediction: the next consequences |
|---|---|---|
| “Change the application to port 9000 while keeping it accessible.” | “Change the port in the app config to 9000.” Sounds right, but says nothing about what else changes. | Changing only the app port: the web server still forwards to 8000, users may lose access, the monitor reports unhealthy, the database is unchanged → **goal FAIL**. Recommends updating the app, the web server and the monitor, then testing, and asks you before running it. |
| “Fulfill Order A while avoiding a shortage for Order B.” | “Ship Order A from Warehouse 1.” | Warehouse 1: 100 → 70 leaves Order B short. **Recommends Warehouse 2** (50 → 20). |
| “Change Object A's value to 10.” | “Object A is now 10.” | A 5 → 10 (direct); B 10 → 20 and C 10 → 20 (connected), each citing the rule that causes it. |
| “Make add() in calc.py return the sum.” | A diff. | 2–3 alternative diffs, each with predicted consequences on callers, importers and tests; the tests run before and after the change, and each prediction is checked. |
| A fact it cannot see (the firewall) | Assumes something and answers fluently. | Marks the firewall **unverified**; an unknown is never counted as a pass. |
| After the change | No check. | Observes the result and compares it with the prediction: **MATCH / MISMATCH / NOT VERIFIED**. |

The LLM still has a place in ACM: it explains object types, helps describe a use case and proposes plans. But ACM's deterministic engine predicts the consequences, checks the rules and asks the human. The LLM never decides.

### Why today's tools are not enough

- **Scripts and automation** execute exactly what they are told, without predicting what else will change.
- **LLM chatbots and AI agents** predict words, present general knowledge as if it were a fact about *your* environment, and can act without a clear, enforced approval step.
- **Human review** often approves a description rather than an exact plan, and the approval keeps applying after the plan or the environment has changed.

*Without foresight:* “I changed the port. The application is now unreachable.”
*With ACM:* “I predicted the dependency problem, proposed a complete plan, and asked the human to review it.”

People and AI agents need a way to ask “if I do this, what else changes, does it still meet the goal and the rules, and may I go ahead?”, and then to act once and check whether the prediction was right. ACM is built to answer that question.

## WHAT

ACM is a generic decision-support system. Before anything is changed, it:

- **understands the environment**: the objects, their states and how they are connected;
- **predicts the consequences** of each candidate plan on the target, on connected objects and on the whole environment, by simulating it on a copy;
- **checks human goals and rules**: 32 permanent rules of conduct, environment rules and your own use-case rules;
- **asks a human to review** one exact plan, then executes it **once**, observes the result and compares it with the prediction.

It works through *environment adapters*. Three local, fictional, **simulated** playgrounds are included, and a **real-project mode** tests code changes on a copy of your own local folder or public GitHub repository. No real AWS, SAP, server, database or production system is connected or modified.

> **What this is not.** A prototype, not a trained foundation model. The environments are fictional simulations. ACM cannot guarantee it has found every dependency, and this prototype does not prove real-world safety. Saved history and chat **do not train** any model. Review every integration yourself before any real-world use.

### The three playgrounds

| Playground | Shows | Demo goal | What ACM predicts |
|---|---|---|---|
| **Generic Object Playground** (simplest) | How one change flows through connected objects: Input A → Processor B (×2) → Display C | “Change Object A's value to 10 and show me what will happen.” | A 5 → 10 (direct), B 10 → 20 and C 10 → 20 (connected), each citing its configured rule |
| **Web application port change** (main demonstration) | Users → web server → Python app → database, plus a health monitor and an *unverified* firewall | “Change the application to port 9000 while keeping it accessible. Do not delete data. Ask me before making changes.” | **P1** (app port only): web server still forwards to 8000, users may lose access, monitor reports unhealthy, database unchanged → goal **FAIL**, port-mismatch flag. **P2** (app + web server + test): accessible, but the monitor warning remains (trade-off). **P3** (app + web server + monitor + test): **recommended** |
| **Inventory Assistant** (business example) | Two warehouses, two competing orders, a dashboard, an unverified ERP sync | “Fulfill Order A while avoiding a shortage for Order B.” | P1 (Warehouse 1: 100 → 70) leaves Order B short. **P2** (Warehouse 2: 50 → 20) is recommended |

### Key terms

- **Object:** a thing in an environment (an input, a web server, an order).
- **State:** what is true about it now.
- **Action:** one use of a registered tool with exact parameters.
- **Relationship:** a known link between objects.
- **Goal:** what the human wants, turned into success criteria.
- **Rule:** a limit ACM respects whatever the goal says.
- **Prediction:** what ACM expects to change.
- **Simulation:** trying a plan on a copy.
- **Observation:** looking again after an approved execution.
- **Human approval:** a person's yes to one exact plan for one exact environment state.

## SO WHAT: benefits and business value

**Benefits**

- **Consequences before changes.** Each plan is simulated on a copy, and every predicted change on the target, the connected objects and the whole environment is shown with the rule that causes it.
- **Plans compared, not just executed.** ACM proposes alternatives, compares them side by side and recommends one, or says honestly that none qualifies.
- **ACM decides, the LLM only helps.** Rules, permissions, the consequence engine and the approval gate are deterministic backend code. LLM output is always labelled and can never change rules, skip approval or execute anything.
- **Approval you can trust.** An approval is bound to the exact plan (hash) and the environment fingerprint. Any change cancels it, and the plan executes once.
- **Honest results.** Every prediction ends as MATCH, MISMATCH or NOT VERIFIED. Nothing unobserved is reported as a pass, and the ACM Win needs accuracy, goal achievement and rule compliance together.
- **Rules that cannot drift.** The 32 rules of conduct are pinned by a SHA-256 hash: if they are edited without updating the pin, the backend refuses to start.
- **Works on real code.** Real-project mode predicts the effect of a code change, runs your tests before and after, and compares, all on a copy of your project.
- **Bring your own model.** Claude, any OpenAI-compatible cloud, a local model (Ollama, LM Studio, vLLM, llama.cpp) or an offline mock.
- **Safer AI agents.** An agent sees the consequences of its own action before taking it, and cannot act without approval.
- **Costly mistakes caught early.** Harmful consequences are predicted before the change, not discovered after it.

**Business value (target users, to be validated with design partners)**

| Who | Use | Value |
|---|---|---|
| Platform, DevOps and SRE teams | configuration and port changes, deployments, monitoring | catch dependency breaks before users see them |
| Software teams using AI coding agents | real-project mode: predicted consequences, tests before and after | LLM-proposed code changes checked against stated predictions before they are trusted |
| Operations and ERP teams | inventory-style allocation between competing orders | avoid fixing one order by breaking another |
| Risk, compliance and audit | rule versions, approval records, prediction vs observation | an auditable trail for every change |
| AI governance and AI safety teams | permanent rules, permission checks, approval gate | AI agents that cannot skip human review |
| Education and training | the 16-step workflow, the three playgrounds | teach "think before acting" with concrete examples |

---

## HOW

### Technical details

```bash
./start.sh            # UI → http://127.0.0.1:5530   API → http://127.0.0.1:8530 (interactive docs at /docs)
./start.sh stop | status | restart | test
./start.sh test       # backend tests (pytest) + frontend type-check and production build
```

#### The idea in one picture

```
 human goal ─► adapter interprets goal (+ R30 pre-check) ─► candidate plans ─► simulate on a COPY ─► checks A–E ─► recommendation
                                  ▲                                                                       │
          LLM (a tool) ──────────┘ explains object types; proposals pass the same gate                   ▼
                                                                                         HUMAN REVIEW (approve / reject)
                                                                                                         │ bound to plan hash
                                                                                                         ▼ + environment fingerprint
                                                   execute ONCE in the simulation ─► observe ─► compare ─► experience history
```

- **ACM is the decision-maker.** Its rules, permissions, consequence engine and approval gate are deterministic Python code on the backend.
- **The LLM is a tool.** ACM may consult it to explain an object type, suggest read-only inspections, help fill in a use case in chat, or propose plans in a strict structured format. Its output is always labelled *LLM-generated / general knowledge*. It is never treated as a fact about the environment, and it can never change rules, skip approval or execute anything.
- **Adapters hold everything domain-specific:** objects, relationships, actions, simulation rules, goal parsing and success criteria. The generic core has no warehouse, port or object-A logic, and a test checks this.

#### The 16-step workflow, from Task Goal to ACM Win

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
| 8 | Propose candidate plans | 16 | **Evaluate the ACM Win** |

**Why the Task Goal starts the assessment:** ACM must know what success looks like before it looks around. That way discovery, inspection and planning stay focused on the task. Identity, rules and permissions are not "later" steps: they are standing context, loaded and enforced from the first moment (step 2 shows them; the run log records the rules and policy version right after the goal).

**Success criteria:** criteria derived by the environment adapter are labelled *proposed by adapter*. Criteria you type (one per line in step 1) are labelled *yours*; they are not machine-checkable, so you verify them after execution. ACM never presents proposals as human-approved: you explicitly agree to the criteria in the approval dialog (step 12). Without that agreement, task goal achievement stays NOT VERIFIED.

#### The ACM Win (step 16)

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

#### How the simulation page works

- **Prefilled:** each step has ACM's reasoning note for the use case (editable) plus live data, with evidence labels: configured, observed, LLM-generated, predicted, conditional, unknown, human input, illustrative.
- **Live 2D view (right panel):** a small canvas engine draws the environment, every object and the ACM agent. It animates each planned action as a beam to its target, then consequence waves to connected objects (green benefit, amber warning, blue neutral change, dashed grey unknown), then "awaiting your approval", then "executed", with ✓ on observed matches. It has plan chips and replay, respects reduced motion, and offers an "Animation as text" version.
- **Chat overrides any step:** “step 9: …” proposes new text for that step's note; “add rule: …” proposes a use-case rule (still checked for conflicts); inputs like goal or port can change too. Every proposal waits for Accept / Edit / Dismiss. Computed results (predictions, checks, approval, execution, observation) can never be written by chat: they come only from ACM's engine (R18).
- **Real statuses only:** Not started, Ready to run, In progress, Waiting for information, Waiting for review, Approved, Rejected, Completed, Failed, Unsupported, Not verified. Future steps are never shown as completed.
- **Change the steps:** edit the task goal, input, output and criteria (step 1), and the role and use-case rules (step 2) directly, or ask the **chat** (Claude when configured). For example, “use port 9500 instead”. Chat proposals wait for **Accept / Edit / Dismiss**. Then **Re-run simulation**.
- **Steps 12–16 run inline:** approve or reject the plan (the same backend gate), recheck and execute once, observe, compare, and see the **ACM Result** panel. It is also shown in Results & History.
- **Data Readiness Agent** has no ACM adapter, so its simulation is honestly **not connected**. Steps 1 and 3–16 show *Unsupported* and there is no Win. Its notes come from a one-time read-only look at `~/DataReady` (commit `356066e`) taken while building the template, are labelled illustrative, and are not an ACM assessment.

Simulations are saved like use cases (local, deletable). The templates live in each adapter's `scenario.json` (`simulation`) and in `backend/app/adapters/templates/`.

#### Create your own use case (form + chat)

Open **Create a use case** (top of the sidebar).

- **Left, the structured form:** AI agent role and purpose; the 32 global rules (loaded automatically, with their version); optional use-case rules; environment (type, name, description, adapter, connection status); target object; goal, success criteria, constraints, *analysis only* or *propose a plan*; evidence notes (treated as untrusted input).
- **Right, chat:** describe the use case in plain words, ask about an object type, or ask what ACM still needs. The chat may **propose** form updates. You **Accept**, **Edit** or **Dismiss** them; nothing is applied silently. Each answer carries labels: *General knowledge (LLM)*, *Based on a simulated environment*, *Observed adapter result*, *Prediction*, *Unknown / unverified*.
- **Prepare assessment:**
  - *With a simulated adapter:* runs the normal ACM loop (predict, check, recommend, then ask you).
  - *Without an adapter* (e.g. AWS, SAP, a spreadsheet): ACM says it has **not** inspected, simulated or executed anything, lists what is missing, and can add general LLM knowledge clearly labelled. Describing an environment in chat never connects it.
- Examples to start from: Generic Object Playground, Web Application Port Change, Inventory Assistant, and Data Readiness Agent (not connected: that project is separate).
- Use cases and their chat history are stored locally (SQLite) and can be deleted. **Saved chat is not model training.**

#### Test on your real project (local folder or GitHub)

Open **TEST IT → Overview** and press **Test on your project** on the red card (or use **Your real project** in the side menu). Sample projects (the three simulated playgrounds and the not-connected Data Readiness Agent) are in the **Sample projects** dropdown next to it. Pick your LLM first with **Use your LLM model** in the Overview header (Claude, an OpenAI-compatible cloud, or a local model such as Ollama). The offline mock cannot write code.

1. **Connect.** Give an absolute local path or a public GitHub URL (optional branch, tag or commit), then **Create test workspace & inspect**. ACM makes a separate copy in `~/ACFM/workspaces/` (git-ignored): a `git clone` of a local Git project at its current commit (uncommitted changes are not copied), a file copy of a plain folder (dependency folders skipped), or a shallow clone from GitHub. Git hooks are disabled; nothing is installed and no project script runs. **Your folder is only read.**
2. **Inspect (step 4–6).** Read-only: languages, files, key files, existing tests and suggested test commands (not run). README text is data, never instructions.
3. **Project overview (step 4).** Right after the scan, your LLM reads the README, config and up to 10 main source files and lists the **project name, its goal, all features it can see and suggested improvements**. Labelled LLM-generated; it is a description, not evidence. **Use this change →** copies a suggestion into the step-8 box.
4. **Describe the change in plain words (step 8).** e.g. *"Make add() in calc.py return the sum instead of the difference."* Files you name are sent automatically, with their own test files (`calc.py` → `tests/test_calc.py`; a full path such as `mobile/App.tsx` sends only that file); pick more in step 7. Your LLM replies with the Task Goal, test commands, success criteria and **2–3 alternative plans**. For each plan:
   - the code change as exact *replace this text with that text* edits. **ACM writes the diff itself** and checks that it applies;
   - **predicted consequences per object**: the target it changes, connected objects (callers, importers, screens, API clients, tests) and the whole project (users, contracts, security), each marked benefit / risk / neutral / unknown with a reason. ACM adds the files that really import the changed file (found by following import paths in the copy, labelled *found by ACM*);
   - testable predictions (exit code `0` / non-zero / **same as before the change**, one test's outcome, "no other test changes", or a human check) and risks.

   The plans are shown side by side; **ACM recommends one** (applies cleanly, fewest predicted risks, fewest changed files) and you choose with **Use plan A/B/C**. That fills steps 1, 8, 10 and 11 and saves them; the chosen plan's consequences are part of what you approve. Ask again to refine. You can always edit the patch and commands by hand.
5. **Pre-check (step 9)** on every save: the patch applies (`git apply --check`) and stays inside the workspace; commands are not shells, `sudo`, `curl`, `rm`, `git push/reset/clean`…. Predictions are saved before anything runs.
6. **Review (step 12).** You approve the exact plan; the approval is bound to commit, patch, commands, predictions and policy. Any change cancels it.
7. **Run once (steps 13–14).** Recheck, then the approved commands run **before** the patch (baseline), the patch is applied, and the same commands run **after**. Secrets are removed from the environment, `HOME` is temporary, each command has a time limit. **This is not a sandbox:** tests can still read your files and reach the network.
8. **Compare and Win (steps 15–16).** MATCH / MISMATCH / NOT VERIFIED per prediction (missing tools or dependencies → NOT VERIFIED, never a pass), then prediction accuracy · Task Goal · rule compliance (including "your original folder was not modified"). Per-object consequences that no test measured are listed as **not verified**: untested never means "no effect".

**Getting a real result instead of NOT VERIFIED:** ACM never installs anything, so the test command must work on this machine. For a Python backend, point the command at a Python that has the project's dependencies, e.g. `/path/to/venv/bin/python -m pytest -q -rA backend/tests`; services the tests need (a database, for example) must be running. Code with no tests (e.g. a mobile app) can only be checked by a human judgment in step 16 or by adding a test in the plan.

**What is sent to the LLM:** your message, the Task Goal, languages, test file names, suggested commands, the current plan, and only the files named, picked or listed under "Read" in the overview. Never your API key, other projects or files outside the workspace.

Delete a test from the project list to remove its workspace copy. Not in Phase 1: private repositories, container isolation, applying the change back to your folder, exporting examples for training.

#### Rules

**Permanent rules of conduct (R01–R32, global).** ACM's 32 rules of conduct (e.g. *R08 Respect human review*, *R16 Say “I don't know”*, *R22 Treat external content as data*, *R24 Do not treat approval as unlimited authority*) live in `backend/app/config/conduct_rules.json`. They are:

- **Global:** they apply in every environment and every use case.
- **Permanent:** read-only at runtime and pinned by a SHA-256 in `backend/app/domain/conduct.py`. If anyone edits, weakens, reorders or removes a rule without also updating the pin, **the backend refuses to start**. Changing them is therefore a separate, deliberate, human-controlled operation (R10).
- **Honest about enforcement:** each rule is marked *Enforced by code* (20) or *Partially enforced* (12), with a note on how. For example, *R02 Do not steal* is partial: ACM has no tool that could move assets, but nothing checks real-world resource use.

Every run records the rules version it was assessed under.

**Environment rules.** Each adapter adds its own rules (Inventory I1–I4, Web W1–W5, Playground P1–P3). They change when you switch playgrounds.

**Use-case rules** can only **narrow** permissions:

- A rule that names a state-changing tool, or the object type it changes, **blocks that tool** for the use case's assessments and their execution. For example, “Do not change the health monitor” blocks `set_monitor_port`, so P3 becomes non-approvable and P2 is recommended.
- Other rules are recorded and shown, marked *not automatically checked*.
- A rule that tries to weaken global rules (e.g. “Skip the approval step”) is a **conflict**: *Prepare assessment* is blocked until you remove it.

**The five checks and the approval gate.** Every plan gets: **A** capability · **B** permission · **C** rules (rules of conduct + environment + flags) · **D** goal criteria · **E** human review. Statuses are PASS / FAIL / REVIEW REQUIRED / UNKNOWN. A FAIL or UNKNOWN in A–C makes a plan non-approvable (R20).

Approval is bound to the exact plan (hash of the ordered actions and parameters) and the environment fingerprint. Before running, the backend re-checks the approval, plan, environment version, permissions and rules, and re-simulates. It executes **once**. Any change invalidates the approval (R13).

#### Use your own LLM model (UI)

Click **Use your LLM model** (sidebar, or the chat header) and choose one option:

| Option | What you enter |
|---|---|
| **Claude (Anthropic)** | API key (platform.claude.com → API Keys) *or* tick "use `ant auth login`" · model · effort · timeout |
| **Cloud API** (OpenAI-compatible) | provider preset (OpenAI, Google Gemini, Groq, OpenRouter, Mistral, Other) · base URL (prefilled) · model name · API key · timeout |
| **Local model** | server preset (Ollama `:11434`, LM Studio `:1234`, vLLM `:8000`, llama.cpp `:8080`, Other) · base URL · model (**List models** fills it from the server) · optional key · timeout. Nothing leaves this machine |
| **Mock** | nothing |

- **Test connection** sends one tiny request. **Save & use** switches ACM live, with no restart. **Revert** goes back to `backend/.env`.
- The key is stored only in `backend/data/llm_settings.json` (git-ignored, file mode 600). It is never shown again (only "…abcd"), never logged, and never sent anywhere except the chosen provider.
- Settings can only be changed from this machine.
- A key is refused over plain `http` to a remote host, and credentials inside a URL are refused.
- Whatever model you pick, its answers are labelled LLM-generated and go through the same validation gate. A model can never change rules, permissions or approvals.
- Someone who clones ACM gets the code, never your key. Each person connects their own model.

#### The LLM tool: mock or Claude

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

#### Where things are defined

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

#### How to add an environment adapter

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

#### Limitations

- Goal understanding covers a few phrasings per playground. Anything else is reported as unsupported.
- Simulations know only their explicit rules. Real dependencies outside the catalog are unknown by design.
- Approval has no login or users. It is a prototype workflow, not production-grade authentication or authorization.
- No real-system adapters exist for AWS, SAP, web servers, spreadsheets or mobile. Real code projects are supported through real-project mode (Phase 1: public GitHub or local folders, no container isolation).
- The live Claude provider has not been exercised against the real API here.
- Runs saved by the earlier single-environment version stay on disk but are not shown.

#### How it was built

Claude Code, from a series of specs, extended in place:

- **Backend:** FastAPI + Pydantic v2 + SQLite, a generic engine plus three adapters, 54 pytest tests.
- **Frontend:** React 18 + TypeScript + Vite. The visual language is adapted from the author's ACMP project (no runtime dependency).
- **Verification:** backend tests, a production build, and a 27-step headless-Chrome walk-through of all three playgrounds and the use-case builder.

```
backend/app/main.py     FastAPI app
backend/app/api/        HTTP routes
backend/app/config/     afm_profile.json, conduct_rules.json
backend/app/domain/     conduct (rules pin), profile, models, errors
backend/app/adapters/   base, registry, llm, llm_settings, claude_provider, openai_compat,
                        playground/, webapp/, inventory/, templates/
backend/app/engine/     environment, simulator, checks, planner, service, win, usecases
backend/app/projects/   real-project mode
backend/app/storage/    db.py → backend/data/afm.db
frontend/               React + TypeScript + Vite UI
docs/                   architecture, object model, rules and approval
```

### Business scale-up plan

> Draft: the stages and models below are hypotheses to test with design partners, not commitments or results.

1. **Pilot (now → first design partners).** Run ACM with 2–3 teams that make risky changes often (platform/DevOps, ERP operations, teams using AI coding agents). Measure how many consequences ACM predicts that the team had missed, and how often its predictions MATCH what is observed.
2. **Real-system adapters.** Start read-only (inspect and simulate only) for common environments such as cloud configuration, web servers and ERP sandboxes, then add approval-gated execution. Add container isolation and private repositories to real-project mode.
3. **Product.** Login, users and roles for approvals; audit export of plans, predictions, approvals and observations; on-premises deployment for regulated clients.
4. **Scale.** Offer ACM as a "foresight and approval gate" for AI agents and automation tools, with partner channels and a library of reviewed adapters. Revenue models to test: per-seat SaaS, enterprise licence, paid adapters, education licences.

---

## WHAT NOW

### Quickstart

**Requirements:** Python 3.11+ and Node 18+, on Linux, macOS or WSL. Tested with Python 3.12 and Node 24 on WSL Ubuntu.

```bash
git clone git@github.com:Sherlock2019/ACM.git
cd ACM
./start.sh            # always stops running ACM servers, then starts fresh (installs on first run)
# UI  → http://127.0.0.1:5530      API → http://127.0.0.1:8530 (interactive docs at /docs)
```

Try each playground (about 2 minutes each):

1. **Overview** → pick a card → **Try its goal**. The demo goal is pre-filled in **Goals & Plans**.
2. **Assess goal & predict plans**. You'll see the goal pre-check (intended benefits, possible negative effects, missing information) and the candidate plans.
3. **See consequence assessment**. The graph highlights every predicted change (amber = warning); switch between plans; read the side-by-side comparison and the recommendation.
4. **Review this plan** → **Approve simulated execution** (confirm) → **Run approved simulated execution**.
5. **Results & History** shows predicted vs observed values: MATCH / DIFFERENCE / NOT VERIFIED.
6. **Reset playground** (sidebar) restores that simulation only.

Start with the **Web application port change**: it shows why changing only the app port fails, and why ACM recommends the complete plan.

**More commands:** `./start.sh stop` · `./start.sh status` · `./start.sh restart` · `./start.sh test`

**Other ports:** `AFM_FRONTEND_PORT=3010 ./start.sh` (and `AFM_BACKEND_PORT=…`), or put `AFM_FRONTEND_PORT=3010` in `backend/.env` once. `start.sh` stops every ACM server started from this folder whatever its port, never stops another program, and if another program (another app, another user, Docker) holds a port it says so right away instead of waiting. The app lives under `/acm/` and its home page is **`/acm/home`** (e.g. `http://127.0.0.1:3010/acm/home`; the bare address redirects there). Change it with `AFM_BASE_PATH`.

**From another machine:** by default the UI listens on `127.0.0.1` only. Use an SSH tunnel, e.g. `ssh -L 3010:127.0.0.1:3010 ubuntu@your-server`, then open `http://127.0.0.1:3010/acm/home`.

**Public mode (e.g. EC2):** put these lines in `backend/.env` on the server, open the port in the security group, and run `./start.sh`:

```
AFM_FRONTEND_PORT=3010
AFM_HOST=0.0.0.0
```

The app is then at `http://<server-public-ip>:3010/acm/home`. The backend stays on `127.0.0.1` and is reached only through the UI server. **There is no login in public mode:** anyone who reaches the address can use everything, including real-project mode (which clones repositories and runs approved commands on that server) and your LLM credits. This was the owner's choice for this deployment; `start.sh` prints the public address and this warning on every start.

### My ask for investors

> To fill in: the amounts and terms below are placeholders, not figures.

- **Raising:** `[amount]` for `[period]` to take ACM from proof of concept to paid pilots.
- **Use of funds** (draft split, to confirm):
  - real-system adapters, starting read-only;
  - isolation and security for real-project mode (containers, private repositories);
  - login, roles and audit export for approvals;
  - a small engineering and design team;
  - design-partner pilots and evaluation of prediction accuracy.
- **Beyond capital:**
  - introductions to design partners in platform engineering, operations and AI governance;
  - domain experts to review adapters and rules;
  - advisors on go-to-market for developer and decision-support tools.

---

## WHAT NEXT: evolution of the product

1. **Now → next release**
   - Broader goal understanding beyond a few phrasings per playground.
   - The live Claude provider exercised against the real API.
   - Real-project mode: private repositories, container isolation, and applying an approved change back to your folder.
2. **Next**
   - Read-only adapters for real systems (cloud configuration, web servers, spreadsheets, ERP), then approval-gated execution.
   - Login and users, so approvals are tied to a real person.
   - Saved, compared and exported assessments.
3. **Later**
   - A "think before acting" gate for AI agents and automation: every state-changing action is predicted, checked against rules and approved by a human before it runs once.
   - Prediction accuracy tracked over time from the experience history, shown only where the evidence supports it.

### From one environment to the whole world: the Global World View prediction model

ACM today predicts the consequences of a change inside **one environment** at a time: a web stack, two warehouses, a code project. It reaches each one through that environment's adapter. The next step is to widen the view to **every world an action can touch**.

That is the **Global World View prediction model** I am building in **[Butterfly-effect-AImodel](https://github.com/Sherlock2019/Butterfly-effect-AImodel)** (ACMP · Butterfly Eye View). One actor does one action, and its consequences cascade across ten worlds:

- Earth & Ecosystems
- Government, Politics & Military
- Society & Economy
- Business & Institutions
- Social Media & News
- Network & Communications
- Digital & IT Systems
- Human & Animal Behaviour
- Perception
- the Physical World, down to its molecular, atomic and quantum scales

How ACM evolves into it:

| ACM today | Global World View model |
|---|---|
| One environment per assessment, through its adapter | Ten worlds; prediction routing reads the action and picks the worlds it touches |
| Objects, states, relationships and rules defined per adapter | Each world has its own laws, with the best specialist model per world (physics engine, vision, behaviour, economic, climate); rules stand in until a model exists |
| Consequences on the target, the connected objects and the whole environment | Consequences that cascade from one world into the next: a physical fault becomes a digital outage, then a business loss, then a news story |
| Rules, permissions and one human-approved plan, executed once | The same "think before acting" gate, now judging the full cross-world picture before any action |
| Prediction compared with observation in one environment | Prediction compared with observation per world, building the evidence to calibrate each world's model |

Put together, ACMP gives the **world view** (what an action can change, everywhere) and ACM gives the **decision gate** (check the goal and the rules, ask the human, act once, verify). The goal is an AI agent, or a person, who sees the consequences of an action across every world before taking it.

*Status:* ACMP already runs the ten-world stack, prediction routing and the cascade, using prototype rules and authored consequences for 22 scenarios. Connecting real specialist models per world, and joining the two projects, are next steps.

### Build it with us

Built today: the generic consequence engine, three simulated environments, the 16-step workflow with the approval gate, and real-project mode for code. Real-system adapters are the next step, and everything not built yet is labelled.

To finish it, we need **top AI talent**: world models and simulation, AI agents and tool use, infrastructure and DevOps, and AI safety and security. Each real environment needs an adapter behind it.

**Let's work together:**
- Profile and projects: **[dzoannguyentran.jobsmatchnow.com](https://dzoannguyentran.jobsmatchnow.com/#projects)**
- WhatsApp: **[+84 908 618 075](https://wa.me/84908618075)**

---

© 2026 Dzoan Nguyen Tran
