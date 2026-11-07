import { uuid, type CaseResource } from "./contracts";
export const caseHistoryKey = "procuremind.case-history.ids.v1";
type HistoryStorage = Pick<Storage, "getItem" | "setItem">;
export function readCaseHistory(storage: HistoryStorage): string[] {
  try {
    const value: unknown = JSON.parse(storage.getItem(caseHistoryKey) ?? "[]");
    return Array.isArray(value) ? [...new Set(value.filter(uuid))].slice(0, 50) : [];
  } catch { return []; }
}
export function rememberCase(storage: HistoryStorage, caseId: string): { ids: string[]; saved: boolean } {
  if (!uuid(caseId)) return { ids: readCaseHistory(storage), saved: false };
  const ids = [caseId, ...readCaseHistory(storage).filter(id => id !== caseId)].slice(0, 50);
  try { storage.setItem(caseHistoryKey, JSON.stringify(ids)); return { ids, saved: true }; }
  catch { return { ids, saved: false }; }
}
export function orderCases(cases: CaseResource[], recentIds: string[]): CaseResource[] {
  const rank = new Map(recentIds.map((id, i) => [id, i]));
  return cases.filter(c => !c.deleted_at).sort((a, b) =>
    (rank.get(a.case_id) ?? Infinity) - (rank.get(b.case_id) ?? Infinity)
    || Date.parse(b.updated_at) - Date.parse(a.updated_at));
}
