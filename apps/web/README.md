# GigBid web (Next.js 16 + TypeScript)

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev      # http://localhost:3000
npm run gen:api        # regenerate lib/api-types.ts after API changes (export openapi.json first, see CI)
npm run typecheck
npx playwright install chromium && npm run test:e2e        # or PW_CHANNEL=chrome to use installed Chrome
```
Screens: login, onboarding (persona or upload, rates, Connects budget, saved searches, marketplace),
inbox (filters, scout, live progress), pipeline (kanban), job detail (requirement-to-evidence
matrix, risk, price rationale), proposal studio (claims with evidence on hover, dry-run cost,
approve / edit / reject with reason), approvals, messages, agent run viewer, analytics,
settings with the memory viewer. Pending approvals live in the backend checkpointer, so they
survive refreshes. The red banner appears when the marketplace is down; work is queued.
