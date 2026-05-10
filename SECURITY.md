# Security

## API Key Handling

Code Param Tuner is designed as a local-only app.

- API keys are stored by the local backend in `~/.code-param-tuner/settings.json` by default.
- The frontend does not persist API keys in `localStorage`.
- `/api/settings` never returns the raw API key; it only returns whether a key exists.
- Request and error logs do not include API keys.
- The Monaco editor runtime is vendored under `frontend/vendor/monaco-editor`, so the app does not load editor scripts from a CDN.

## Network Boundaries

- The server binds to `127.0.0.1` by default.
- CORS defaults to `http://localhost:8000` and `http://127.0.0.1:8000`.
- CSP only allows scripts, styles, fonts, images, and API calls from this local app.
- Do not expose this service on public or shared networks unless you add authentication and a deployment-grade secret store.

## Third-Party API URLs

Custom API Base URLs are supported, but the backend rejects localhost and common private IP ranges to reduce SSRF risk.

## Reporting Issues

Please avoid posting secrets, API keys, private code, or private logs in public GitHub issues.
