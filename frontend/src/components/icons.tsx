// One cohesive stroke icon set (24px grid, 1.75 stroke, round caps).
import type { ReactNode } from "react";

const P: Record<string, ReactNode> = {
  overview: <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>,
  identity: <><path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" /><path d="M9 12l2 2 4-4" /></>,
  environment: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8 7.5l3 8M16 7.5l-3 8M8.5 6h7" /></>,
  workspace: <><path d="M4 6h16M4 12h10M4 18h7" /><circle cx="18" cy="16" r="3" /><path d="M20.2 18.2L22 20" /></>,
  review: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
  history: <><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v4h4" /><path d="M12 7v5l3 2" /></>,
  reset: <><path d="M4 4v5h5" /><path d="M5.5 15a7 7 0 1 0 1.2-7.6L4 9" /></>,
  warehouse: <><path d="M3 9l9-5 9 5v11H3z" /><path d="M7 20v-6h10v6M7 17h10" /></>,
  product: <><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" /></>,
  inventory: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 10h16M10 4v16" /></>,
  order: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v4h4M9 12h6M9 16h6" /></>,
  dashboard: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M7 13l3-3 2 2 4-4" /></>,
  unknown: <><circle cx="12" cy="12" r="9" strokeDasharray="3 3" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.7M12 17h.01" /></>,
  reservation: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M8 3v4M16 3v4M4 10h16M9 15l2 2 4-4" /></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  check: <path d="M5 12l5 5L20 7" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  play: <path d="M7 4l13 8-13 8z" />,
  spark: <><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></>,
  lock: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
  brain: <><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3V4zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3V4z" /></>,
};

export function Icon({ name, size = 18, className = "" }: { name: keyof typeof P | string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className} style={{ flex: "none" }}>
      {P[name] ?? P.unknown}
    </svg>
  );
}

export const typeIcon = (t: string) =>
  ({ warehouse: "warehouse", product: "product", inventory_record: "inventory", customer_order: "order",
     inventory_dashboard: "dashboard", external_integration: "unknown", reservation: "reservation" } as Record<string, string>)[t] ?? "unknown";

export function Mark({ size = 34 }: { size?: number }) {
  // AFM mark: a lens (foresight) with an action point and a ripple ring.
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" style={{ flex: "none" }}>
      <rect x="1" y="1" width="38" height="38" rx="11" fill="rgba(var(--accent-rgb),.1)" stroke="rgba(var(--accent-rgb),.45)" />
      <circle cx="20" cy="20" r="11" fill="none" stroke="var(--accent)" strokeWidth="2.2" />
      <circle cx="20" cy="20" r="6" fill="none" stroke="var(--blue)" strokeWidth="1.4" strokeDasharray="2 2.4" />
      <circle cx="20" cy="20" r="2.6" fill="var(--text)" />
    </svg>
  );
}
