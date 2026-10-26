#!/usr/bin/env python3
"""Parse the inference suite once with MLM's real parser and freeze the parses.

    python scripts/make_inference_suite.py            # needs MLM's parser (Stanza)
    python scripts/make_inference_suite.py --check    # also print each scenario's bindings

Writes examples/inference_suite.conllu (silver data: parser output, reviewed via
--check), then builds the suite from it - the same way the demo and tests do.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acm.inference import SUITE_CONLLU, all_sentences, load_scenarios, run_suite  # noqa: E402

HEADER = """\
# ACM inference suite - SILVER data (MLM parser output), not gold annotation.
# Produced by scripts/make_inference_suite.py from examples/inference_suite.yaml.
# Regenerate deliberately and review the diff.
#
# parser: {parser}
# language: en
"""


def main() -> int:
    from splm.config import Config
    from splm.linguistic.factory import build_parser

    backend = build_parser(Config.load())
    sentences = all_sentences(load_scenarios())
    blocks = []
    for text in sentences:
        document = backend.parse(text, "en")
        if len(document.sentences) != 1:
            print(f"warning: {text!r} parsed as {len(document.sentences)} sentences", file=sys.stderr)
        for sentence in document.sentences:
            blocks.append(f"# input = {text}\n{sentence.to_conllu()}")
    SUITE_CONLLU.write_text(HEADER.format(parser=getattr(backend, "name", "unknown")) + "\n" + "\n".join(blocks),
                            encoding="utf-8")
    print(f"wrote {SUITE_CONLLU.relative_to(ROOT)} ({len(blocks)} sentences)")

    suite = run_suite()
    print(f"{suite['stats']['scenarios']} scenarios, {suite['stats']['questions']} questions; missing: {suite['missing']}")
    if "--check" in sys.argv:
        for item in suite["items"]:
            s = item["summary"]
            binds = ", ".join(f"{b['concept_role']}={b['entity']}" for b in item["trace"].get("bindings", []))
            print(f"{item['id']} {item['action']}\n     {s['concept']} | {binds} | places={s['places']}")
            for qa in item["answers"]:
                print(f"     Q: {qa['question']}\n        A: {qa['answer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
