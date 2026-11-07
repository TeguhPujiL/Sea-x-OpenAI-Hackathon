import type { DocumentType } from "./contracts";

// Filename suggestions do not establish content or compliance. Conflicting
// type hints deliberately leave the choice to the user.
const filenameRules: { type: DocumentType; pattern: RegExp }[] = [
  { type: "TOR", pattern: /\b(?:tor|kak)\b|\bterms? of reference\b|\bkerangka acuan(?: kerja)?\b/ },
  { type: "TECHNICAL_SPECIFICATION", pattern: /\btechnical (?:specifications?|specs?)\b|\btech specs?\b|\bspesifikasi(?: teknis)?\b|\bspecifications?\b/ },
  { type: "OWNER_COST_ESTIMATE", pattern: /\bhps\b|\bowner(?:s| s)? cost estimate\b|\bharga perkiraan sendiri\b/ },
  { type: "TECHNICAL_JUSTIFICATION", pattern: /\btechnical (?:need )?justification\b|\bjustifikasi teknis\b/ },
  { type: "SUPPLIER_QUOTATION", pattern: /\bquotations?\b|\b(?:vendor|supplier) (?:[a-z0-9]+ )?(?:quotes?|offers?|proposals?)\b|\bpenawaran(?: harga)?\b/ },
  { type: "WARRANTY_EVIDENCE", pattern: /\bwarrant(?:y|ies)\b|\bgaransi\b/ },
  { type: "EVALUATION_REPORT", pattern: /\b(?:bid )?evaluation reports?\b|\bbid evaluation\b|\blaporan evaluasi\b|\bberita acara (?:hasil )?evaluasi\b/ },
  { type: "CONTRACT", pattern: /\bpurchase orders?\b|\b(?:contract|contracts|kontrak|po|spk)\b|\bsurat (?:pesanan|perintah kerja)\b/ },
];

export function detectDocumentType(filename: string): DocumentType {
  const name = (filename.split(/[\\/]/).pop() ?? filename).normalize("NFKC")
    .replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\.[^.]+$/, "").toLowerCase()
    .replace(/[’']/g, " ").replace(/[_\-.]+/g, " ").replace(/\s+/g, " ").trim();
  const matches = filenameRules.filter(rule => rule.pattern.test(name));
  return matches.length === 1 ? matches[0].type : "OTHER";
}
