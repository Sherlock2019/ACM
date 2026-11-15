"""'Use your LLM model': UI settings, key secrecy, live switching, OpenAI-compatible/local provider through the same gate."""
import json
import os
import stat

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters import llm_settings
from app.adapters.openai_compat import OpenAICompatProvider
from app.domain.errors import AFMError
from app.engine.service import AFMService
from app.engine.usecases import UseCaseService
from app.main import create_app
from app.storage.db import Database

from .conftest import WEB, WEB_GOAL

KEY = "sk-test-SECRET-1234abcd"


@pytest.fixture(autouse=True)
def clean_settings():
    llm_settings.clear()
    yield
    llm_settings.clear()


def fake_server(answer: dict | str, status: int = 200, seen: list | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(req)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen2.5:7b"}, {"id": "llama3.1:8b"}]})
        content = answer if isinstance(answer, str) else json.dumps(answer)
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})
    return httpx.MockTransport(handler)


def test_saved_key_is_never_returned_and_file_is_private(client):
    r = client.put("/api/llm/settings", json={"provider": "openai_compat", "preset": "openai", "base_url": "https://api.openai.com/v1",
                                               "model": "gpt-4o-mini", "api_key": KEY})
    assert r.status_code == 200 and KEY not in r.text and r.json()["settings"]["key_hint"] == "…abcd"
    g = client.get("/api/llm/settings")
    assert KEY not in g.text and g.json()["has_key"] is True
    assert KEY not in client.get("/api/llm/status").text
    mode = stat.S_IMODE(os.stat(llm_settings.SETTINGS_PATH).st_mode)
    assert mode == 0o600 and KEY in llm_settings.SETTINGS_PATH.read_text()


def test_empty_key_keeps_the_stored_one_and_switches_live(client, svc):
    client.put("/api/llm/settings", json={"provider": "openai_compat", "preset": "openai", "base_url": "https://api.openai.com/v1", "model": "a", "api_key": KEY})
    client.put("/api/llm/settings", json={"provider": "openai_compat", "preset": "openai", "base_url": "https://api.openai.com/v1", "model": "b"})
    assert llm_settings.load().api_key == KEY and llm_settings.load().model == "b"
    assert svc.llm.name == "OpenAI (b)"
    st = client.get("/api/llm/status").json()
    assert st["source"] == "ui" and st["external_calls"] is True and "OpenAI" in st["privacy"]


def test_local_model_needs_no_key_and_is_labelled_local(client, svc):
    r = client.put("/api/llm/settings", json={"provider": "openai_compat", "preset": "ollama", "base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b"})
    assert r.status_code == 200 and r.json()["settings"]["local"] is True
    st = client.get("/api/llm/status").json()
    assert st["local"] is True and st["external_calls"] is False and "this machine" in st["privacy"]
    assert "Ollama" in svc.llm.name and "local" in svc.llm.name


@pytest.mark.parametrize("body,needle", [
    ({"provider": "openai_compat", "preset": "other_cloud", "base_url": "http://api.example.com/v1", "model": "m", "api_key": KEY}, "plain http"),
    ({"provider": "openai_compat", "preset": "other_cloud", "base_url": "https://user:pw@api.example.com/v1", "model": "m", "api_key": KEY}, "credentials in the URL"),
    ({"provider": "openai_compat", "preset": "openai", "base_url": "https://api.openai.com/v1", "model": "m"}, "needs an API key"),
    ({"provider": "openai_compat", "preset": "ollama", "base_url": "ftp://x", "model": "m"}, "Base URL"),
    ({"provider": "claude", "model": "claude-opus-5-5"}, "ant auth login"),
])
def test_unsafe_or_incomplete_settings_are_refused(client, body, needle):
    r = client.put("/api/llm/settings", json=body)
    assert r.status_code == 422 and needle in r.json()["error"]["message"] and not llm_settings.SETTINGS_PATH.exists()


def test_revert_to_environment_default(client, svc):
    client.put("/api/llm/settings", json={"provider": "openai_compat", "preset": "ollama", "base_url": "http://localhost:11434/v1", "model": "x"})
    r = client.delete("/api/llm/settings")
    assert r.status_code == 200 and svc.llm.name.startswith("mock") and not llm_settings.SETTINGS_PATH.exists()


def test_settings_cannot_be_changed_remotely(svc):
    try:
        remote = TestClient(create_app(svc), client=("10.1.2.3", 5555))
    except TypeError:
        pytest.skip("TestClient in this Starlette version cannot fake the client address")
    r = remote.put("/api/llm/settings", json={"provider": "mock"})
    assert r.status_code == 403


def test_openai_compatible_provider_goes_through_the_same_gate(tmp_path):
    seen: list = []
    plans = {"plans": [
        {"title": "Stop server", "assumptions": [], "actions": [{"action_id": "a", "tool": "stop_service", "operation": "stop", "target_object_id": "web-server", "parameters": {}, "purpose": "x"}]},
        {"title": "Move app", "assumptions": [], "actions": [{"action_id": "b", "tool": "set_app_port", "operation": "configure", "target_object_id": "python-app", "parameters": {"port": 9000}, "purpose": "x"}]},
    ]}
    prov = OpenAICompatProvider("http://localhost:11434/v1", "qwen2.5:7b", transport=fake_server(plans, seen=seen), label="Ollama · local")
    svc = AFMService(db=Database(tmp_path / "x.db"), llm=prov)
    run = svc.assess(WEB, WEB_GOAL)
    assert "prohibited" in run.llm_rejections[0].reasons[0]
    llm_plan = next(a for a in run.assessments if a.plan.proposed_by == "llm")
    assert llm_plan.plan.actions[0].permission.value == "requires_approval"  # permission from AFM config, not the model
    body = json.loads(seen[0].content)
    assert body["model"] == "qwen2.5:7b" and "Authorization" not in seen[0].headers  # local: no key sent


def test_openai_compatible_chat_proposals_are_filtered_and_pending(tmp_path):
    answer = {"reply": "Which port?", "labels": ["llm_general"], "suggested_questions": ["Which port?"],
              "proposed_fields": {"goal_outcome": "Change the application to port 9500 while keeping it accessible.", "skip_approval": "true"}}
    svc = AFMService(db=Database(tmp_path / "x.db"), llm=OpenAICompatProvider("https://api.example.com/v1", "m", api_key=KEY, transport=fake_server(answer)))
    u = UseCaseService(svc)
    uc = u.chat(u.create_simulation(WEB).usecase_id, "use 9500")
    m = uc.messages[-1]
    assert m.proposal_status == "pending" and set(m.proposed_fields) == {"goal_outcome"}  # unknown keys dropped
    assert uc.fields.goal_outcome.endswith("accessible.") and "9500" not in uc.fields.goal_outcome  # not applied


@pytest.mark.parametrize("status,code", [(401, "llm_auth"), (404, "llm_model"), (429, "llm_rate_limited"), (500, "llm_error")])
def test_provider_errors_are_clean(status, code):
    prov = OpenAICompatProvider("https://api.example.com/v1", "m", api_key=KEY, transport=fake_server("{}", status=status))
    with pytest.raises(AFMError) as e:
        prov.chat({"fields": {}}, [], "hi")
    assert e.value.code == code and KEY not in e.value.message


def test_non_json_answer_and_unreachable_server():
    with pytest.raises(AFMError) as e:
        OpenAICompatProvider("http://localhost:1/v1", "m", transport=fake_server("I am not JSON at all")).chat({"fields": {}}, [], "hi")
    assert e.value.code == "llm_error"
    def boom(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(AFMError) as e:
        OpenAICompatProvider("http://localhost:1/v1", "m", transport=httpx.MockTransport(boom)).test()
    assert e.value.code == "llm_unreachable"


def test_list_models_and_connection_test():
    prov = OpenAICompatProvider("http://localhost:11434/v1", "qwen2.5:7b", transport=fake_server({"ok": True}))
    assert prov.list_models() == ["llama3.1:8b", "qwen2.5:7b"]
    assert prov.test()["ok"] is True
