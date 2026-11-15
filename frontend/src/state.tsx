import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./services/api";
import type { EnvironmentDescription, EnvironmentView, FutureAdapter, LLMStatus, ProfileResponse, RunSummary } from "./types/afm";

interface AFMState {
  profile: ProfileResponse | null; envs: EnvironmentDescription[]; future: FutureAdapter[]; views: Record<string, EnvironmentView>;
  runs: RunSummary[]; llm: LLMStatus | null; error: string | null; selected: string | null;
  select: (envId: string | null) => void; refresh: () => Promise<void>;
}
const Ctx = createContext<AFMState | null>(null);
const KEY = "afm.selectedEnvironment";

function readSelected(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export function AFMProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [envs, setEnvs] = useState<EnvironmentDescription[]>([]);
  const [future, setFuture] = useState<FutureAdapter[]>([]);
  const [views, setViews] = useState<Record<string, EnvironmentView>>({});
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [llm, setLlm] = useState<LLMStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(readSelected);

  const refresh = useCallback(async () => {
    try {
      const [p, e, r, l] = await Promise.all([api.profile(), api.environments(), api.runs(), api.llmStatus()]);
      const vs = await Promise.all(e.environments.map((x) => api.view(x.environment_id)));
      setProfile(p); setEnvs(e.environments); setFuture(e.future); setRuns(r); setLlm(l);
      setViews(Object.fromEntries(vs.map((v) => [v.environment_id, v])));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const select = useCallback((envId: string | null) => {
    setSelected(envId);
    try { if (envId) localStorage.setItem(KEY, envId); else localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
  }, []);

  const valid = selected && envs.some((x) => x.environment_id === selected) ? selected : envs.length ? null : selected;
  return <Ctx.Provider value={{ profile, envs, future, views, runs, llm, error, selected: valid, select, refresh }}>{children}</Ctx.Provider>;
}

export function useAFM() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAFM outside provider");
  return v;
}

export function useRoute(): string[] {
  const read = () => (window.location.hash.replace(/^#\/?/, "") || "why").split("/").map(decodeURIComponent);
  const [r, setR] = useState(read);
  useEffect(() => {
    const on = () => { setR(read()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return r;
}

export const go = (path: string) => { window.location.hash = `#/${path}`; };

/** objects of an environment by id, including objects only created in a prediction (e.g. new reservations) */
export function objectNames(view: EnvironmentView | undefined): Record<string, string> {
  return Object.fromEntries((view?.objects ?? []).map((o) => [o.id, o.name]));
}
