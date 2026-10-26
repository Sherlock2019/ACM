#!/usr/bin/env python3
"""Ask a real language model the same "what happens next to X?" questions ACM answers.

    python scripts/make_llm_baseline.py            # run with MLM's environment (torch + transformers)

Uses the base Transformer MLM is configured with (config/model.yaml), on CPU, from
the local Hugging Face cache - nothing is downloaded unless it is already configured.
For every question it records one greedy answer and three sampled ones (temperature
0.9, fixed seeds), with the exact prompt, model id and settings, in
examples/llm_baseline.json. The tour shows these outputs verbatim.

This is a small *base* model (no instruction tuning). Larger chat models answer far
better; the comparison is about properties (reasons, stability, abstention,
modalities), not about which one writes nicer sentences.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "examples" / "llm_baseline.json"
QUESTIONS = [
    # (scenario action, subject phrase as in ACM's question)
    ("John sold his car to Sarah.", ["Mark", "Sarah", "John"]),
    ("John flew to London.", ["the people living near the airport", "the earth"]),
    ("The engineer deleted the database in production.", ["the company's customers", "the database"]),
    ("The company destroyed the forest.", ["the forest", "the earth"]),
    ("Tom gave all his money to Maria.", ["Tom's plan to buy a bike"]),
    ("John kicked the ball.", ["the ball"]),
    ("John did not sell his car to Sarah.", ["Sarah"]),
]
SAMPLES = [1, 2, 3]
MAX_NEW = 40


def main() -> int:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from acm.inference import load_scenarios
    from splm.config import Config

    config = Config.load()
    model_id = config.get("model.model.model_id") or config.model.get("model_id")
    cache = config.get("model.model.cache_dir")
    tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache)
    model = AutoModelForCausalLM.from_pretrained(model_id, cache_dir=cache)
    model.eval()
    scenarios = {s["action"]: s for s in load_scenarios()}

    def generate(prompt: str, seed: int | None) -> str:
        inputs = tokenizer(prompt, return_tensors="pt")
        kwargs = {"max_new_tokens": MAX_NEW, "pad_token_id": tokenizer.eos_token_id}
        if seed is None:
            kwargs["do_sample"] = False
        else:
            torch.manual_seed(seed)
            kwargs.update(do_sample=True, temperature=0.9, top_p=0.95)
        with torch.no_grad():
            output = model.generate(**inputs, **kwargs)
        text = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return text.split("\nQuestion:")[0].split("\n\n")[0].strip()

    records = []
    for action, subjects in QUESTIONS:
        context = " ".join(scenarios[action]["context"]) if action in scenarios else ""
        for subject in subjects:
            prompt = f"{context} {action}".strip() + f"\nQuestion: What happens next to {subject}?\nAnswer:"
            started = time.perf_counter()
            greedy = generate(prompt, None)
            samples = [generate(prompt, seed) for seed in SAMPLES]
            records.append({
                "action": action, "context": scenarios.get(action, {}).get("context", []), "subject": subject,
                "prompt": prompt, "greedy": greedy, "samples": samples,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"[{subject}] {greedy!r}")
    OUT.write_text(json.dumps({
        "model": model_id, "kind": "base language model (no instruction tuning), local CPU",
        "settings": {"max_new_tokens": MAX_NEW, "greedy": "do_sample=False",
                     "samples": f"temperature=0.9, top_p=0.95, seeds {SAMPLES}"},
        "recorded": time.strftime("%Y-%m-%d"),
        "records": records,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(records)} questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
