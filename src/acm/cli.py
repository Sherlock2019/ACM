"""ARM command line.

    python -m acm.cli predict "John will sell his car to Sarah in Paris tomorrow." \\
        --context "Mark wants to buy John's car."
    python -m acm.cli predict "..." --format mermaid      # mind map
    python -m acm.cli graph   "..."                       # the vector graph, as Mermaid
    python -m acm.cli remember "..."                      # store in the graph vector DB
    python -m acm.cli similar  "..."                      # nearest stored actions
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from acm.engine import ConsequenceEngine
from acm.render import to_flowchart, to_mindmap, to_text

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "acm.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="acm", description="Action Reaction Model - what an action changes, and for whom."
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
    demo = sub.add_parser("demo", help="run the multimodal tabletop demo (fixture replay + simulator)")
    demo.add_argument("--report", type=Path, default=Path("docs/demo/tabletop_report.html"),
                      help="where to write the self-contained HTML report")
    demo.add_argument("--json", type=Path, default=None, help="also write the full demo result as JSON")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "demo":
        from acm.demo import run_demo
        from acm.visual_report import render_report

        result = run_demo()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(result), encoding="utf-8")
        print(f"report: {args.report}")
        if args.json is not None:
            from acm.inference import run_suite

            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"json:   {args.json}")
            suite_data = run_suite()
            suite = args.json.parent / "inference_suite.json"
            suite.write_text(json.dumps(suite_data, ensure_ascii=False), encoding="utf-8")
            print(f"suite:  {suite}")
            from acm.inference import EXAMPLES, pair_llm

            baseline_file = EXAMPLES / "llm_baseline.json"
            if baseline_file.is_file():  # recorded real LLM answers (scripts/make_llm_baseline.py)
                paired = pair_llm(suite_data, json.loads(baseline_file.read_text(encoding="utf-8")))
                (args.json.parent / "llm_vs_acm.json").write_text(json.dumps(paired, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"llm:    {args.json.parent / 'llm_vs_acm.json'}")
        print(result["badge"])
        return 0

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
        from acm.store import GraphVectorStore

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
