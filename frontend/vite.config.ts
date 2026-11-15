import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.AFM_API_URL ?? "http://127.0.0.1:8530";

export default defineConfig({
  plugins: [react()],
  server: { port: 5530, strictPort: true, proxy: { "/api": api } },
  preview: { port: 5530, strictPort: true, proxy: { "/api": api } },
});
