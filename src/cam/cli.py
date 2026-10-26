"""CAM command line.

    python -m cam.cli predict "John will sell his car to Sarah in Paris tomorrow." \\
        --context "Mark wants to buy John's car."
    python -m cam.cli predict "..." --format mermaid      # mind map
    python -m cam.cli graph   "..."                       # the vector graph, as Mermaid
    python -m cam.cli remember "..."                      # store in the graph vector DB
    python -m cam.cli similar  "..."                      # nearest stored actions
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cam.engine import ConsequenceEngine
from cam.render import to_flowchart, to_mindmap, to_text

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "cam.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cam", description="Consequence Action Model - what an action changes, and for whom."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("text", help="the action; earlier sentences in it count as context")
        p.add_argument("--context", action="append", default=[], help="a context sentence (repeatable)")
        p.add_argument("--language", default=None, help="force a language instead of detecting it")
        return p

    predict = command("predict", "consequences of an action")
    predict.add_argument("--format", choices=["text", "mermaid", "json"], default="text")
    command("graph", "the action graph as a Mermaid flowchart")
    for name, help_text in (("remember", "store the action graph"), ("similar", "find similar stored actions")):
        p = command(name, help_text)
        p.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    engine = ConsequenceEngine()
    report = engine.analyze(args.text, context=args.context, language=args.language)

    if args.command == "predict":
        if args.format == "mermaid":
            print(to_mindmap(report))
        elif args.format == "json":
            print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))
        else:
            print(to_text(report))
    elif args.command == "graph":
        print(to_flowchart(report.graph))
    else:
        from cam.store import GraphVectorStore

        store = GraphVectorStore(args.db)
        if args.command == "remember":
            graph_id = store.add(report)
            print(f"stored graph {graph_id} in {args.db}  {store.stats()}")
        else:
            for hit in store.similar_actions(report):
                print(f"{hit['score']:.3f}  #{hit['graph_id']}  {hit['label']:<10}  {hit['text']}")
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
