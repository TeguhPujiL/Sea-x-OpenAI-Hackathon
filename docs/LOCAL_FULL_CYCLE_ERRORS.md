# Local full-cycle test follow-up

7 November 2026, Asia/Jakarta. Changes remain local pending the user's workflow test; any later push targets fauzan.

## job.ai_execution validation message

The latest local analysis job was FAILED with AI_PROVIDER_ERROR, result=null, ai_execution.model=null and usage=null. The backend ExecutionView explicitly permits a null model when no provider response exists; requested configuration is not actual runtime provenance. The frontend AiExecution type and nested decoder incorrectly required a string, so it replaced the useful job failure/retry UI with `job.ai_execution does not match API Contract v1.1.`

The frontend now accepts an explicitly null model, shows Not returned by provider, and retains validation for missing or malformed values. It does not substitute the requested model name as if OpenAI returned it. Tests preserve the actual failed status, error code, validation counters and retryability.

Verification: 37 frontend tests passed; TypeScript checking and the production build passed. The updated frontend decoder also successfully read the user's actual persisted failed job through the running local API. No analysis retry was automatically submitted.

## Local runtime issues

The earlier audit-only instance used restricted read/review scopes and a disabled provider key; it was unsuitable for full-cycle testing. A separate real app on http://127.0.0.1:8002 uses the full required backend scopes, a dedicated .runtime/full-cycle.db and the configured key/model, with no seeded data.

That process initially inherited the execution sandbox's outbound network restriction. An unauthenticated HTTPS probe to OpenAI failed with WinError 10013 inside the sandbox and reached the API outside it (HTTP 401 as expected without credentials). The task-owned port-8002 server was restarted outside that restriction with the same database, uploads and demo identity. Connectivity is established; this is not proof of key validity, model access or a successful live analysis. The original failed job remains immutable, and the user can explicitly retry it after reloading the rebuilt frontend.

No API keys, local runtime data or unrelated config.py changes are included in this fix.
