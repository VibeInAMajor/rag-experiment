# Standalone MAF runtime

- Run Hatch commands from this directory. Use `hatch run check`, `hatch run types` and `hatch run test` for offline checks.
- Keep agent definitions and the invocation contract provider-neutral. Provider SDKs belong in `src/agent_runtime/adapters/` and load after admission.
- Keep this package independent of Workbench, Haystack and local inference or storage services.
- The explicit smoke uses a synthetic input. Record live verification separately from offline tests.
