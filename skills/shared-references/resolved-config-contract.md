# Resolved Config Contract

Core constraints:

1. `state/RESOLVED_RUN_CONFIG.json` is the deterministic run configuration artifact for one run.
2. Resolved config must be derived from `RUN_POLICY.yaml`, run defaults, environment-derived provider settings, plus any bounded compatibility overrides from `config.yaml` when that file exists.
3. Resolved config must expose stable mechanics sections for:
   - `generation`
   - `island`
   - `ranking`
   - `convergence`
   - `proximity`
4. Continuous numeric mechanics values must stay within documented bounds and must not be invented ad hoc by a host agent.
5. The `proximity` section freezes non-secret embedding provider settings for the run, including provider, model, dimensions, environment variable names for endpoint/key lookup, and timeout. It must not contain API key values.
6. Consumers that need effective run settings should prefer the resolved config artifact over raw defaults, current environment variables, or compatibility YAML shells.
7. Provider-specific defaults may select different non-secret environment variable names, models, and dimensions, but resolved config must still avoid storing API key values.
