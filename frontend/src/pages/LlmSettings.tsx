import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "../components/icons";
import { ErrorBox, Loading, Panel, Plain } from "../components/ui";
import { api } from "../services/api";
import { useAFM } from "../state";
import type { LLMPreset, LLMSettingsIn, LLMSettingsView } from "../types/afm";

type Choice = "claude" | "cloud" | "local" | "mock";
const CLOUD = ["openai", "gemini", "groq", "openrouter", "mistral", "other_cloud"];
const LOCAL = ["ollama", "lmstudio", "vllm", "llamacpp", "other_local"];
const LOCAL_STEPS: Record<string, string[]> = {
  ollama: ["Install Ollama from ollama.com (Linux/WSL: curl -fsSL https://ollama.com/install.sh | sh).", "Download a model: ollama pull qwen2.5:7b", "Ollama serves on port 11434 (it usually starts on its own; otherwise: ollama serve).", "If Ollama runs on Windows and AFM in WSL, localhost works with mirrored networking."],
  lmstudio: ["Open LM Studio and download a model.", "Developer tab → load the model → Start Server (default port 1234)."],
  vllm: ["pip install vllm", "vllm serve <huggingface-model-id> --port 8000 (add --api-key if you want one)."],
  llamacpp: ["Build or download llama.cpp.", "llama-server -m your-model.gguf --port 8080"],
  other_local: ["Start any server that speaks the OpenAI /v1/chat/completions API and enter its address."],
};
const CHOICES: { id: Choice; title: string; sub: string; icon: string }[] = [
  { id: "claude", title: "Claude (Anthropic)", sub: "Your Anthropic API key, or sign in with ant auth login", icon: "brain" },
  { id: "cloud", title: "Cloud API", sub: "OpenAI, Gemini, Groq, OpenRouter, Mistral or any OpenAI-compatible API", icon: "spark" },
  { id: "local", title: "Local model", sub: "Ollama, LM Studio, vLLM, llama.cpp: nothing leaves this machine", icon: "inventory" },
  { id: "mock", title: "Mock (offline)", sub: "No model, no key: deterministic demo answers", icon: "reset" },
];

function Field({ id, label, children, help }: { id: string; label: string; children: ReactNode; help?: ReactNode }) {
  return <div><label className="lbl" htmlFor={id}>{label}</label>{children}{help && <p className="faint tiny mt-s">{help}</p>}</div>;
}

export function LlmSettings() {
  const { llm, refresh } = useAFM();
  const [presets, setPresets] = useState<Record<string, LLMPreset>>({});
  const [claudeModels, setClaudeModels] = useState<string[]>([]);
  const [saved, setSaved] = useState<LLMSettingsView | null>(null);
  const [choice, setChoice] = useState<Choice>("local");
  const [form, setForm] = useState({ preset: "ollama", base_url: "http://localhost:11434/v1", model: "", api_key: "", use_ant_login: false, effort: "low" as "low" | "medium" | "high", timeout: 120 });
  const [showKey, setShowKey] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.llmPresets().then((p) => { setPresets(p.presets); setClaudeModels(p.claude_models); }).catch((e) => setErr(e.message));
    api.llmSettings().then((s) => {
      setSaved(s);
      if (s.source !== "ui" || !s.provider) return;
      const c: Choice = s.provider === "claude" ? "claude" : s.provider === "mock" ? "mock" : LOCAL.includes(s.preset ?? "") || s.local ? "local" : "cloud";
      setChoice(c);
      setForm((f) => ({ ...f, preset: s.preset ?? f.preset, base_url: s.base_url ?? "", model: s.model ?? "", api_key: "", use_ant_login: !!s.use_ant_login, effort: s.effort ?? "low", timeout: s.timeout ?? 60 }));
    }).catch((e) => setErr(e.message));
  }, []);

  const pick = (c: Choice) => {
    setChoice(c); setMsg(null); setModels([]);
    if (c === "cloud") setForm((f) => ({ ...f, preset: "openai", base_url: presets.openai?.base_url ?? "", model: "", api_key: "", timeout: 60 }));
    if (c === "local") setForm((f) => ({ ...f, preset: "ollama", base_url: presets.ollama?.base_url ?? "http://localhost:11434/v1", model: "", api_key: "", timeout: 120 }));
    if (c === "claude") setForm((f) => ({ ...f, model: claudeModels[0] ?? "claude-opus-5-5", api_key: "", timeout: 60 }));
  };
  const setPreset = (p: string) => { setForm((f) => ({ ...f, preset: p, base_url: presets[p]?.base_url ?? f.base_url, model: "" })); setModels([]); setMsg(null); };
  const body = (): LLMSettingsIn => choice === "mock" ? { provider: "mock" }
    : choice === "claude" ? { provider: "claude", model: form.model, api_key: form.api_key, use_ant_login: form.use_ant_login, effort: form.effort, timeout: form.timeout }
    : { provider: "openai_compat", preset: form.preset, base_url: form.base_url, model: form.model, api_key: form.api_key, timeout: form.timeout };
  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setMsg(null);
    try { await fn(); } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(null); }
  };
  const test = () => run("test", async () => { const r = await api.testLlm(body()); setMsg({ ok: r.ok, text: `Connected to ${r.provider} in ${r.latency_ms} ms. Sample answer: ${r.sample}` }); });
  const save = () => run("save", async () => { const r = await api.saveLlmSettings(body()); setSaved(r.settings); setForm((f) => ({ ...f, api_key: "" })); await refresh(); setMsg({ ok: true, text: `Saved. AFM now uses ${r.provider}. The key is stored on this machine only and will not be shown again.` }); });
  const revert = () => run("revert", async () => { const r = await api.clearLlmSettings(); setSaved({ source: "environment", provider: null }); await refresh(); setMsg({ ok: true, text: r.message + ` Now: ${r.provider}.` }); });
  const listModels = () => run("models", async () => { const r = await api.listLlmModels({ ...body(), provider: "openai_compat" }); setModels(r.models); if (r.models[0] && !form.model) setForm((f) => ({ ...f, model: r.models[0] })); setMsg({ ok: true, text: `${r.models.length} model(s) found.` }); });

  if (err) return <ErrorBox error={err} />;
  if (!Object.keys(presets).length) return <Loading what="LLM settings" />;
  const p = presets[form.preset];
  const sameAsSaved = saved?.source === "ui" && saved.has_key && ((choice === "claude" && saved.provider === "claude") || (choice !== "claude" && saved.base_url === form.base_url));
  const keyPlaceholder = sameAsSaved ? `saved key ${saved?.key_hint}: leave empty to keep it` : choice === "claude" ? "sk-ant-…" : p?.key_required ? "paste your API key" : "optional";

  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Settings</p>
          <h1 className="mt-s">Use your LLM model</h1>
          <p className="lede">Connect AFM's chat and LLM tool to your own model: a cloud API with your key, or a model running on this machine. AFM works without any model too (mock).</p>
        </div>
        <div className="glass-flat" style={{ padding: 12, minWidth: 260 }}>
          <p className="hud-label">Active now</p>
          <p className="small mt-s"><strong>{llm?.provider}</strong></p>
          <p className="faint tiny mt-s">{llm?.source === "ui" ? "From these settings" : "From backend/.env (or the default mock)"} · {llm?.privacy}</p>
        </div>
      </div>

      <div className="grid g4" role="radiogroup" aria-label="Model source">
        {CHOICES.map((c) => (
          <button key={c.id} role="radio" aria-checked={choice === c.id} className={`glass panel env-card ${choice === c.id ? "selected" : ""}`} style={{ textAlign: "left", cursor: "pointer", color: "inherit" }} onClick={() => pick(c.id)}>
            <span className="row" style={{ flexWrap: "nowrap" }}><span className="type-ico"><Icon name={c.icon} /></span><strong>{c.title}</strong></span>
            <span className="small dim">{c.sub}</span>
          </button>
        ))}
      </div>

      <Panel title={CHOICES.find((c) => c.id === choice)!.title}>
        {choice === "mock" && <p className="small">No setup needed. Chat answers are scripted and nothing leaves this machine. Choose this to demo AFM without any model or key.</p>}

        {choice === "claude" && (
          <div className="stack">
            <div className="grid g2">
              <Field id="k" label="Anthropic API key" help={<>Create one at platform.claude.com → API Keys (billed per use to your Console account; a claude.ai chat subscription is separate).</>}>
                <div className="row" style={{ flexWrap: "nowrap" }}><input id="k" className="field" type={showKey ? "text" : "password"} autoComplete="off" value={form.api_key} disabled={form.use_ant_login} placeholder={keyPlaceholder} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
                  <button className="btn-ghost tiny" onClick={() => setShowKey(!showKey)} aria-label={showKey ? "Hide key" : "Show key"}>{showKey ? "hide" : "show"}</button></div>
              </Field>
              <Field id="m" label="Model" help="Any Claude model your account can use.">
                <input id="m" className="field" list="claude-models" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
                <datalist id="claude-models">{claudeModels.map((m) => <option key={m} value={m} />)}</datalist>
              </Field>
            </div>
            <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={form.use_ant_login} onChange={(e) => setForm({ ...form, use_ant_login: e.target.checked })} />Use <code>ant auth login</code> (browser sign-in on this machine) instead of a key</label>
            <div className="grid g2">
              <Field id="e" label="Effort"><select id="e" className="field" value={form.effort} onChange={(e) => setForm({ ...form, effort: e.target.value as "low" | "medium" | "high" })}><option>low</option><option>medium</option><option>high</option></select></Field>
              <Field id="t" label="Timeout (seconds)"><input id="t" className="field" type="number" min={5} max={600} value={form.timeout} onChange={(e) => setForm({ ...form, timeout: Number(e.target.value) })} /></Field>
            </div>
          </div>
        )}

        {(choice === "cloud" || choice === "local") && (
          <div className="stack">
            <div className="grid g2">
              <Field id="pre" label={choice === "cloud" ? "Provider" : "Local server"}>
                <select id="pre" className="field" value={form.preset} onChange={(e) => setPreset(e.target.value)}>
                  {(choice === "cloud" ? CLOUD : LOCAL).map((k) => <option key={k} value={k}>{presets[k]?.label}</option>)}
                </select>
              </Field>
              <Field id="url" label="Base URL" help={choice === "cloud" ? "Prefilled for the provider. Check its docs: URLs and models change." : "Address of the server on this machine (OpenAI-compatible /v1)."}>
                <input id="url" className="field mono" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
              </Field>
              <Field id="mod" label="Model name" help={p?.model_hint}>
                <div className="row" style={{ flexWrap: "nowrap" }}>
                  <input id="mod" className="field" list="srv-models" value={form.model} placeholder={p?.model_hint} onChange={(e) => setForm({ ...form, model: e.target.value })} />
                  <button className="btn" onClick={listModels} disabled={!!busy || !form.base_url}>{busy === "models" ? "…" : "List models"}</button>
                </div>
                <datalist id="srv-models">{models.map((m) => <option key={m} value={m} />)}</datalist>
              </Field>
              <Field id="k2" label={`API key${p?.key_required ? "" : " (optional)"}`} help={`Where: ${p?.key_help}`}>
                <div className="row" style={{ flexWrap: "nowrap" }}><input id="k2" className="field" type={showKey ? "text" : "password"} autoComplete="off" value={form.api_key} placeholder={keyPlaceholder} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
                  <button className="btn-ghost tiny" onClick={() => setShowKey(!showKey)} aria-label={showKey ? "Hide key" : "Show key"}>{showKey ? "hide" : "show"}</button></div>
              </Field>
              <Field id="t2" label="Timeout (seconds)" help={choice === "local" ? "Local models can be slow on CPU; 120 s or more is normal." : undefined}>
                <input id="t2" className="field" type="number" min={5} max={600} value={form.timeout} onChange={(e) => setForm({ ...form, timeout: Number(e.target.value) })} />
              </Field>
            </div>
            {choice === "local" && LOCAL_STEPS[form.preset] && (
              <div className="note small"><strong>How to start {presets[form.preset]?.label}:</strong><ol className="bullets mt-s">{LOCAL_STEPS[form.preset].map((s) => <li key={s}><code>{s}</code></li>)}</ol></div>
            )}
          </div>
        )}

        <div className="warn small mt">
          <strong>Privacy.</strong> {choice === "mock" ? "Nothing leaves this machine." : choice === "local" ? "Chat messages and the selected use-case or object fields go only to the model server at the address above (on this machine)." : `Chat messages and the selected use-case or object fields are sent to ${choice === "claude" ? "Anthropic" : presets[form.preset]?.label}. Never full repositories or other use cases.`} The key is stored in <code>backend/data/llm_settings.json</code> (git-ignored, readable only by you), never shown again and never logged. Whatever model you choose, its answers are labelled LLM-generated and cannot change AFM's rules, permissions or approvals.
        </div>

        <div className="row mt">
          {choice !== "mock" && <button className="btn" onClick={test} disabled={!!busy}>{busy === "test" ? "Testing…" : "Test connection"}</button>}
          <button className="btn-primary" onClick={save} disabled={!!busy}>{busy === "save" ? "Saving…" : "Save & use"}</button>
          {saved?.source === "ui" && <button className="btn-ghost" onClick={revert} disabled={!!busy}>Revert to backend/.env default</button>}
        </div>
        {msg && <p className={msg.ok ? "small mt" : "error-box mt"} role="status" style={msg.ok ? { color: "var(--pass)" } : undefined}>{msg.ok ? "✓ " : ""}{msg.text}</p>}
        {saved?.source === "ui" && <p className="faint tiny mt-s">Saved: {saved.provider}{saved.preset ? ` · ${saved.preset}` : ""}{saved.model ? ` · ${saved.model}` : ""}{saved.has_key ? ` · key ${saved.key_hint}` : ""}</p>}
      </Panel>
      <Plain>Cloning AFM gives you the code, never anyone else's key: each person connects their own model here (or in backend/.env). Settings can only be changed from this machine. AFM stays the decision-maker; the model is a tool.</Plain>
    </div>
  );
}
