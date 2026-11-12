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

| Benefit | Why it matters |
|---|---|
| **The whole cascade, not one slice** | one action → physical, human, digital, financial, social and planetary effects, together |
| **The best model for each world** | a physics engine for motion, a vision model for perception, an economic model for markets |
| **Plug and play** | swap in a better model for one world without retraining the others |
| **Explainable end to end** | every consequence says which world, which model or rule, which evidence |
| **Safer AI agents** | an agent sees the full consequences of its own action before taking it |
| **Better human decisions** | people, companies and governments see what a choice changes, and for whom |
| **Predicts in phrases, not tokens** | the next consequence or next action comes out as a unit of meaning (Phrase DNA), not word by word: fewer tokens |
| **The best context for any LLM** | only what matters goes in: the worlds touched, the actors, their goals, the state, the evidence |
| **A harness config for agents** | routing tells the agent harness which models and tools to call, with which context |

*Token savings and context quality are design goals, not yet benchmarked.*

```bash
git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git SLM
git clone git@github.com:Sherlock2019/ACM.git && cd ACM && ./start.sh   # → http://127.0.0.1:3010
```

## What next: build it with us

Built today: the shared meaning (MLM), routing, state changes, other actors' goals, 8 scenes and
a 2D physics lab, with rules standing in for most worlds' models. Connecting the real specialist
models is the next step, and everything not built yet is labelled.

To finish it, we need **top AI talent**: physics simulation (Unreal Engine 5), computer vision,
world models, agents, and economic and earth modelling. Each world needs a real model behind it.

**Let's work together:**
- Profile and projects: **[dzoannguyentran.jobsmatchnow.com](https://dzoannguyentran.jobsmatchnow.com/#projects)**
- WhatsApp: **[+84 908 618 075](https://wa.me/84908618075)**

© 2026 Dzoan Nguyen Tran · [MIT](LICENSE)
