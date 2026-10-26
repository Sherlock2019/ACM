#!/usr/bin/env python3
"""Freeze MLM parser output for CAM's tests, the same way MLM does for its own.

    python scripts/make_fixtures.py

CAM's tests then run without a parser model. Re-run after deliberately changing
the parser and review the diff: a changed tree changes the tests' premises.
"""

from __future__ import annotations

import sys
from pathlib import Path

CAM_ROOT = Path(__file__).resolve().parents[1]
OUT = CAM_ROOT / "tests" / "fixtures"

SENTENCES: dict[str, list[str]] = {
    "en": [
        "Mark wants to buy John's car.",
        "John will sell his car to Sarah in Paris tomorrow to pay his debt.",
        "John sold his car to Sarah.",
        "John sold his car.",
        "John did not sell his car to Sarah.",
        "If the bank refuses, John will sell his car to Sarah.",
        "Sarah needs a car.",
        "John owns a car.",
        "He sold it to Sarah.",
        "Mark bought a car.",
        "John stole the car.",
        "The engineer deleted the database in production.",
        "The company destroyed the forest.",
        "John flew to London.",
        "John traveled to Paris by train.",
        "John kicked the ball.",
        "I will give my car to Sarah.",
        "Mark hopes to win the race.",
        "Sarah won the race.",
        "John is tired.",
    ],
    "fr": [
        "Marc veut acheter la voiture de John.",
        "John vendra sa voiture demain.",
    ],
}

HEADER = """\
# CAM test fixture - SILVER data (MLM parser output), not gold annotation.
# Produced by scripts/make_fixtures.py. Regenerate deliberately and review the diff.
#
# parser: {parser}
# language: {language}
"""


def main() -> int:
    from splm.config import Config
    from splm.linguistic.factory import build_parser

    backend = build_parser(Config.load())
    OUT.mkdir(parents=True, exist_ok=True)
    for language, sentences in SENTENCES.items():
        blocks = []
        for text in sentences:
            document = backend.parse(text, language)
            if len(document.sentences) != 1:
                print(f"warning: {text!r} parsed as {len(document.sentences)} sentences", file=sys.stderr)
            for sentence in document.sentences:
                blocks.append(f"# input = {text}\n{sentence.to_conllu()}")
        target = OUT / f"{language}.conllu"
        target.write_text(
            HEADER.format(parser=getattr(backend, "name", "unknown"), language=language)
            + "\n"
            + "\n".join(blocks),
            encoding="utf-8",
        )
        print(f"wrote {target} ({len(blocks)} sentences)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
