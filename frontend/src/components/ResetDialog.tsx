import { useRef, useState } from "react";
import { api } from "../services/api";
import { useAFM } from "../state";
import { Icon } from "./icons";

export function ResetButton({ className = "btn" }: { className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { refresh, selected, envs } = useAFM();
  const env = envs.find((e) => e.environment_id === selected);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!env) return null;
  const doReset = async () => {
    setBusy(true);
    try { setMsg((await api.reset(env.environment_id)).message); await refresh(); }
    catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <>
      <button className={className} onClick={() => { setMsg(null); ref.current?.showModal(); }}>
        <Icon name="reset" size={15} /> Reset playground
      </button>
      <dialog ref={ref} className="modal" aria-labelledby="reset-title">
        <h2 id="reset-title">Reset “{env.name}”?</h2>
        {msg ? <p className="mt dim" role="status">{msg}</p> : (
          <p className="mt dim">This restores the playground's initial scenario. It changes <strong>only this local simulated environment</strong>.
            Run history is kept, and any approval made before the reset becomes stale.</p>
        )}
        <div className="row mt-l" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={() => ref.current?.close()}>{msg ? "Close" : "Cancel"}</button>
          {!msg && <button className="btn-primary" disabled={busy} onClick={doReset}>{busy ? "Resetting…" : "Reset simulation"}</button>}
        </div>
      </dialog>
    </>
  );
}
