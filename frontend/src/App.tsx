import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient, RequestError, TransportError, type ClientConfig, type PreparedRequest } from "./api";
import { decodeCase, decodeCaseDeleted, decodeDocument, decodeDocumentDeleted, decodeJob, decodeChallenge, decodeSimulation, decodeRepair, decodeReview, decodeAudit, object, ShapeError, uuid, type CaseInput, type CaseResource, type DocumentType } from "./contracts";
import { loadWorkspace, listAll, restoreCaseResources } from "./resources";
import { emptyIds, emptyResources, readIds, saveIds, cleanCase, terminal, recoveredStep, pollJob, hasRequiredDocuments, canReview, storageKey, type Identifiers, type Resources } from "./workflow";
import { WorkspaceView } from "./WorkspaceView";
import { CaseHistory } from "./CaseHistory";
import { readCaseHistory, rememberCase, caseHistoryKey } from "./history";
import { loadHistoryActivity, type HistoryActivity } from "./historyActivity";
import { saveDocumentTypes } from "./documentTypes";
import { newUploadItems, uploadBatch, type UploadItem } from "./uploads";
import { vendorWorkflow, prepareVendorSimulationBatch, type SimulationParameters } from "./vendorWorkflowData";
import { vendorAssessment } from "./vendorAssessmentData";
import { comparisonData } from "./VendorDecisionSummary";
import { validateEvidenceSet } from "./repairEvidenceData";
import { loadFindingScenarios, prepareFindingScenarioBatch } from "./findingScenarios";

export default function App({ config, userName, onLogout }: { config: ClientConfig; userName?: string; onLogout?: () => Promise<void> }) {
  const [typeDrafts, setTypeDrafts] = useState<Record<string, DocumentType>>({});
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyCases, setHistoryCases] = useState<CaseResource[]>([]);
  const [historyActivity, setHistoryActivity] = useState<HistoryActivity>({});
  const historyRequest = useRef(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [recentIds, setRecentIds] = useState<string[]>(() => { try { return readCaseHistory(window.localStorage); } catch { return []; } });
  const [historyStorageWarning, setHistoryStorageWarning] = useState(false);
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const uploadRef = useRef<UploadItem[]>([]);
  const uploadMode = useRef<"initial" | "revision">("initial");
  const client = useMemo(() => createClient(config), [config]);
  const [ids, setIds] = useState<Identifiers>(() => { try { return readIds(window.sessionStorage); } catch { return emptyIds(); } });
  const idsRef = useRef(ids);
  const [resources, setResources] = useState<Resources>(emptyResources);
  const [scenarioAvailability, setScenarioAvailability] = useState<"loading" | "ready" | "disabled" | "error">("disabled");
  const [scenarioLoadError, setScenarioLoadError] = useState<string | null>(null);
  const [vendorPreference, setVendorPreference] = useState<{ scope: string; id: string | null }>({ scope: "", id: null });
  const preferenceScope = resources.caseResource && resources.job ? `${resources.caseResource.case_id}.${resources.job.job_id}` : "";
  useEffect(() => {
    let id: string | null = null;
    try { id = preferenceScope ? window.sessionStorage.getItem(`procuremind.vendor-preference.${preferenceScope}`) : null; } catch { /* Preference remains optional. */ }
    setVendorPreference({ scope: preferenceScope, id: id && /^[A-Z0-9]{1,40}$/.test(id) ? id : null });
  }, [preferenceScope]);
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
  const commit = useCallback((next: Resources) => {
    const current = resourceRef.current;
    if (next.findingScenarioHistory === undefined && next.caseResource?.case_id === current.caseResource?.case_id && next.job?.job_id === current.job?.job_id) {
      next = { ...next, findingScenarioHistory: current.findingScenarioHistory };
    }
    resourceRef.current = next; setResources(next);
  }, []);
  const refreshFindingScenarios = useCallback(async (signal?: AbortSignal) => {
    const snapshot = resourceRef.current, caseId = snapshot.caseResource?.case_id, jobId = snapshot.job?.job_id;
    if (!caseId || !jobId || !snapshot.job?.result) { setScenarioAvailability("disabled"); return; }
    setScenarioAvailability("loading"); setScenarioLoadError(null);
    try {
      const items = await loadFindingScenarios(client, caseId, signal);
      if (!mounted.current || signal?.aborted || resourceRef.current.caseResource?.case_id !== caseId || resourceRef.current.job?.job_id !== jobId) return;
      commit({ ...resourceRef.current, findingScenarioHistory: items.filter(item => item.analysis_job_id === jobId) });
      setScenarioAvailability("ready");
    } catch (error) {
      if (!mounted.current || signal?.aborted || resourceRef.current.caseResource?.case_id !== caseId || resourceRef.current.job?.job_id !== jobId) return;
      if (error instanceof RequestError && error.status === 404) setScenarioAvailability("disabled");
      else { setScenarioAvailability("error"); setScenarioLoadError(error instanceof Error ? error.message : "Could not load finding scenarios"); }
    }
  }, [client, commit]);
  useEffect(() => {
    const controller = new AbortController();
    void refreshFindingScenarios(controller.signal);
    return () => controller.abort();
  }, [resources.caseResource?.case_id, resources.job?.job_id, resources.job?.status, refreshFindingScenarios]);
  useEffect(() => {
    const caseId = resources.caseResource?.case_id;
    setTypeDrafts({});
    if (!caseId) return;
    try { const result = rememberCase(window.localStorage, caseId); setRecentIds(result.ids); setHistoryStorageWarning(!result.saved); }
    catch { setHistoryStorageWarning(true); }
  }, [resources.caseResource?.case_id]);
  const updateUploads = (items: UploadItem[]) => { uploadRef.current = items; setUploadItems(items); };
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

  async function execute<T>(label: string, factory: () => PreparedRequest<T> | Promise<PreparedRequest<T>>, apply: (value: T, signal: AbortSignal) => void | Promise<void>, resourceVersion?: number) {
    if (busyRef.current || restoring || conflict) return;
    const expectedVersion = resourceVersion ?? (label === "Recording internal review" ? resourceRef.current.caseResource?.version ?? 0 : resourceRef.current.repair?.version ?? resourceRef.current.caseResource?.version ?? 0);
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
        if (actual instanceof TransportError && request && !received) {
          if (request.method === "POST" && request.path.endsWith("/challenges") && !request.idempotencyKey) {
            setError(new Error("The challenge response was interrupted and its outcome is unknown. Refresh resources to inspect saved challenge history before starting another generation."));
          } else { const sameRequest = request; setTransportRetry(() => () => { void attempt(sameRequest); }); }
        }
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
    try { const next = await refresh(true); await refreshFindingScenarios(); if (step === 5) await readAssurance(); if (conflict) setConflict({ ...conflict, refreshed: true, refreshError: undefined }); if (next.job && !terminal(next.job.status) && polling.current?.signal.aborted) beginPolling(next.job.job_id); }
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
  async function loadHistory() {
    const request = ++historyRequest.current;
    setHistoryOpen(true); setHistoryLoading(true); setHistoryError(null);
    try {
      const values = await listAll(client, "/cases", decodeCase);
      const activity = await loadHistoryActivity(client, values);
      if (mounted.current && request === historyRequest.current) { setHistoryCases(values); setHistoryActivity(activity); }
    }
    catch (err) { if (mounted.current && request === historyRequest.current) setHistoryError(err instanceof Error ? err.message : "Could not load cases"); }
    finally { if (mounted.current && request === historyRequest.current) setHistoryLoading(false); }
  }
  function openCase(caseId: string) {
    if (!uuid(caseId.trim())) { setError(new Error("Enter a valid UUID v4 case ID.")); return; }
    if ((dirtyRef.current || Object.keys(typeDrafts).some(id => resourceRef.current.documents.some(d => d.document_id === id && d.document_type !== typeDrafts[id])) || uploadRef.current.some(item => item.status === "unknown")) && !window.confirm("Open another case? Unsaved text, document type selections and unresolved upload retries will be left behind. Server records remain available.")) return;
    const next = { ...emptyIds(), case_id: caseId.trim() };
    void execute("Opening case", () => client.prepare("GET", `/cases/${next.case_id}`, decodeCase), async value => {
      polling.current?.abort(); restoration.current?.abort(); setPollState(null); updateUploads([]);
      changeIds(next); commit({ ...emptyResources(), caseResource: value }); adoptText("");
      const jobs = await listAll(client, `/cases/${next.case_id}/jobs`, decodeJob);
      const latest = [...jobs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
      if (latest && latest.case_id !== next.case_id) throw new ShapeError("Cross-case job rejected.");
      next.analysis_job_id = latest?.job_id ?? null; changeIds(next);
      const restored = await restoreCaseResources(client, next); const loaded = restored.resources; applyLoaded(loaded, restored.ids); setStep(recoveredStep(loaded)); setHistoryOpen(false);
      if (loaded.job && !terminal(loaded.job.status)) beginPolling(loaded.job.job_id);
      else void readAssurance();
    });
  }
  async function runUploads(items: UploadItem[], revision = false) {
    const caseId = idsRef.current.case_id;
    if (!caseId || busyRef.current || restoring || conflict || transportRetry) return;
    if (resourceRef.current.job && !terminal(resourceRef.current.job.status)) { setError(new Error("Wait for the active analysis before uploading.")); return; }
    if (!revision && (dirtyRef.current || resourceRef.current.job) && !window.confirm("Upload new documents and start a fresh assessment workspace? Existing analysis and review records remain on the server.")) return;
    uploadMode.current = revision ? "revision" : "initial";
    busyRef.current = true; setBusy("Uploading PDFs"); setError(null);
    const controller = new AbortController(); mutation.current = controller;
    updateUploads(items);
    try {
      await uploadBatch(client, caseId, items, updateUploads, document => {
        if (!mounted.current || idsRef.current.case_id !== caseId) return;
        polling.current?.abort(); setPollState(null);
        const documents = [...resourceRef.current.documents.filter(d => d.document_id !== document.document_id), document];
        if (revision) {
          changeIds({ ...idsRef.current, document_ids: documents.map(d => d.document_id) });
          commit({ ...resourceRef.current, documents });
        } else {
          changeIds({ ...emptyIds(), case_id: caseId, document_ids: documents.map(d => d.document_id) });
          commit({ ...emptyResources(), caseResource: resourceRef.current.caseResource, documents }); adoptText("");
        }
      }, controller.signal);
      if (!controller.signal.aborted) await refreshCase(controller.signal);
    } catch (err) { if (!controller.signal.aborted) setError(err instanceof Error ? err : new Error(String(err))); }
    finally { busyRef.current = false; if (mounted.current) setBusy(null); }
  }
  async function saveTypes(preserveRevision = false) {
    if (busyRef.current || restoring || conflict || transportRetry) return;
    if (resourceRef.current.job && !terminal(resourceRef.current.job.status)) return;
    if (!preserveRevision && dirtyRef.current && !window.confirm("Saving document types leaves the unsaved repair text. Continue?")) return;
    busyRef.current = true; setBusy("Saving document types"); setError(null);
    const controller = new AbortController(); mutation.current = controller;
    try {
      await saveDocumentTypes(client, resourceRef.current.documents, typeDrafts, value => {
        const documents = resourceRef.current.documents.map(d => d.document_id === value.document_id ? value : d);
        setTypeDrafts(previous => { const next = { ...previous }; delete next[value.document_id]; return next; });
        polling.current?.abort(); setPollState(null);
        if (preserveRevision) {
          changeIds({ ...idsRef.current, document_ids: documents.map(d => d.document_id) });
          commit({ ...resourceRef.current, documents });
        } else {
          changeIds({ ...emptyIds(), case_id: value.case_id, document_ids: documents.map(d => d.document_id) });
          commit({ ...emptyResources(), caseResource: resourceRef.current.caseResource, documents }); adoptText("");
        }
      }, controller.signal);
      await refreshCase(controller.signal);
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err : new Error(String(err)));
        if (err instanceof RequestError && err.body.code === "VERSION_CONFLICT") {
          try { await refresh(true, controller.signal); } catch { /* Preserve the original conflict. */ }
        }
      }
    } finally { busyRef.current = false; if (mounted.current) setBusy(null); }
  }
  async function deleteHistoryCase(value: CaseResource) {
    if (busyRef.current || restoring || conflict || transportRetry) return;
    if (!window.confirm(`Delete case "${value.title}" from the list? Its server history is retained. Active analyses or reviewed cases cannot be deleted.`)) return;
    const reason = window.prompt("Reason for deleting this case:", "Case is no longer needed");
    if (!reason?.trim()) return;
    busyRef.current = true; setBusy("Deleting case"); setError(null);
    try {
      const result = await client.prepare("DELETE", `/cases/${value.case_id}`, decodeCaseDeleted, { body: { reason: reason.trim(), expected_version: value.version } }).send();
      if (result.case_id !== value.case_id) throw new ShapeError("Deleted case identity does not match");
      setHistoryCases(previous => previous.filter(c => c.case_id !== value.case_id));
      setRecentIds(previous => { const next = previous.filter(id => id !== value.case_id); try { window.localStorage.setItem(caseHistoryKey, JSON.stringify(next)); } catch { setHistoryStorageWarning(true); } return next; });
      if (idsRef.current.case_id === value.case_id) {
        polling.current?.abort(); restoration.current?.abort(); updateUploads([]); setTypeDrafts({});
        changeIds(emptyIds()); commit(emptyResources()); adoptText(""); setStep(0); setPollState(null);
      }
    } catch (err) { setError(err instanceof Error ? err : new Error(String(err))); if (err instanceof RequestError && err.body.code === "VERSION_CONFLICT") await loadHistory(); }
    finally { busyRef.current = false; if (mounted.current) setBusy(null); }
  }
  const hasTypeChanges = resources.documents.some(d => typeDrafts[d.document_id] && typeDrafts[d.document_id] !== d.document_type);
  function selectFinding(id: string, openChallenge = false) {
    if (!resources.findings.some(f => f.finding_id === id)) return;
    if (id !== ids.selected_finding_id) {
      if (dirtyDraft && !window.confirm("Change findings and discard unsaved draft text? Existing server records remain available.")) return;
      changeIds({ ...ids, selected_finding_id: id, challenge_id: null, simulation_id: null, repair_proposal_id: null });
      commit({ ...resources, challenge: null, simulation: null, repair: null, reviews: [], audit: [] }); adoptText("");
    }
    if (openChallenge) setStep(2);
  }
  const finding = resources.findings.find(f => f.finding_id === ids.selected_finding_id);
  function generateVendorChallenge(id: string, requested: string[]) {
    void execute("Generating vendor challenge", () => {
      const target = resourceRef.current.findings.find(f => f.finding_id === id);
      if (!target || !vendorAssessment(resourceRef.current).canChallenge(target) || !requested.length) throw new Error("Select an active verified finding and supporting evidence to request.");
      return client.prepare("POST", `/cases/${idsRef.current.case_id}/challenges`, decodeChallenge,
        { status: 201, body: { finding_id: id, generation_mode: "AI_ASSISTED", requested_evidence: requested } });
    }, value => {
      if (value.case_id !== idsRef.current.case_id || value.finding_id !== id) throw new ShapeError("Challenge references another case or finding.");
      const current = resourceRef.current;
      const challengeHistory = [...(current.challengeHistory ?? []).filter(c => c.challenge_id !== value.challenge_id), value];
      if (idsRef.current.selected_finding_id === id) changeIds({ ...idsRef.current, challenge_id: value.challenge_id });
      commit({ ...current, challengeHistory, challenge: idsRef.current.selected_finding_id === id ? value : current.challenge });
    });
  }
  function simulateVendorPoints(findingIds: string[], parameters: SimulationParameters) {
    void execute("Simulating vendor challenges", () => prepareVendorSimulationBatch(client, resourceRef.current, findingIds, parameters, (value, completed, total) => {
      if (idsRef.current.case_id !== value.case_id) throw new ShapeError("Active case changed during simulation.");
      const current = resourceRef.current;
      commit({ ...current, simulationHistory: [...(current.simulationHistory ?? []).filter(s => s.simulation_id !== value.simulation_id), value] });
      setBusy(`Simulating vendor challenges ${completed}/${total}`);
    }), () => {});
  }
  function generateFindingScenarios(findingIds: string[], assumptions: string[]) {
    void execute("Generating finding-based scenarios", () => prepareFindingScenarioBatch(client, resourceRef.current, findingIds, assumptions, (value, completed, total) => {
      if (value.case_id !== idsRef.current.case_id || value.analysis_job_id !== resourceRef.current.job?.job_id) throw new ShapeError("Scenario context changed during generation.");
      const current = resourceRef.current;
      commit({ ...current, findingScenarioHistory: [...(current.findingScenarioHistory ?? []).filter(item => item.scenario_id !== value.scenario_id), value] });
      setBusy(`Generating finding-based scenarios ${completed}/${total}`);
    }), () => {});
  }
  function useVendorSimulation(simulationId: string) {
    const current = resourceRef.current, workflow = vendorWorkflow(current);
    const simulation = workflow.simulations.find(s => s.simulation_id === simulationId);
    const target = current.findings.find(f => f.finding_id === simulation?.finding_id);
    if (!simulation || !target || !workflow.assessment.canChallenge(target)) return;
    if (dirtyRef.current && !window.confirm("Use this simulation and leave the unsaved repair text? Server history is retained.")) return;
    const challenge = workflow.challenges.filter(c => c.finding_id === target.finding_id && c.status !== "CLOSED").sort((a,b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0] ?? null;
    changeIds({ ...idsRef.current, selected_finding_id: target.finding_id, challenge_id: challenge?.challenge_id ?? null,
      simulation_id: simulation.simulation_id, repair_proposal_id: null });
    commit({ ...current, challenge, simulation, repair: null, reviews: [], audit: [] }); adoptText(""); setStep(4);
  }
  function reanalyzeRevisions(documentIds: string[]) {
    if (hasTypeChanges) { setError(new Error("Save document types before analysis.")); return; }
    const selection = validateEvidenceSet(resources, documentIds);
    if (!selection.ready) { setError(new Error(selection.errors.join(" "))); return; }
    if (dirtyDraft && !window.confirm("Analyze revised evidence and leave unsaved repair text? Original records remain preserved.")) return;
    const caseId = ids.case_id;
    void execute("Analyzing revised evidence", () => client.prepare("POST", `/cases/${caseId}/analyses`, decodeJob,
      { status: 202, body: { document_ids: documentIds, analysis_types: ["REQUIREMENT_EXTRACTION", "CONTRADICTION_DETECTION"], force_reanalysis: true } }), async (value, signal) => {
        if (value.case_id !== caseId) throw new ShapeError("Analysis belongs to another case.");
        polling.current?.abort();
        changeIds({ ...emptyIds(), case_id: caseId, document_ids: resourceRef.current.documents.map(d => d.document_id), analysis_job_id: value.job_id });
        commit({ ...emptyResources(), caseResource: resourceRef.current.caseResource, documents: resourceRef.current.documents, job: value });
        adoptText(""); setStep(1); await refreshCase(signal); beginPolling(value.job_id);
      });
  }
  return <WorkspaceView userName={userName} onLogout={onLogout ? () => {
    if ((dirtyRef.current || Object.keys(typeDrafts).some(id => resourceRef.current.documents.some(d => d.document_id === id && d.document_type !== typeDrafts[id])) || uploadRef.current.some(item => item.status === "unknown")) && !window.confirm("Sign out and leave unsaved work or unresolved upload retries?")) return;
    void onLogout().then(() => { try { window.sessionStorage.removeItem(storageKey); } catch { /* No resource content is stored. */ } }).catch(err => setError(err));
  } : undefined}
    onHistory={() => historyOpen ? setHistoryOpen(false) : void loadHistory()}
    historyPanel={historyOpen ? <CaseHistory cases={historyCases} activity={historyActivity} recentIds={recentIds} activeId={ids.case_id} loading={historyLoading} error={historyError} disabled={!!busy || restoring || !!conflict || !!transportRetry} onOpen={openCase} onDelete={value => void deleteHistoryCase(value)} onRefresh={() => void loadHistory()} onClose={() => setHistoryOpen(false)} /> : undefined}
    historyStorageWarning={historyStorageWarning} uploadItems={uploadItems}
    onRetryUploads={() => void runUploads(uploadRef.current, uploadMode.current === "revision")}
    onClearUploads={() => { if (uploadRef.current.some(item => item.status === "unknown") && !window.confirm("Clear upload status and abandon pending transport retries? Uploaded server records will be kept.")) return; updateUploads([]); }}
    onDeleteDocument={documentId => {
      const document = resourceRef.current.documents.find(d => d.document_id === documentId);
      if (!document || !window.confirm(`Remove ${document.filename} from this case? The server will preserve its history and reject removal if it is protected by an active analysis or finalized review.`)) return;
      const reason = window.prompt("Reason for removing this document:", "Uploaded the wrong document");
      if (!reason?.trim()) return;
      void execute("Removing document", () => client.prepare("DELETE", `/documents/${documentId}`, decodeDocumentDeleted, {
        body: { reason: reason.trim(), expected_version: document.version },
      }), async (value, signal) => {
        if (value.document_id !== documentId) throw new ShapeError("Deleted document identity does not match.");
        polling.current?.abort(); setPollState(null);
        const documents = resourceRef.current.documents.filter(d => d.document_id !== documentId);
        setTypeDrafts(previous => { const next = { ...previous }; delete next[documentId]; return next; });
        updateUploads(uploadRef.current.filter(item => item.document?.document_id !== documentId));
        changeIds({ ...emptyIds(), case_id: idsRef.current.case_id, document_ids: documents.map(d => d.document_id) });
        commit({ ...emptyResources(), caseResource: resourceRef.current.caseResource, documents }); adoptText(""); await refreshCase(signal);
      }, document.version);
    }}
    documentTypeDrafts={typeDrafts} onDocumentType={(documentId, type) => setTypeDrafts(previous => ({ ...previous, [documentId]: type }))}
    onSaveDocumentTypes={() => void saveTypes()} resources={resources} ids={ids} step={step} busy={busy} restoring={restoring} pollState={pollState} error={error} conflict={conflict} storageWarning={storageWarning} demoMode={demoMode} healthMessage={healthMessage} meta={client.lastMeta} transportRetry={transportRetry}
    proposedText={proposedText} dirtyDraft={dirtyDraft} setProposedText={value => adoptText(value, value !== resources.repair?.proposed_text)}
    onStep={next => { setStep(next); if (next === 5) void readAssurance(); }} onRefresh={() => void refreshWorkspace()} onDismissError={() => setError(null)}
    onReset={() => {
      if ((resources.caseResource || transportRetry || dirtyDraft || uploadItems.some(item => item.status === "unknown")) && !window.confirm(`Start a new local workspace? Existing cases remain on the server. Unsaved draft text will be discarded.${transportRetry || uploadItems.some(item => item.status === "unknown") ? " A request has an unknown server outcome; opening a new workspace abandons its transport retry." : ""}`)) return;
      polling.current?.abort(); restoration.current?.abort(); updateUploads([]); changeIds(emptyIds()); commit(emptyResources()); adoptText(""); setConflict(null); setError(null); setTransportRetry(undefined); setStep(0); setPollState(null);
      try { window.sessionStorage.removeItem(storageKey); } catch { setStorageWarning(true); }
    }}
    onResume={openCase}
    onCreate={form => {
      const data = new FormData(form);
      const body: CaseInput = { title: String(data.get("title")).trim(), category: String(data.get("category")).trim(), description: String(data.get("description")).trim(), quantity: Number(data.get("quantity")), budget_ceiling_idr: Number(data.get("budget_ceiling_idr")), currency: "IDR" };
      void execute("Creating case", () => {
        if (!body.title || !body.category || !Number.isSafeInteger(body.quantity) || body.quantity < 1 || !Number.isSafeInteger(body.budget_ceiling_idr) || body.budget_ceiling_idr < 0) throw new Error("Provide a title, category, positive integer quantity, and nonnegative integer IDR budget.");
        return client.prepare("POST", "/cases", decodeCase, { body, status: 201 });
      }, value => { changeIds({ ...emptyIds(), case_id: value.case_id }); commit({ ...emptyResources(), caseResource: value }); });
    }}
    onUpload={(files, description) => void runUploads(newUploadItems(files, description))}
    onUploadRevision={(files, description) => void runUploads(newUploadItems(files, description), true)}
    onReanalyzeRevisions={reanalyzeRevisions} onSaveRevisionDocumentTypes={() => void saveTypes(true)}
    onGenerateVendorChallenge={generateVendorChallenge} onSimulateVendorPoints={simulateVendorPoints} onUseVendorSimulation={useVendorSimulation}
    scenarioAvailability={scenarioAvailability} scenarioLoadError={scenarioLoadError} onGenerateFindingScenarios={generateFindingScenarios}
    selectedVendorId={vendorPreference.scope === preferenceScope ? vendorPreference.id : null}
    onSelectVendor={id => {
      if (!preferenceScope || !comparisonData(resourceRef.current, null).vendors.some(v => v.id === id && v.selectable)) return;
      setVendorPreference({ scope: preferenceScope, id });
      try { window.sessionStorage.setItem(`procuremind.vendor-preference.${preferenceScope}`, id); } catch { setStorageWarning(true); }
    }}
    onAnalyze={() => {
      if (hasTypeChanges) { setError(new Error("Save document types before analysis.")); return; }
      if (dirtyDraft && !window.confirm("Start a new analysis and leave the unsaved repair text? Existing server records remain immutable.")) return;
      const caseId = ids.case_id; const documentIds = resources.documents.map(d => d.document_id);
      void execute("Starting analysis", () => {
        if (resourceRef.current.documents.some(d => typeDrafts[d.document_id] && typeDrafts[d.document_id] !== d.document_type)) throw new Error("Save document types before analysis.");
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
    onSelectFinding={id => selectFinding(id)} onChallengeFinding={id => selectFinding(id, true)}
    onChallenge={requested => void execute("Generating challenge", () => {
      if (!finding || cleanCase(resources.job) || !requested.length) throw new Error("Select a real finding and at least one evidence request.");
      return client.prepare("POST", `/cases/${ids.case_id}/challenges`, decodeChallenge, { status: 201, body: { finding_id: finding.finding_id, generation_mode: "AI_ASSISTED", requested_evidence: requested } });
    }, value => {
      if (value.case_id !== ids.case_id || value.finding_id !== finding?.finding_id) throw new ShapeError("Challenge references another case or finding.");
      changeIds({ ...idsRef.current, challenge_id: value.challenge_id }); commit({ ...resourceRef.current, challenge: value,
        challengeHistory: [...(resourceRef.current.challengeHistory ?? []).filter(c => c.challenge_id !== value.challenge_id), value] });
    })}
    onSimulate={(baseline, alternative, supplierVersion) => void execute("Running deterministic simulation", () => {
      if (!finding || !resources.challenge || !Number.isSafeInteger(baseline) || baseline < 1 || !Number.isSafeInteger(alternative) || alternative < 1 || !supplierVersion.trim()) throw new Error("Provide positive integer RAM thresholds, a supplier data version, and a challenged finding.");
      return client.prepare("POST", `/cases/${ids.case_id}/simulations`, decodeSimulation, { status: 201, body: { finding_id: finding.finding_id, baseline: { minimum_ram_gb: baseline }, alternative: { minimum_ram_gb: alternative }, supplier_data_version: supplierVersion.trim() } });
    }, value => {
      if (value.case_id !== ids.case_id || value.finding_id !== finding?.finding_id) throw new ShapeError("Simulation references another case or finding.");
      changeIds({ ...idsRef.current, simulation_id: value.simulation_id, repair_proposal_id: null }); commit({ ...resourceRef.current, simulation: value, repair: null, reviews: [], audit: [],
        simulationHistory: [...(resourceRef.current.simulationHistory ?? []).filter(s => s.simulation_id !== value.simulation_id), value] }); adoptText("");
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
