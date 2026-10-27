"""The language layer: a local LLM answers questions from ACM's facts, in Phrase DNA.

    question --LLM--> plan      (physics questions: which object, which action, how far)
    ACM / simulator   facts     (consequences, rules, events — computed, not generated)
    facts + question --LLM--> answer + one phrase per consequence:
                              WHO · DOES · WHAT · WHERE · WHEN · WITH WHOM · WHY

The model only words the answer. It is told to use the facts and nothing else, runs at
temperature 0 with a fixed seed, and every phrase it returns is checked for shape. When
the model is unreachable, callers fall back to ACM's own deterministic sentences.

Defaults to Ollama on this machine (qwen2.5:7b); override with ACM_LLM_URL / ACM_LLM_MODEL.
Nothing is sent off the machine unless ACM_LLM_URL points elsewhere.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

URL = os.environ.get("ACM_LLM_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("ACM_LLM_MODEL", "qwen2.5:7b")
TIMEOUT_S = float(os.environ.get("ACM_LLM_TIMEOUT", "120"))
PHRASE_KEYS = ("who", "does", "what", "where", "when", "with_whom", "why")


class LLMUnavailable(RuntimeError):
    pass


def _post(path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(f"{URL}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise LLMUnavailable(f"LLM at {URL} unreachable: {exc}") from exc


def status() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=3) as response:
            names = [m["name"] for m in json.loads(response.read()).get("models", [])]
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        return False, f"no LLM server at {URL} ({exc})"
    if MODEL not in names and f"{MODEL}:latest" not in names:
        return False, f"model {MODEL} is not pulled on {URL} (ollama pull {MODEL})"
    return True, f"{MODEL} via {URL}"


def chat_json(system: str, user: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    reply = _post("/api/chat", {
        "model": MODEL, "stream": False, "format": "json", "keep_alive": "30m",
        "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }, TIMEOUT_S)
    content = reply.get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise LLMUnavailable(f"{MODEL} returned no JSON: {content[:200]!r}") from exc
    return (data if isinstance(data, dict) else {}), round(time.perf_counter() - started, 2)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"null", "none", "unknown", "n/a", "-"} else None


def _phrases(raw: Any) -> list[dict[str, str | None]]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            phrase = {key: _text(item.get(key)) for key in PHRASE_KEYS}
            if phrase["who"] or phrase["does"]:
                out.append(phrase)
    return out[:10]


# -- answering ---------------------------------------------------------------------------------

ANSWER_SYSTEM = """You are the language layer of ACM, the Actions Consequential Model.
ACM's engine has already computed the FACTS (JSON) about an action and its consequences.
Answer the QUESTION using ONLY those FACTS.
Rules:
- Never add a consequence, cause, person, place, number or reason that is not in FACTS.
- If FACTS do not answer the question, say ACM has no evidence for it (never say "no impact").
- Facts marked unknown stay unknown; assumed values are called assumptions.
- For a what-if, say concretely which consequences are new and which no longer follow.
- Keep the answer to 1-4 plain sentences.
Return JSON exactly like:
{"answer": "<plain-language answer>",
 "phrases": [{"who": "...", "does": "...", "what": "...", "where": "...", "when": "...", "with_whom": "...", "why": "..."}]}
Give one phrase per consequence you mention, each written as a consequence of the original action.
"why" names the cause (the original action) and the rule from FACTS. Use null for a field FACTS do not give."""


def answer(question: str, facts: dict[str, Any], kind: str = "phrase") -> dict[str, Any]:
    """The LLM's grounded answer: {"text", "phrases", "model", "seconds"}."""
    source = "ACM's rule engine" if kind == "phrase" else "the physics simulation and the object behaviour library"
    user = f"FACTS (from {source}):\n{json.dumps(facts, ensure_ascii=False)}\n\nQUESTION: {question}"
    data, seconds = chat_json(ANSWER_SYSTEM, user)
    text = _text(data.get("answer"))
    if not text:
        raise LLMUnavailable(f"{MODEL} gave no answer")
    return {"text": text, "phrases": _phrases(data.get("phrases")), "model": MODEL, "seconds": seconds}


def phrase_facts(result: dict[str, Any]) -> dict[str, Any]:
    """The part of an acm.ask result the LLM may use, kept small."""
    def row(ch: dict[str, Any]) -> dict[str, Any]:
        d = ch["dna"]
        return {"ring": ch["ring_title"], "kind": ch["kind"], "basis": ch["basis"], "who": d["who"], "does": d["does"],
                "what": d["what"], "where": d["where"], "when": d["when"], "with_whom": d["with_whom"],
                "cause": d["why"], "rule": d["rule"], **({"status": ch["status"]} if ch.get("status") else {})}

    facts: dict[str, Any] = {
        "original_action": {k: v for k, v in result["action"].items() if v not in (None, False, "")},
        "question_intent": result["intent"],
        "acm_answer": result["answer"],
        "consequences": [row(ch) for ch in result["chains"][:14]],
        "unknown": result["unknowns"],
    }
    cf = result.get("counterfactual")
    if cf:
        facts["what_if_action"] = {k: v for k, v in cf["action"].items() if v not in (None, False, "")}
        facts["no_longer_follow"] = [row(ch) for ch in cf["removed"][:10]]
        facts["new_consequences"] = [row(ch) for ch in cf["added"][:10]]
        facts.pop("consequences")
    return facts


# -- reading physics questions -----------------------------------------------------------------

PLAN_SYSTEM = """You read a question about a tabletop scene and turn it into a plan for a physics simulator.
OBJECTS lists what was detected. "it" means the SELECTED object.
Return JSON exactly like:
{"target": "<an object id from OBJECTS>",
 "intent": "what_happens" | "will_fall" | "fracture" | "spill" | "properties" | "why",
 "action": null | {"kind": "push" | "flick" | "drop" | "remove_support", "dir": 1 | -1,
                   "distance_m": <number>, "speed_mps": <number>, "height_m": <number>}}
Rules:
- "action" is only for a hypothetical action stated in the question (push, nudge, slide, move, flick, hit, knock,
  drop, lift, remove the table). Otherwise it is null and the current action is used.
- dir is 1 toward the right edge / off the table / +x, and -1 toward the centre / left / -x. Default 1.
- Convert cm to metres. Defaults: push distance 0.2, flick speed 2.0, drop height 0.3.
- "hard", "harder", "fast" mean a flick. Removing the table or its support is remove_support.
- intent: "will_fall" for fall/tip questions, "fracture" for break/survive/damage, "spill" for spill/contents,
  "properties" for weight/material, "why" for why, otherwise "what_happens".
Examples:
Q: What happens if I shove the blue cup 25 cm off the table? -> {"target": "blue_cup_01", "intent": "what_happens",
   "action": {"kind": "push", "dir": 1, "distance_m": 0.25, "speed_mps": 2.0, "height_m": 0.3}}
Q: Will the red mug survive if someone knocks it hard to the right? -> {"target": "red_cup_01", "intent": "fracture",
   "action": {"kind": "flick", "dir": 1, "distance_m": 0.2, "speed_mps": 2.0, "height_m": 0.3}}
Q: Slide it 10 cm toward the middle -> {"target": "<SELECTED>", "intent": "what_happens",
   "action": {"kind": "push", "dir": -1, "distance_m": 0.1, "speed_mps": 2.0, "height_m": 0.3}}
Q: Can it break? -> {"target": "<SELECTED>", "intent": "fracture", "action": null}"""


def physics_plan(question: str, objects: list[dict[str, Any]], selected: str) -> dict[str, Any]:
    ids = [o["id"] for o in objects]
    user = f"OBJECTS: {json.dumps(objects)}\nSELECTED: {selected}\nQUESTION: {question}"
    data, seconds = chat_json(PLAN_SYSTEM, user)
    target = data.get("target") if data.get("target") in ids else selected
    intent = data.get("intent") if data.get("intent") in {"what_happens", "will_fall", "fracture", "spill", "properties", "why"} \
        else "what_happens"
    action = None
    raw = data.get("action")
    if isinstance(raw, dict) and raw.get("kind") in {"push", "flick", "drop", "remove_support"}:
        def num(key: str, default: float, lo: float, hi: float) -> float:
            try:
                return min(hi, max(lo, float(raw.get(key) if raw.get(key) is not None else default)))
            except (TypeError, ValueError):
                return default

        action = {"kind": raw["kind"], "dir": -1 if raw.get("dir") in (-1, "-1") else 1,
                  "distance_m": num("distance_m", 0.2, 0.01, 1.0), "speed_mps": num("speed_mps", 2.0, 0.1, 5.0),
                  "height_m": num("height_m", 0.3, 0.05, 1.0)}
    return {"target": target, "intent": intent, "action": action, "model": MODEL, "seconds": seconds}
