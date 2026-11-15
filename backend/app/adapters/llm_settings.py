"""LLM settings chosen in the UI ("Use your LLM model").

Stored in backend/data/llm_settings.json (git-ignored folder, file mode 600). The API key is written only there,
never logged, never returned to the browser (only a masked hint), never sent anywhere except the chosen provider.
If no settings file exists, AFM falls back to environment configuration (backend/.env) and finally to the mock.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from ..domain.errors import AFMError

SETTINGS_PATH = Path(os.environ.get("AFM_LLM_SETTINGS_PATH") or Path(__file__).resolve().parents[2] / "data" / "llm_settings.json")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}

PRESETS: dict[str, dict[str, Any]] = {
    # cloud, OpenAI-compatible (check each provider's docs: URLs and model names change)
    "openai": {"kind": "cloud", "label": "OpenAI", "base_url": "https://api.openai.com/v1", "model_hint": "e.g. gpt-4o-mini", "key_required": True,
               "key_help": "platform.openai.com → API keys"},
    "gemini": {"kind": "cloud", "label": "Google Gemini (OpenAI-compatible endpoint)", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "model_hint": "a Gemini model name from Google AI Studio", "key_required": True, "key_help": "aistudio.google.com → Get API key"},
    "groq": {"kind": "cloud", "label": "Groq", "base_url": "https://api.groq.com/openai/v1", "model_hint": "a model id from console.groq.com",
             "key_required": True, "key_help": "console.groq.com → API Keys"},
    "openrouter": {"kind": "cloud", "label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "model_hint": "e.g. provider/model-name",
                   "key_required": True, "key_help": "openrouter.ai → Keys"},
    "mistral": {"kind": "cloud", "label": "Mistral", "base_url": "https://api.mistral.ai/v1", "model_hint": "a model id from console.mistral.ai",
                "key_required": True, "key_help": "console.mistral.ai → API keys"},
    "other_cloud": {"kind": "cloud", "label": "Other OpenAI-compatible API", "base_url": "", "model_hint": "the provider's model id", "key_required": True,
                    "key_help": "your provider's console"},
    # local servers (nothing leaves this machine)
    "ollama": {"kind": "local", "label": "Ollama", "base_url": "http://localhost:11434/v1", "model_hint": "e.g. qwen2.5:7b (ollama pull qwen2.5:7b)",
               "key_required": False, "key_help": "not needed"},
    "lmstudio": {"kind": "local", "label": "LM Studio", "base_url": "http://localhost:1234/v1", "model_hint": "the model loaded in LM Studio",
                 "key_required": False, "key_help": "not needed"},
    "vllm": {"kind": "local", "label": "vLLM", "base_url": "http://localhost:8000/v1", "model_hint": "the --model you served",
             "key_required": False, "key_help": "only if you started vLLM with --api-key"},
    "llamacpp": {"kind": "local", "label": "llama.cpp server", "base_url": "http://localhost:8080/v1", "model_hint": "any name (single model)",
                 "key_required": False, "key_help": "only if started with --api-key"},
    "other_local": {"kind": "local", "label": "Other local OpenAI-compatible server", "base_url": "http://localhost:", "model_hint": "the served model id",
                    "key_required": False, "key_help": "if your server requires one"},
}


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["mock", "claude", "openai_compat"]
    preset: Optional[str] = None
    base_url: str = ""
    model: str = ""
    api_key: str = ""  # stored on disk only
    use_ant_login: bool = False  # Claude: use `ant auth login` instead of a key
    effort: Literal["low", "medium", "high"] = "low"
    timeout: float = Field(default=60, ge=5, le=600)


def mask(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else "")


def is_local(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "") in LOCAL_HOSTS
    except ValueError:
        return False


def validate(s: LLMSettings) -> None:
    if s.provider == "openai_compat":
        p = urlparse(s.base_url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise AFMError("invalid_input", "Base URL must look like https://host/v1 or http://localhost:PORT/v1.", 422)
        if p.username or p.password:
            raise AFMError("invalid_input", "Do not put credentials in the URL; use the API key field.", 422)
        if p.scheme == "http" and not is_local(s.base_url) and s.api_key:
            raise AFMError("invalid_input", "Refusing to send an API key over plain http to a remote host. Use https.", 422)
        if not s.model.strip():
            raise AFMError("invalid_input", "Enter the model name.", 422)
        preset = PRESETS.get(s.preset or "")
        if preset and preset["key_required"] and not s.api_key:
            raise AFMError("invalid_input", f"{preset['label']} needs an API key.", 422)
    if s.provider == "claude" and not s.api_key and not s.use_ant_login:
        raise AFMError("invalid_input", "Enter your Anthropic API key, or tick “use ant auth login”.", 422)


def load() -> Optional[LLMSettings]:
    try:
        return LLMSettings.model_validate(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return None


def save(s: LLMSettings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(s.model_dump_json())
    os.chmod(tmp, 0o600)
    os.replace(tmp, SETTINGS_PATH)


def clear() -> None:
    try:
        SETTINGS_PATH.unlink()
    except FileNotFoundError:
        pass


def public_view(s: Optional[LLMSettings]) -> dict[str, Any]:
    """Safe to send to the browser: never includes the key."""
    if s is None:
        return {"source": "environment", "provider": None}
    d = s.model_dump(exclude={"api_key"})
    d.update({"source": "ui", "has_key": bool(s.api_key), "key_hint": mask(s.api_key),
              "local": s.provider == "openai_compat" and is_local(s.base_url)})
    return d


def build(s: LLMSettings):
    from .claude_provider import ClaudeProvider
    from .llm import MockLLM
    from .openai_compat import OpenAICompatProvider

    if s.provider == "mock":
        return MockLLM()
    if s.provider == "claude":
        return ClaudeProvider(model=s.model or None, effort=s.effort, api_key=None if s.use_ant_login else s.api_key, timeout=s.timeout)
    label = PRESETS.get(s.preset or "", {}).get("label", "openai-compatible")
    return OpenAICompatProvider(base_url=s.base_url, model=s.model, api_key=s.api_key, timeout=s.timeout,
                                label=f"{label}{' · local' if is_local(s.base_url) else ''}")
