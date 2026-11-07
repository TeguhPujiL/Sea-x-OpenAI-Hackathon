# OpenAI invalid_json_schema correction

7 November 2026 (Asia/Jakarta). The local full-cycle analysis failed with AI_PROVIDER_ERROR and retryable=false because the provider rejected the request before generation.

The exact sanitized provider response was HTTP 400, code invalid_json_schema, parameter text.format.schema: `In context=('properties', 'document_id'), 'uuid4' is not a valid format.` Pydantic UUID4 emits format=uuid4; the strict Structured Outputs format accepts uuid. The configured model remained gpt-6.1-sol, and the read-only model-access check succeeded using the configured backend credential.

The provider-only schema adapter maps UUID4 fields to the supported uuid format plus an anchored UUID-v4 pattern. Analysis, challenge and repair adapters all use it. Public request/response schemas and local Pydantic UUID4 validation are unchanged, and provider output is still independently validated. No fields, enums, evidence rules or assurance decisions were changed.

Source: [OpenAI Structured Outputs supported schema constraints](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). Both string format=uuid and pattern are supported.

Executed verification:

- 94 provider/P0/decision/demo backend tests passed, including six new schema/adapter regressions. They verify all three outbound schemas, UUID-v4 restrictions, strict mode, original schema preservation and local rejection of other UUID versions.
- Before the change, a minimal synthetic request reproduced the exact 400 rejection.
- After the change, the same synthetic schema diagnostic returned status=completed, model=gpt-6.1-sol and a locally valid empty requirements/findings result. No user PDFs were sent by that diagnostic. This proves schema compatibility, not the outcome of a procurement scenario.
- The task-owned local server on port 8002 was restarted only after confirming no analysis was in flight. Its existing database, uploads, failed job history and identity were preserved. Retrying creates a new job rather than rewriting a failed record.

API credentials are loaded server-side. No credential or unrelated local config.py edit is committed with this fix. The changes remain local pending the user's full-cycle verification; any later authorized push targets fauzan.
