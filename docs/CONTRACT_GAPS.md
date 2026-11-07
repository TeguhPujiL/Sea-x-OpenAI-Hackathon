# Contract gaps

| Gap | State | Safe behavior |
| --- | --- | --- |
| Primary 39-page API Contract v1.1 missing | OPEN / BLOCKED | No exact route, enum, request, response or model lock; no feature endpoints |
| Nested envelopes and stable error codes | OPEN / PROPOSED | Current development helpers are explicitly provisional |
| Clean-case review | OPEN / PROPOSED ADDENDUM | Playbook reports review requires repair_proposal_id and no APPROVE_CASE; never invent this enum, findings or repair proposals |
| Supplier datasets differ | OPEN / PROPOSED DATA SEPARATION | Keep contract golden and negative-pack data versions separate |

The playbook reports contract totals for 50 units of 660M, 690M, 825M IDR; the separate negative pack uses 710M, 835M, 680M with different RAM mapping. Use contract fixtures for the eventual golden simulation after verifying the primary source. No fixtures or simulator are implemented here.

All corrections and extensions are PROPOSED until reviewed through a versioned contract addendum. No business status enum, including APPROVE_CASE, has been introduced.
