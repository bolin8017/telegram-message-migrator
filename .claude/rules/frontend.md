---
paths:
  - "frontend/src/**/*.{ts,tsx}"
---

# Frontend Conventions

- Never use `.catch(() => {})` on API calls — show error state in UI or `console.error`
- SSE connections (`useSSE`) must provide `onError` handler to surface disconnections
- Server-side auth verification via `/api/auth/status` — don't rely solely on Zustand store state
- Use correct backend field names: stats use `forwarded`/`failed`/`skipped` (not `errors`)
- Path alias: `@/*` maps to `./src/*`
- State split: Zustand for UI state, React Query for server cache
- DaisyUI component classes for UI elements — avoid raw Tailwind for common patterns
