import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient, RequestError, TransportError, type ClientConfig, type PreparedRequest } from "./api";
import { decodeCase, decodeDocument, decodeJob, decodeChallenge, decodeSimulation, decodeRepair, decodeReview, decodeAudit, object, ShapeError, uuid, type CaseInput, type DocumentType } from "./contracts";
import { loadWorkspace, listAll } from "./resources";
import { emptyIds, emptyResources, readIds, saveIds, cleanCase, terminal, recoveredStep, pollJob, hasRequiredDocuments, canReview, storageKey, type Identifiers, type Resources } from "./workflow";
import { WorkspaceView } from "./WorkspaceView";

export default function App({ config }: { config: ClientConfig }) {
  const client = useMemo(() => createClient(config), [config]);
  const [ids, setIds] = useState<Identifiers>(() => { try { return readIds(window.sessionStorage); } catch { return emptyIds(); } });
  const idsRef = useRef(ids);
  const [resources, setResources] = useState<Resources>(emptyResources);
  const resourceRef = useRef(resources);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [restoring, setRestoring] = useState(!!ids.case_id);
  const [error, setError] = useState<Error | null>(null);
  const [transportRetry, setTransportRetry] = useState<(() => void) | undefined>();
  const [pollState, setPollState] = useState<string | null>(null);
  const [storageWarning, setStorageWarning] = useState(false);
  const [proposedText, setText] = useState("");
  const textRef = useRef("");
  const [dirtyDraft, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const [conflict, setConflict] = useState<{ localText: string; expectedVersion: number; refreshed: boolean; refreshError?: string } | null>(null);
  const [demoMode, setDemoMode] = useState<boolean | null>(null);
  const [healthMessage, setHealthMessage] = useState("Checking backend…");
  const mounted = useRef(true);
  const mutation = useRef<AbortController | null>(null);
  const polling = useRef<AbortController | null>(null);
  const restoration = useRef<AbortController | null>(null);
  const changeIds = useCallback((next: Identifiers) => {
    idsRef.current = next; setIds(next);
    try { setStorageWarning(!saveIds(window.sessionStorage, next)); } catch { setStorageWarning(true); }
  }, []);
  const commit = useCallback((next: Resources) => { resourceRef.current = next; setResources(next); }, []);
  const adoptText = useCallback((value: string, dirty = false) => { textRef.current = value; setText(value); dirtyRef.current = dirty; setDirty(dirty); }, []);
  const applyLoaded = useCallback((next: Resources, nextIds: Identifiers, preserveText = false) => {
    commit(next);
    const selected = next.findings.some(f => f.finding_id === nextIds.selected_finding_id) ? nextIds.selected_finding_id : next.findings[0]?.finding_id ?? null;
    changeIds({ ...nextIds, document_ids: next.documents.map(d => d.document_id), selected_finding_id: selected });
    if (!preserveText) adoptText(next.repair?.proposed_text ?? "");
  }, [commit, changeIds, adoptText]);
  const refreshCase = useCallback(async (signal?: AbortSignal) => {
    const caseId = idsRef.current.case_id; if (!caseId) return;
    const value = await client.get(`/cases/${caseId}`, decodeCase, signal);
    if (value.case_id !== caseId) throw new ShapeError("Case response identity does not match the active case.");
    if (mounted.current) commit({ ...resourceRef.current, caseResource: value });
  }, [client, commit]);
  const refresh = useCallback(async (explicit: boolean, signal?: AbortSignal) => {
    const snapshot = { ...idsRef.current };
    const next = await loadWorkspace(client, snapshot, signal, explicit);
    if (!mounted.current || signal?.aborted) return next;
    const changedDraft = dirtyRef.current && next.repair?.version !== resourceRef.current.repair?.version;
    if (changedDraft) setConflict({ localText: textRef.current, expectedVersion: resourceRef.current.repair?.version ?? 0, refreshed: true });
    applyLoaded(next, snapshot, dirtyRef.current);
    return next;
  }, [client, applyLoaded]);
  const beginPolling = useCallback((jobId: string) => {
    polling.current?.abort();
    const controller = new AbortController(); polling.current = controller;
    setPollState("Polling analysis · next check after 1 second");
    void pollJob(signal => client.get(`/jobs/${jobId}`, decodeJob, signal), job => {
      if (job.case_id !== idsRef.current.case_id || job.job_id !== jobId) throw new ShapeError("Polled job does not belong to the active analysis.");
      commit({ ...resourceRef.current, job });
      setPollState(terminal(job.status) ? `Analysis ${job.status.toLowerCase().replaceAll("_", " ")}` : "Polling analysis · waiting for a terminal status");
    }, controller.signal).then(async () => {
      if (!controller.signal.aborted) await refresh(false, controller.signal);
    }).catch(err => {
      if (controller.signal.aborted || !mounted.current) return;
      setPollState("Analysis polling interrupted · resume to continue"); setError(err instanceof Error ? err : new Error(String(err)));
    });
  }, [client, commit, refresh]);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController(); restoration.current = controller;
    void client.get("/health", value => {
      const v = object(value); if (v.status !== "ok" || typeof v.demo_mode !== "boolean") throw new ShapeError("Unexpected foundation health response.");
      return v as { status: string; demo_mode: boolean };
    }, controller.signal).then(health => { if (!controller.signal.aborted) { setDemoMode(health.demo_mode); setHealthMessage("Backend reachable · health only"); } }).catch(() => { if (!controller.signal.aborted) setHealthMessage("Backend not reachable or health unavailable"); });
    if (idsRef.current.case_id) {
      setRestoring(true);
      void refresh(false, controller.signal).then(next => {
        if (controller.signal.aborted) return;
        setStep(recoveredStep(next)); if (next.job && !terminal(next.job.status)) beginPolling(next.job.job_id);
      }).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err : new Error(String(err))); }).finally(() => { if (!controller.signal.aborted) setRestoring(false); });
    }
    return () => { mounted.current = false; controller.abort(); polling.current?.abort(); mutation.current?.abort(); };
  }, [client, refresh, beginPolling]);

  async function execute<T>(label: string, factory: () => PreparedRequest<T> | Promise<PreparedRequest<T>>, apply: (value: T, signal: AbortSignal) => void | Promise<void>) {
    if (busyRef.current || restoring || conflict) return;
    const expectedVersion = label === "Recording internal review" ? resourceRef.current.caseResource?.version ?? 0 : resourceRef.current.repair?.version ?? resourceRef.current.caseResource?.version ?? 0;
    const localText = dirtyRef.current ? textRef.current : "";
    async function attempt(request?: PreparedRequest<T>) {
      if (busyRef.current || !mounted.current) return;
      busyRef.current = true; setBusy(label); setError(null); setTransportRetry(undefined);
      const controller = new AbortController(); mutation.current = controller;
      let received = false;
      try {
        request ??= await factory(); const value = await request.send(controller.signal); received = true;
        if (!controller.signal.aborted && mounted.current) await apply(value, controller.signal);
      } catch (err) {
        if (!mounted.current || controller.signal.aborted) return;
        const actual = err instanceof Error ? err : new Error(String(err)); setError(actual);
        if (actual instanceof TransportError && request && !received) { const sameRequest = request; setTransportRetry(() => () => { void attempt(sameRequest); }); }
        if (actual instanceof RequestError && actual.status === 409 && actual.body.code === "VERSION_CONFLICT") {
          let refreshed = false; let refreshErrorMessage: string | undefined;
          try { const next = await loadWorkspace(client, idsRef.current, controller.signal, true); applyLoaded(next, idsRef.current, true); refreshed = true; }
          catch (refreshError) { refreshErrorMessage = `Refresh failed: ${refreshError instanceof Error ? refreshError.message : String(refreshError)}`; }
          setConflict({ localText, expectedVersion, refreshed, refreshError: refreshErrorMessage });
        }
      } finally { busyRef.current = false; if (mounted.current) setBusy(null); }
    }
    await attempt();
  }
  async function refreshWorkspace() {
    if (busyRef.current || restoring) return;
    busyRef.current = true; setBusy("Refreshing resources"); setError(null); setTransportRetry(undefined);
    try { const next = await refresh(true); if (step === 5) await readAssurance(); if (conflict) setConflict({ ...conflict, refreshed: true, refreshError: undefined }); if (next.job && !terminal(next.job.status) && polling.current?.signal.aborted) beginPolling(next.job.job_id); }
    catch (err) { setError(err instanceof Error ? err : new Error(String(err))); }
    finally { busyRef.current = false; setBusy(null); }
  }
  async function readAssurance() {
    if (!idsRef.current.case_id) return;
    const caseId = idsRef.current.case_id;
    try {
      const [reviews, audit] = await Promise.all([listAll(client, `/cases/${caseId}/reviews`, decodeReview), listAll(client, `/cases/${caseId}/audit`, decodeAudit)]);
      if (reviews.some(v => v.case_id !== caseId) || audit.some(v => v.case_id !== caseId)) throw new ShapeError("Cross-case assurance response rejected.");
      if (mounted.current && idsRef.current.case_id === caseId) commit({ ...resourceRef.current, reviews, audit });
    } catch (err) { if (mounted.current && idsRef.current.case_id === caseId) setError(err instanceof Error ? err : new Error(String(err))); }
  }
  const finding = resources.findings.find(f => f.finding_id === ids.selected_finding_id);
  return <WorkspaceView resources={resources} ids={ids} step={step} busy={busy} restoring={restoring} pollState={pollState} error={error} conflict={conflict} storageWarning={storageWarning} demoMode={demoMode} healthMessage={healthMessage} meta={client.lastMeta} transportRetry={transportRetry}
    proposedText={proposedText} dirtyDraft={dirtyDraft} setProposedText={value => adoptText(value, value !== resources.repair?.proposed_text)}
    onStep={next => { setStep(next); if (next === 5) void readAssurance(); }} onRefresh={() => void refreshWorkspace()} onDismissError={() => setError(null)}
    onReset={() => {
      if ((resources.caseResource || transportRetry || dirtyDraft) && !window.confirm(`Start a new local workspace? Existing cases remain on the server. Unsaved draft text will be discarded.${transportRetry ? " The previous request has an unknown server outcome; opening a new workspace abandons its transport retry." : ""}`)) return;
      polling.current?.abort(); restoration.current?.abort(); changeIds(emptyIds()); commit(emptyResources()); adoptText(""); setConflict(null); setError(null); setTransportRetry(undefined); setStep(0); setPollState(null);
      try { window.sessionStorage.removeItem(storageKey); } catch { setStorageWarning(true); }
    }}
    onResume={caseId => {
      if (!uuid(caseId.trim())) { setError(new Error("Enter a valid UUID v4 case ID.")); return; }
      const next = { ...emptyIds(), case_id: caseId.trim() };
      void execute("Opening case", () => client.prepare("GET", `/cases/${next.case_id}`, decodeCase), async value => {
        changeIds(next); commit({ ...emptyResources(), caseResource: value });
        const jobs = await listAll(client, `/cases/${next.case_id}/jobs`, decodeJob);
        const latest = [...jobs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
        if (latest && latest.case_id !== next.case_id) throw new ShapeError("Cross-case job rejected.");
        next.analysis_job_id = latest?.job_id ?? null; changeIds(next);
        const loaded = await loadWorkspace(client, next); applyLoaded(loaded, next); setStep(recoveredStep(loaded));
        if (loaded.job && !terminal(loaded.job.status)) beginPolling(loaded.job.job_id);
      });
    }}
    onCreate={form => {
      const data = new FormData(form);
      const body: CaseInput = { title: String(data.get("title")).trim(), category: String(data.get("category")).trim(), description: String(data.get("description")).trim(), quantity: Number(data.get("quantity")), budget_ceiling_idr: Number(data.get("budget_ceiling_idr")), currency: "IDR" };
      void execute("Creating case", () => {
        if (!body.title || !body.category || !Number.isSafeInteger(body.quantity) || body.quantity < 1 || !Number.isSafeInteger(body.budget_ceiling_idr) || body.budget_ceiling_idr < 0) throw new Error("Provide a title, category, positive integer quantity, and nonnegative integer IDR budget.");
        return client.prepare("POST", "/cases", decodeCase, { body, status: 201 });
      }, value => { changeIds({ ...emptyIds(), case_id: value.case_id }); commit({ ...emptyResources(), caseResource: value }); });
    }}
    onUpload={(file: File, type: DocumentType, description: string) => {
      const caseId = ids.case_id;
      void execute("Uploading PDF", async () => {
        if (!caseId) throw new Error("Create a case before uploading.");
        if (!file.size || file.type && file.type !== "application/pdf" || await file.slice(0, 5).text() !== "%PDF-") throw new Error("Choose a nonempty PDF with a valid PDF signature. Full extraction and security checks are performed by the server.");
        const multipart = new FormData(); multipart.append("file", file); multipart.append("document_type", type); if (description.trim()) multipart.append("description", description.trim());
        return client.prepare("POST", `/cases/${caseId}/documents`, decodeDocument, { multipart, status: 201 });
      }, async (value, signal) => {
        if (value.case_id !== caseId) throw new ShapeError("Uploaded document belongs to another case.");
        const documents = [...resourceRef.current.documents.filter(d => d.document_id !== value.document_id), value];
        changeIds({ ...emptyIds(), case_id: caseId, document_ids: documents.map(d => d.document_id) });
        commit({ ...emptyResources(), caseResource: resourceRef.current.caseResource, documents }); adoptText(""); await refreshCase(signal);
      });
    }}
    onAnalyze={() => {
      if (dirtyDraft && !window.confirm("Start a new analysis and leave the unsaved repair text? Existing server records remain immutable.")) return;
      const caseId = ids.case_id; const documentIds = resources.documents.map(d => d.document_id);
      void execute("Starting analysis", () => {
        if (!caseId || !hasRequiredDocuments(resourceRef.current.documents)) throw new Error("A TOR and technical specification are required for the P0 comparison.");
        return client.prepare("POST", `/cases/${caseId}/analyses`, decodeJob, { status: 202, body: { document_ids: documentIds, analysis_types: ["REQUIREMENT_EXTRACTION", "CONTRADICTION_DETECTION"], force_reanalysis: false } });
      }, value => {
        if (value.case_id !== caseId) throw new ShapeError("Analysis belongs to another case.");
        changeIds({ ...emptyIds(), case_id: caseId, document_ids: documentIds, analysis_job_id: value.job_id });
        commit({ ...emptyResources(), caseResource: resourceRef.current.caseResource, documents: resourceRef.current.documents, job: value }); adoptText(""); setStep(1);
        if (terminal(value.status)) void refresh(false).catch(err => setError(err)); else beginPolling(value.job_id);
      });
    }}
    onRetryAnalysis={reason => {
      const job = resources.job;
      void execute("Creating retry job", () => {
        if (!job || !["FAILED", "NEEDS_REVIEW"].includes(job.status) || !reason.trim()) throw new Error("Only FAILED or NEEDS_REVIEW analyses can be retried, with a reason.");
        return client.prepare("POST", `/jobs/${job.job_id}/retries`, decodeJob, { status: 202, body: { reason: reason.trim() } });
      }, value => {
        if (value.case_id !== ids.case_id || value.job_id === job?.job_id) throw new ShapeError("Retry must create a new job in the same case.");
        changeIds({ ...emptyIds(), case_id: ids.case_id, document_ids: ids.document_ids, analysis_job_id: value.job_id });
        commit({ ...emptyResources(), caseResource: resources.caseResource, documents: resources.documents, job: value }); adoptText(""); beginPolling(value.job_id);
      });
    }}
    onResumePolling={() => { if (ids.analysis_job_id) { setError(null); beginPolling(ids.analysis_job_id); } }}
    onSelectFinding={id => {
      if (id === ids.selected_finding_id || !resources.findings.some(f => f.finding_id === id)) return;
      if (dirtyDraft && !window.confirm("Change findings and discard unsaved draft text? Existing server records remain available.")) return;
      changeIds({ ...ids, selected_finding_id: id, challenge_id: null, simulation_id: null, repair_proposal_id: null });
      commit({ ...resources, challenge: null, simulation: null, repair: null, reviews: [], audit: [] }); adoptText("");
    }}
    onChallenge={requested => void execute("Generating challenge", () => {
      if (!finding || cleanCase(resources.job) || !requested.length) throw new Error("Select a real finding and at least one evidence request.");
      return client.prepare("POST", `/cases/${ids.case_id}/challenges`, decodeChallenge, { status: 201, body: { finding_id: finding.finding_id, generation_mode: "AI_ASSISTED", requested_evidence: requested } });
    }, value => {
      if (value.case_id !== ids.case_id || value.finding_id !== finding?.finding_id) throw new ShapeError("Challenge references another case or finding.");
      changeIds({ ...idsRef.current, challenge_id: value.challenge_id }); commit({ ...resourceRef.current, challenge: value });
    })}
    onSimulate={(baseline, alternative, supplierVersion) => void execute("Running deterministic simulation", () => {
      if (!finding || !resources.challenge || !Number.isSafeInteger(baseline) || baseline < 1 || !Number.isSafeInteger(alternative) || alternative < 1 || !supplierVersion.trim()) throw new Error("Provide positive integer RAM thresholds, a supplier data version, and a challenged finding.");
      return client.prepare("POST", `/cases/${ids.case_id}/simulations`, decodeSimulation, { status: 201, body: { finding_id: finding.finding_id, baseline: { minimum_ram_gb: baseline }, alternative: { minimum_ram_gb: alternative }, supplier_data_version: supplierVersion.trim() } });
    }, value => {
      if (value.case_id !== ids.case_id || value.finding_id !== finding?.finding_id) throw new ShapeError("Simulation references another case or finding.");
      changeIds({ ...idsRef.current, simulation_id: value.simulation_id, repair_proposal_id: null }); commit({ ...resourceRef.current, simulation: value, repair: null, reviews: [], audit: [] }); adoptText("");
    })}
    onGenerateRepair={action => void execute("Generating repair draft", () => {
      if (!finding || !resources.simulation || cleanCase(resources.job)) throw new Error("A real finding and recorded simulation are required.");
      return client.prepare("POST", `/findings/${finding.finding_id}/repair-proposals`, decodeRepair, { status: 201, body: { action_type: action, simulation_id: resources.simulation.simulation_id, generation_mode: "AI_ASSISTED" } });
    }, value => {
      if (value.case_id !== ids.case_id || value.finding_id !== finding?.finding_id || value.simulation_id !== resources.simulation?.simulation_id || value.status !== "DRAFT") throw new ShapeError("A generated repair must be a DRAFT referencing the selected finding and simulation.");
      changeIds({ ...idsRef.current, repair_proposal_id: value.repair_proposal_id }); commit({ ...resourceRef.current, repair: value }); adoptText(value.proposed_text);
    })}
    onSaveRepair={submit => {
      const repair = resources.repair; const text = proposedText.trim();
      void execute(submit ? "Submitting repair draft" : "Saving repair draft", () => {
        if (!repair || repair.status !== "DRAFT" || !text) throw new Error("Only a DRAFT proposal with nonempty proposed text can be edited or submitted.");
        return client.prepare("PATCH", `/repair-proposals/${repair.repair_proposal_id}`, decodeRepair, { body: { proposed_text: text, ...(submit ? { status: "SUBMITTED" } : {}), expected_version: repair.version } });
      }, async (value, signal) => {
        if (value.case_id !== ids.case_id || value.repair_proposal_id !== repair?.repair_proposal_id || value.finding_id !== ids.selected_finding_id || value.status !== (submit ? "SUBMITTED" : "DRAFT")) throw new ShapeError("Repair update response does not match the requested resource or transition.");
        commit({ ...resourceRef.current, repair: value }); adoptText(value.proposed_text); await refreshCase(signal);
        if (submit) { setStep(5); await readAssurance(); }
      });
    }}
    onReview={(decision, reason) => void execute("Recording internal review", () => {
      if (!canReview(resourceRef.current) || !reason.trim() || reason.trim().length < 10) throw new Error("A submitted draft and meaningful decision reason are required.");
      return client.prepare("POST", `/cases/${ids.case_id}/reviews`, decodeReview, { status: 201, body: { repair_proposal_id: resources.repair!.repair_proposal_id, decision, decision_reason: reason.trim(), expected_case_version: resources.caseResource!.version } });
    }, async (value, signal) => {
      if (value.case_id !== ids.case_id || value.repair_proposal_id !== resources.repair?.repair_proposal_id) throw new ShapeError("Review references another case or repair proposal.");
      commit({ ...resourceRef.current, reviews: [...resourceRef.current.reviews, value] }); await refreshCase(signal); await readAssurance();
    })}
    onReconcile={useLocal => {
      if (!conflict?.refreshed) return;
      adoptText(useLocal ? conflict.localText : resources.repair?.proposed_text ?? "", useLocal && conflict.localText !== resources.repair?.proposed_text); setConflict(null); setError(null); setTransportRetry(undefined);
    }}
  />;
}
