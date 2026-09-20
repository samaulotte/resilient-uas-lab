## Summary

<!-- What changes and why. Link the issue if there is one. -->

## Type of change

- [ ] Bug fix
- [ ] New feature or scenario
- [ ] Schema or API change (versioned, documented in CHANGELOG.md)
- [ ] Documentation
- [ ] Build, CI or dependencies

## Checklist

- [ ] `make lint`, `make typecheck` and `make test` pass locally
- [ ] Schemas and the generated client are current (`make gen-client` produces no diff)
- [ ] New behaviour is covered by tests (unit, integration or end-to-end)
- [ ] Documentation under `docs/` reflects the change
- [ ] Container and Compose security defaults are unchanged (non-root, read-only, no Docker socket, pinned images) or the change is explained below
- [ ] No secrets, `.env` files, keys or certificates are included
- [ ] The change stays within the effects-only scope (see `docs/threat-model.md`)

## Verification

<!-- Commands you ran and their outcome. For UI changes, add a screenshot at 1440x900. -->
