# Co-Scientist Dashboard

This app is the standalone dashboard viewer for Co-Scientist runs.

## Runtime model

1. The app serves both the UI and the read-only dashboard API.
2. The API reads only canonical artifacts under `runs/`.
3. The app does not depend on repository-local Python API services, database fallbacks, or hidden state loaders.

## Artifact sources

The server routes read from:

1. `runs/<run_id>/dashboard/SNAPSHOT.json`
2. `runs/<run_id>/state/CURRENT_STAGE.json`
3. run directory timestamps for listing fallback metadata

## Local usage

Install dependencies:

```bash
pnpm install
```

Start the dev server:

```bash
pnpm dev
```

Preview the production build:

```bash
pnpm build
pnpm preview
```

Optional environment variables:

1. `CO_SCIENTIST_RUNS_DIR`: absolute path to the `runs/` directory
2. `CO_SCIENTIST_API_BASE`: optional external API base override for development/debugging
