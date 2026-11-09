"""ACM command line.

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
        prog="acm", description="Action–Consequence Model - what an action changes, and for whom."
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
    scene = sub.add_parser("scene", help="the scene engine: a structured script, its consequences, next scenes")
    scene.add_argument("action", choices=["list", "validate", "show", "analyze", "branches", "select", "export", "bundle"])
    scene.add_argument("scene", nargs="?", default="car_sale", help="scene id (scenes/<id>.yaml) or a path")
    scene.add_argument("--branch", default=None, help="branch id, for select / export")
    scene.add_argument("--provider", choices=["demo", "model"], default="demo",
                       help="branches from the authored demo (default) or the local LLM")
    scene.add_argument("--no-fallback", action="store_true", help="with --provider model: fail instead of falling back")
    scene.add_argument("-o", "--out", type=Path, default=None, help="write JSON here instead of printing")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "scene":
        return scene_command(args)

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
            from acm.scene import bundle, load_scene, scene_ids

            for scene_id in scene_ids():  # the dashboard's scene demo reads these (authored, deterministic)
                out = args.json.parent / f"scene_{scene_id}.json"
                out.write_text(json.dumps(bundle(load_scene(scene_id)), ensure_ascii=False), encoding="utf-8")
                print(f"scene:  {out}")
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


def scene_command(args: argparse.Namespace) -> int:
    from acm.scene import (
        DemoProvider, ProviderError, SceneError, bundle, directions, generate_branches, load_scene, scene_ids,
        select_branch,
    )

    def emit(data) -> None:
        text = json.dumps(data, indent=1, ensure_ascii=False, default=lambda o: o.model_dump(mode="json"))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)

    if args.action == "list":
        print("\n".join(scene_ids()))
        return 0
    try:
        scene = load_scene(args.scene)
    except (SceneError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.action == "validate":
        print(f"{scene.id}: valid ({len(scene.actors)} actors, {len(scene.objects)} objects, {len(scene.events)} events, "
              f"{len(scene.demo.branches) if scene.demo else 0} authored branches)")
    elif args.action == "show":
        print(f"{scene.title}\n{scene.location.name}, {scene.location.city} · {scene.time}\nStatus: {scene.status}\n")
        for e in scene.events:
            who = scene.actor(e.actor).name.upper() if e.actor else ""
            print(f"  {e.order:>2}. {who + ': ' if e.dialogue else ''}{e.dialogue or e.description}")
    elif args.action == "analyze":
        emit(DemoProvider().analyze(scene))
    elif args.action == "branches":
        try:
            result = generate_branches(scene, args.provider, fallback=not args.no_fallback)
        except ProviderError as exc:
            print(f"provider error: {exc}", file=sys.stderr)
            return 2
        if result["fallback"]:
            print(f"note: {result['fallback']}", file=sys.stderr)
        emit(result)
    elif args.action == "select":
        if not args.branch:
            print("select needs --branch", file=sys.stderr)
            return 1
        emit(select_branch(scene, args.branch))
    elif args.action == "export":
        branch = select_branch(scene, args.branch)["branch"] if args.branch else None
        emit(directions(scene, branch))
    elif args.action == "bundle":
        emit(bundle(scene))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
