# <img src="docs/logo.png" alt="Butterfly logo" height="64" align="absmiddle"> The Butterfly Model (ACM)

**⚡ 30-second version** · [📖 3-minute full version →](README_FULL.md)

**1 actor · 1 action = consequences in cascade.**

## The problem

AI is starting to act in the world, but language models only predict the next word. They don't
track what an action **changes**, can't show why they say what they say, and never say "I don't
know".

> *Mark wants John's car. John sold it to Sarah.* **What happens to Mark?**
> A language model: "Mark buys a car." Wrong, and it can't tell.

## The solution

ACM predicts the consequences of an action before it is taken.

1. **One actor does one action:** in text, an image, a video or audio. [MLM](https://github.com/Sherlock2019/NPLM-Next-Phrase-language-model-) turns it into meaning: who · does what · to whom · where · why.
2. **The WHERE picks the world:** a ball in the park is physical, a Facebook post is digital, a purchase is economy, a vote is society.
3. **Each world has its own laws:** atomic, physical, perception, behaviour, digital, business, society & economy, earth.
4. **Consequences cascade** world by world, and other actors react: their goals advance or get blocked.
5. **Compare with what the actor wanted**, then decide.

<p align="center">
  <img src="docs/world-layers.svg" alt="1 actor, 1 action = consequences in cascade: the action is parsed by MLM into Phrase DNA; routing reads its WHERE; consequences spread through eight worlds, from atomic to earth, each with its own laws" width="820">
</p>

[![The radar: the origin actor at the centre, other actors reacting, the impact spreading through the eight worlds](docs/acm-vision.svg)](docs/acm-vision.svg)

## So what: all AI models working as one

Today AI is fragmented. Language models handle words, vision models images, physics engines
motion, behaviour models people, economic models markets, climate models the planet. **Each sees
one slice. None sees the whole consequence of a single action.**

The Butterfly Model connects them into **one system**. MLM gives every model the same meaning of
the action, routing sends it to the right worlds, and in each world the best specialist model
predicts by that world's laws. Their answers come back into one picture.

**1. Holistic prediction across interconnected worlds.** One action → its consequences in every
world at once (physical, human, digital, financial, social, planetary) **and how each world's
effects trigger the next**: the cup falls → the crash is heard → the owner is upset → a claim is
filed → glass is replaced. No single model sees that chain.

| Benefit | What it gives you |
|---|---|
| **Second- and third-order effects** | the ripples behind the obvious result, where the real cost often is |
| **Every actor counted** | each person's goal checked (advanced, blocked, at risk) and their reaction predicted |
| **What-if before acting** | compare alternative actions against the desired outcome, before anything happens |
| **Any input** | text, image, video or audio reach the same meaning |
| **The best model per world, as one system** | physics engine, vision model, behaviour model, economic model, climate model, all connected |
| **Plug and play** | upgrade one world's model without retraining the others; rules stand in until a model exists |
| **Explainable and repeatable** | every consequence says which world, which model or rule, which evidence; same input, same answer |
| **Safer AI agents** | an agent sees the full consequences of its own action before taking it |
| **Better human decisions** | people, companies and governments see what a choice changes, for whom, how far |

**The savings:**

| Saved | How |
|---|---|
| **Tokens** | predicts in phrases (Phrase DNA), not token by token; the LLM only words the final answer |
| **Compute and cost** | routing runs only the models of the worlds an action touches, not every model every time |
| **Context** | a compact, relevant context (worlds, actors, goals, state, evidence) instead of the whole history |
| **Retraining** | new knowledge is a YAML edit or one world's model, not a new giant model |
| **Costly mistakes** | harmful consequences are caught before the action, not after |
| **Agent setup** | routing doubles as the harness config: which models and tools to call, with which context |

*Token, compute and cost savings follow from the design and are not yet benchmarked.*

```bash
git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git SLM
git clone git@github.com:Sherlock2019/ACM.git && cd ACM && ./start.sh   # → http://127.0.0.1:3010
```

## What next: build it with us

Built today: the shared meaning (MLM), routing, state changes, other actors' goals, a
**Scenario Engine** for human reactions (to be trained on movie scripts and psychology), and a
2D physics lab, with rules standing in for most worlds' models. Connecting the real specialist
models is the next step, and everything not built yet is labelled.

To finish it, we need **top AI talent**: physics simulation (Unreal Engine 5), computer vision,
world models, agents, and economic and earth modelling. Each world needs a real model behind it.

**Let's work together:**
- Profile and projects: **[dzoannguyentran.jobsmatchnow.com](https://dzoannguyentran.jobsmatchnow.com/#projects)**
- WhatsApp: **[+84 908 618 075](https://wa.me/84908618075)**

© 2026 Dzoan Nguyen Tran · [MIT](LICENSE)
