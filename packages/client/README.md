# @reslab/api-client

Typed TypeScript client for the Resilient UAS Lab API.

`src/schema.d.ts` is generated from `packages/schemas/openapi.json` with
`openapi-typescript`; never edit it by hand. Regenerate after changing the API:

```bash
make schemas        # exports packages/schemas/openapi.json from the FastAPI app
pnpm gen:client     # regenerates src/schema.d.ts
```

`src/index.ts` wraps `openapi-fetch` and exposes the WebSocket message types used by
Mission Control. Because the frontend imports request and response types from this
package, DTO drift between backend and frontend fails the TypeScript build.
