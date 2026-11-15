import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AFMProvider } from "./state";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AFMProvider>
      <App />
    </AFMProvider>
  </StrictMode>,
);
