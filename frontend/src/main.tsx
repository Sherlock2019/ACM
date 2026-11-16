import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AFMProvider } from "./state";
import { applyTheme, initialTheme } from "./theme";
import "./styles.css";

applyTheme(initialTheme()); // before the first paint, so the page never flashes the other theme

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AFMProvider>
      <App />
    </AFMProvider>
  </StrictMode>,
);
