# <img src="docs/logo.png" alt="Butterfly logo" height="64" align="absmiddle"> The Butterfly Model (ACM)

**1 actor · 1 action = consequences in cascade.**

LLMs predict the next word. ACM predicts what an action **changes**: for whom, in which world, how far.

<p align="center">
  <img src="docs/world-layers.svg" alt="1 actor, 1 action = consequences in cascade: the action is parsed by MLM into Phrase DNA; routing reads its WHERE; consequences spread through eight worlds, from atomic to earth, each with its own laws" width="820">
</p>

## The idea

1. **One actor does one action.** Text, image, video or audio → [MLM](https://github.com/Sherlock2019/NPLM-Next-Phrase-language-model-) turns it into meaning: who · does what · to whom · where · why.
2. **The WHERE picks the world.** Throw a ball in the park → physical. Post on Facebook → digital. Buy at a shop → economy. Vote → society.
3. **Each world has its own laws.** Atomic, physical, perception, behaviour, digital, business, society & economy, earth.
4. **Consequences cascade** world by world, and other actors react: their goals advance or get blocked.
5. **Compare with what the actor wanted.** Then decide.

When the actor is "I", it's an AI checking its own action before taking it.

[![The radar: the origin actor at the centre, other actors reacting, the impact spreading through the eight worlds](docs/acm-vision.svg)](docs/acm-vision.svg)

## Why not just an LLM

> *Mark wants John's car. John sold it to Sarah.* **What happens to Mark?**
>
> **LLM:** "Mark buys a car." · **ACM:** Mark's goal is **BLOCKED** — one car, one owner, and Sarah has it.

LLMs guess. ACM shows the rule, the evidence, and says "unknown" when it doesn't know. Same input, same answer.

## Try it

```bash
git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git SLM
git clone git@github.com:Sherlock2019/ACM.git && cd ACM
./start.sh        # → http://127.0.0.1:3010
```

- `/acm/scenario` — 8 scenes: a car sale, an iPhone gift, a beach photo, a broken window, a protest, an EV, a layoff, a lottery win
- `/acm/scene` — physics lab: push a cup, watch the consequences cascade
- `/acm` — any sentence, its full blast radius
- `acm predict "I will sell my car to Sarah."` — same from the command line

## Status

| Built | Next |
|---|---|
| Meaning (MLM), state changes, other actors' goals, 8 scenes, routing, rule packs, graph memory, 2D physics lab | Unreal Engine 5 physics, real vision (Qwen3-VL, YOLO), routing by WHERE, worlds passing consequences to each other, real economic and earth models |

Most worlds are rules today, not models. Everything not built is labelled as such.

## Rules

- No rule matched ≠ no impact.
- Fact, guess and simulation never mix.
- Unknown is said out loud.

---

`pytest` — 106 tests, no GPU. · Add knowledge in YAML (`packs/`, `scenes/`), no retraining. · Details: [docs/](docs/).

© 2026 Dzoan Nguyen Tran · [MIT](LICENSE)
