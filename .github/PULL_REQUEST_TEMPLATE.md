## What and why

<!-- What does this change, and why? Link the issue. -->

## How it was checked

- [ ] `make check` passes (lint, secret scan, unit tests)
- [ ] GPU path touched? `make smoke` on real hardware, numbers below (and in `CHANGELOG.md` if it is an experiment)
- [ ] `server/catalog/*.json` changed? URL, size and SHA256 come from the upstream release / revision, not from a local file
- [ ] No weights, binaries, renders, logs or secrets added (they are git-ignored; keep it that way)

## Notes for reviewers
