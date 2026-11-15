import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.AFM_API_URL ?? "http://127.0.0.1:8530";
// The app lives under a base path (default /acm/), with /acm/home as its home page.
const raw = process.env.AFM_BASE_PATH ?? "/acm/";
const base = ("/" + raw.replace(/^\/+|\/+$/g, "") + "/").replace(/^\/\/$/, "/");
const home = base + "home";

/** "/", "/acm" and "/acm/" → "/acm/home" (runs before Vite's own middlewares). */
function homeRedirect(): Plugin {
  const go = (url: string | undefined) => url === "/" || url === base || url === base.replace(/\/$/, "");
  // must return nothing: a returned function would be treated by Vite as a "post" hook
  const use = (server: { middlewares: { use: (fn: (req: { url?: string }, res: { statusCode: number; setHeader: (k: string, v: string) => void; end: () => void }, next: () => void) => void) => unknown } }): void => {
    server.middlewares.use((req, res, next) => {
      if (base !== "/" && go(req.url)) { res.statusCode = 302; res.setHeader("Location", home); res.end(); return; }
      next();
    });
  };
  return { name: "acfm-home-redirect", configureServer: use, configurePreviewServer: use };
}

// The browser reaches the backend only through this server: /acm/api/* (and /api/*) → backend /api/*.
const proxy = {
  "/api": api,
  [`${base}api`]: { target: api, rewrite: (p: string) => p.replace(new RegExp(`^${base}api`), "/api") },
};

export default defineConfig({
  base,
  plugins: [react(), homeRedirect()],
  server: { port: 5530, strictPort: true, proxy },
  preview: { port: 5530, strictPort: true, proxy },
});
