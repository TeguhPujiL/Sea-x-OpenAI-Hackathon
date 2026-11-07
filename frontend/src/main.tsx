import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <main className="mx-auto max-w-3xl p-8">
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Shared foundation</p>
      <h1 className="mt-2 text-3xl font-semibold">ProcureMind V4.1</h1>
      <p className="mt-4 text-slate-700">The application shell is ready for team integration.</p>
      <p className="mt-2 text-sm text-slate-600">Workflow features are pending implementation. Synthetic demo data only. Internal assurance is not statutory approval.</p>
    </main>
  </React.StrictMode>,
);
