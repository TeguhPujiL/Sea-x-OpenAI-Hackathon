import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import AuthGate from "./AuthGate";
import { readConfig } from "./api";

document.title = "ProcureMind | Case workspace";
const root = ReactDOM.createRoot(document.getElementById("root")!);
try {
  const config = readConfig(import.meta.env);
  root.render(<React.StrictMode><AuthGate config={config} /></React.StrictMode>);
} catch (error) {
  root.render(<main className="configuration-error"><h1>Workspace configuration required</h1><p role="alert">{error instanceof Error ? error.message : "Invalid API configuration."}</p><p>Set VITE_API_BASE_URL and rebuild the frontend. Never include API keys or reviewer identity.</p></main>);
}
