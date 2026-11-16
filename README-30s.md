# ACM · Action–Consequence Foresight Model, in 30 seconds

**Think before acting.** · [Full README](README.md)

**WHY.** AI agents edit code, change servers and place orders, but language models predict the next word,
not the next state of the environment.

| Request | LLM prediction | ACM prediction |
|---|---|---|
| “Change the app to port 9000, keep it accessible.” | “Change the port in the app config.” | App port only: the web server still forwards to 8000 and users lose access → **goal FAIL**. ACM recommends changing the app, web server and monitor, and asks you first |
| After the change | No check | Prediction vs observation: MATCH / MISMATCH / NOT VERIFIED |

**WHAT.** A decision gate for AI agents in their digital world. ACM simulates each plan on a copy and checks
it against the goal and 32 permanent rules. A human approves one exact plan, ACM executes it once, then
verifies the result. It includes three simulated playgrounds and a real-project mode for code. It is not a
trained model, and it has no real-system adapters yet.
[ACMP](https://github.com/Sherlock2019/Butterfly-effect-AImodel) extends it to a ten-layer world view.

**SO WHAT.** Costly mistakes are caught before the change. Each approval is bound to the exact plan. The LLM
helps but never decides. Built for DevOps/SRE, teams using AI coding agents, and AI governance
*(target users still to be validated)*.

**HOW.** A FastAPI + SQLite engine with environment adapters, a React UI and a 16-step workflow. Bring your
own LLM (Claude, OpenAI-compatible, local or mock). 54 backend tests.

**WHAT NOW.**
```bash
git clone git@github.com:Sherlock2019/ACM.git && cd ACM
./start.sh   # → http://127.0.0.1:5530
```
Try the **Web application port change**. Investors: [the ask](README.md#my-ask-for-investors) *(amounts are placeholders)*.

**WHAT NEXT.** Build a full **Action Prediction Model**: train it, test it, evaluate it, then improve and
retrain it. Collaborate with AI frontier labs and sell to them. We need engineers:
[profile](https://dzoannguyentran.jobsmatchnow.com/#projects) · [WhatsApp](https://wa.me/84908618075)

---

**Made with love by [DzoanNguyentran@gmail.com](mailto:DzoanNguyentran@gmail.com) · A better World Builder**
