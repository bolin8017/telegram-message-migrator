---
paths:
  - "frontend/tests/**/*.ts"
---

# Frontend Test Conventions

- Use `expect.assertions(N)` in tests with `try/catch` error paths to prevent silent pass
- Vitest + Testing Library + jsdom environment
- Test stores and hooks in isolation; mock `fetch` via `vi.spyOn(globalThis, 'fetch')`
- Test setup in `frontend/tests/setup.ts` — provides jsdom environment and jest-dom matchers
