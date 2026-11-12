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

## So what

- **Mark's case, answered right:** his goal is **BLOCKED**. One car, one owner, and Sarah has it.
- **Every answer shows its rule and evidence.** Same input, same answer.
- **Unknown is said out loud:** no rule matched never means no impact.
- **An AI can check its own action** ("I will…") before taking it.
- **New knowledge is a YAML edit**, not retraining.

```bash
git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git SLM
git clone git@github.com:Sherlock2019/ACM.git && cd ACM && ./start.sh   # → http://127.0.0.1:3010
```

## What next: build it with us

Built today: meaning, state changes, other actors' goals, 8 scenes, routing, a 2D physics lab.
Most worlds are still rules, and everything not built is labelled.

To finish it, we need **top AI talent**: physics simulation (Unreal Engine 5), computer vision,
world models, agents, and economic and earth modelling. Each world needs a real model behind it.

**Let's work together:**
- Profile and projects: **[dzoannguyentran.jobsmatchnow.com](https://dzoannguyentran.jobsmatchnow.com/#projects)**
- WhatsApp: **[+84 908 618 075](https://wa.me/84908618075)**

© 2026 Dzoan Nguyen Tran · [MIT](LICENSE)
