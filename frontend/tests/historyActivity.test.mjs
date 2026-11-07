import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createClient } from "../src/api.ts";
import { CaseHistory } from "../src/CaseHistory.tsx";
import { caseHistoryPage } from "../src/history.ts";
import { latestActivity, stepActivity, loadHistoryActivity } from "../src/historyActivity.ts";
import { caseResource, auditResource, envelope, errorEnvelope, IDs } from "./fixtures.mjs";

const event = (type, time, overrides = {}) => ({ ...auditResource(), event_id: crypto.randomUUID(), event_type: type, occurred_at: time, ...overrides });
const options = { query: "", category: "", recentOnly: false, page: 1 };

test("older cases with new activity sort first using server times, including ungrouped case updates", () => {
  const older = { ...caseResource(), created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" };
  const newer = { ...older, case_id: IDs.actor, created_at: "2026-11-02T00:00:00Z", updated_at: "2026-11-02T00:00:00Z" };
  const activity = { [older.case_id]: { events: [event("CASE_UPDATED", "2026-11-07T10:15:12Z")] } };
  assert.equal(latestActivity(older, activity[older.case_id]), "2026-11-07T10:15:12Z");
  assert.equal(caseHistoryPage([newer, older], [], options, activity).items[0].case_id, older.case_id);
  assert.equal(caseHistoryPage([newer, older], [], options).items[0].case_id, newer.case_id);
});

test("step history preserves repeated actions and failure times without inventing downstream steps", () => {
  const times = ["2026-11-07T10:00:01Z", "2026-11-07T10:01:02Z", "2026-11-07T10:02:03Z"];
  const activity = { events: [event("ANALYSIS_FINISHED", times[2]), event("DOCUMENT_UPLOADED", times[1]), event("CASE_CREATED", times[0])] };
  const steps = stepActivity(activity);
  assert.equal(steps[0].events.length, 2);
  assert.equal(steps[0].latest, times[1]);
  assert.equal(steps[1].latest, times[2]);
  assert.deepEqual(steps.slice(2).map(s => s.latest), [null, null, null, null]);
  const full = stepActivity({ events: ["CHALLENGE_GENERATION_FAILED", "SIMULATION_CREATED", "REPAIR_SUBMITTED", "REVIEW_COMPLETED"].map(type => event(type, times[2])) });
  assert.deepEqual(full.slice(2).map(s => s.events.length), [1, 1, 1, 1]);
});

test("history loads every audit page, rejects cross-case events and retains readable cases on denial", async () => {
  const cases = [caseResource(), { ...caseResource(), case_id: IDs.actor }, { ...caseResource(), case_id: IDs.finding }];
  const events = Array.from({ length: 51 }, () => event("DOCUMENT_UPLOADED", "2026-11-07T10:00:01Z"));
  const paths = [];
  const client = createClient({ baseUrl: "/api/v1", development: true }, async url => {
    const path = new URL(url, "http://test"); paths.push(path.pathname + path.search);
    if (path.pathname.includes(IDs.actor)) return Response.json(errorEnvelope("FORBIDDEN", "Required scope is not granted"), { status: 403 });
    if (path.pathname.includes(IDs.finding)) return Response.json(envelope({ items: [events[0]], pagination: { limit: 50, offset: 0, total: 1 } }));
    const offset = Number(path.searchParams.get("offset"));
    return Response.json(envelope({ items: events.slice(offset, offset + 50), pagination: { limit: 50, offset, total: 51 } }));
  });
  const activity = await loadHistoryActivity(client, cases);
  assert.equal(activity[IDs.case].events.length, 51);
  assert.match(activity[IDs.actor].error, /Required scope/);
  assert.match(activity[IDs.finding].error, /Cross-case/);
  assert.equal(activity[IDs.finding].events.length, 0);
  assert.ok(paths.some(p => p.endsWith("offset=50")));
});

test("case history renders latest activity and six timestamp groups with explicit missing records", () => {
  const recorded = "2026-11-07T10:15:12Z";
  const props = { cases: [caseResource()], recentIds: [], activeId: null, loading: false, error: null, disabled: false,
    onOpen() {}, onRefresh() {}, onClose() {}, activity: { [IDs.case]: { events: [event("DOCUMENT_UPLOADED", recorded)] } } };
  const html = renderToStaticMarkup(React.createElement(CaseHistory, props));
  assert.match(html, /Latest activity/);
  assert.match(html, /dateTime="2026-11-07T10:15:12Z"/i);
  assert.match(html, /title="2026-11-07T10:15:12Z"/);
  assert.match(html, /06 · Assure/);
  assert.equal((html.match(/No action recorded/g) ?? []).length, 5);
  const unavailable = renderToStaticMarkup(React.createElement(CaseHistory, { ...props, activity: { [IDs.case]: { events: [], error: "Required scope is not granted" } } }));
  assert.match(unavailable, /Case updated/);
  assert.match(unavailable, /Step history unavailable/);
  assert.match(unavailable, /Required scope is not granted/);
});
