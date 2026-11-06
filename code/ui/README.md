# Web UI

React, Vite, TypeScript, Tailwind CSS and shadcn/ui (Base UI), with CodeMirror for SQL and YAML.

```bash
npm ci
npm run dev -- --port 5173   # port 3000 is used by the UI container in non-prod
npm run build                # typecheck + production build
npm run lint
```

## Structure

```
src/api/         Ingestion API interface, HTTP client, in-browser mock (localStorage), React Query hooks
src/lib/         Templates, naming, schedules, SQL checks, YAML output, service URLs
src/components/  Shared components; ui/ holds shadcn components
src/pages/       Jobs (list, 4-step wizard) and connections (list, form)
```

- **Pending saves:** a connection or job whose pull request is still open is listed with `pending` set. `src/components/inactive-row.tsx` draws it with Status `Inactive` (blue; merged items are `Active`, green), dimmed, with no links or buttons, and a tooltip naming the pull request ([ADR-0018](../../docs/adr/0018-saves-live-in-their-pull-request.md)); the job wizard offers merged connections only.
- **API:** `src/api/http.ts` calls the Ingestion API ([code/control-plane](../control-plane/README.md)) at `/api`, proxied by nginx in the container and by Vite in dev. The container uses it by default (`apiMode: "http"` in `config.js`).
- **Mock API:** `src/api/mock.ts` keeps everything in the browser; nothing reaches Airflow, and the header shows a "Mock API" badge. The dev server uses it unless started with `VITE_API_MODE=http` (then run the API on port 8000).
- **Templates:** forms are generated from `code/templates/sources/*.yaml` and `code/templates/sinks/*.yaml` (read at build time), so a new template needs no UI change.
- **Lightweight by design:** CodeMirror and the form pages are lazy-loaded; prefer a few lines of code over a new dependency.
- **shadcn components:** add with `npx shadcn@latest add <name>`; the CLI is not a project dependency.
