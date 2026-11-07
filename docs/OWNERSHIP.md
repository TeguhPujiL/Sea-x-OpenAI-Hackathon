# Ownership boundaries

| Owner | Owned scope |
| --- | --- |
| A Zaqi | frontend/src/** |
| Teguh | Core; shared contract; case/document/analysis/finding/challenge/repair; services/ai/**; services/documents/**; integration and merge |
| Aris | services/simulation/**; simulation router; fixtures; simulation tests |
| Fazhima | services/assurance/**; review/audit routers; persistence and contract regression tests |

Service paths refer to the backend application service tree when scaffolded. Shared models and schemas require Teguh review. Route modules must preserve these boundaries. Do not implement teammate-owned features as part of the shared foundation. Changes affecting routes, request fields, enums or decision semantics require a versioned approved revision and OpenAPI updates.
