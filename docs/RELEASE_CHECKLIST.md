# Release Checklist

- Run `scripts/check.sh` or `scripts\check.bat`.
- Start the app and open `http://localhost:8000/`.
- Confirm `/api/health` returns `{"ok": true}`.
- Confirm `/favicon.ico` returns HTTP 200.
- Confirm `git status --ignored --short` does not show `backend/venv`, `.venv`, `.env`, caches, or Playwright output as staged files.
- Do not commit API keys or private scripts.
