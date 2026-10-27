# Reviewed local Docker-to-Mac Ollama connection

Scope: this Mac's local Docker Desktop Unix context, synthetic Evaluation Sandbox only. No cloud provider, user-entered destination, hostname allowlist change or wider host listener is introduced.

The CPU sidecar design in `compose.cpu.yaml` was built and reached its genuine local model. A benign cold readiness request exceeded its 180-second bound; model load alone took 111.73 seconds while the isolated source suite was running. It is not accepted as working Docker AI. Raw observations and CPU processor metadata are retained.

The alternative was tested before forwarding source text: a disposable container fetched `http://host.docker.internal:11434/api/tags` through Docker Desktop's fixed host gateway and matched native `qwen3:4b-instruct` digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`. Native Ollama's host binding is unchanged; no `0.0.0.0` host exposure or extra host model port is requested.

Default `compose.yaml` uses a non-root, loopback-only adapter in the application's shared namespace. The existing `LocalOllamaProvider` still connects only to `127.0.0.1:11434` and still refuses proxies/redirects. The adapter:

- Has one fixed upstream: Docker Desktop's local host gateway on port 11434.
- Permits only model metadata and non-streaming chat for the exact model and digest; unrelated host model inventory is not returned.
- Refuses pull/delete/model-management paths, arbitrary URL fields, tools, images, redirects, environment proxies, unsupported methods and transfer encodings.
- Bounds request/response bytes, message count, generation/context, time and concurrent model calls; forwards no browser cookies, credentials or authorization headers.
- Publishes no model port. Only the application port is published on host `127.0.0.1`.
- Retains all application RBAC, tenant/source ACL, consent, validation, audit, idempotency and independent clinician decisions; no provider response bypasses validators.

The adapter can start while native Ollama is unavailable, so forms/catalog and honestly labelled fallback remain accessible. Model readiness and real inference are separate release gates; bridge health alone is not AI success. The host-gateway route is explicitly documented and verified here, not assumed to work on other Docker configurations. Linux/Windows or a changed native model need their own verification. CPU mode remains available separately and its failed readiness is disclosed.
