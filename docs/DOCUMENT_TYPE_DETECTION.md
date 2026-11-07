# Filename-based document types

Normal and Repair uploads now choose an existing contract document type from recognizable filename terms. Matching ignores case, separators, camel-case boundaries, directory components and filename extensions. Numeric file prefixes alone do not establish a type.

| Filename hints | Type |
| --- | --- |
| TOR, terms of reference, KAK, kerangka acuan | TOR |
| Technical specification/spec, spesifikasi teknis | TECHNICAL_SPECIFICATION |
| Owner's cost estimate, HPS, harga perkiraan sendiri | OWNER_COST_ESTIMATE |
| Technical need justification, justifikasi teknis | TECHNICAL_JUSTIFICATION |
| Quotation, vendor/supplier quote/offer/proposal, penawaran | SUPPLIER_QUOTATION |
| Warranty, garansi | WARRANTY_EVIDENCE |
| Bid evaluation/report, laporan evaluasi | EVALUATION_REPORT |
| Purchase order, contract, kontrak, PO, SPK, surat pesanan | CONTRACT |
| No match, or multiple different type matches | OTHER |

This is a filename suggestion, not content validation or a compliance decision. The normal document-type selector remains available after upload. The guessed type is captured with the original multipart request so an interrupted request reuses the same body and idempotency key. Existing documents are not reclassified retroactively. No new public field, enum value or endpoint is added.

The user requested manual testing and no test bot. Only the frontend build and local startup readiness checks accompany activation of this feature.
