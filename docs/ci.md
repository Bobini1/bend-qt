# Automatic builds

The `Checks` workflow runs Python syntax checks, setup examples and Bend
proofs on pushes to `main` and pull requests. The `Qt builds` workflow builds
Qt 6.10.3, 6.11.3 and 6.12.0 concurrently when generator, test or build inputs
change. Both can be started manually. A documentation-only change runs Checks.

Each version uses an Ubuntu 24.04 runner, its matching Qt binaries and pinned
PySide source revision from `generator/qt_targets.json`. LLVM 19, Bend 2.0.40
and Lean 4.34.0 are explicit dependencies. The Bend download is checksum-checked.
SDK, source and extractor caches are separated by version and build inputs.
Native compiler and analysis concurrency are each limited to two workers on
the standard 16 GB runner. The three version jobs run independently.

`scripts/ci-qt-build.py` exposes preparation, generation and verification as
separate steps. Preparation checks corresponding sources and notices before
creating the runtime manifest. Generation compiles every selected native group.
The Qt 6.12 job runs the complete canonical check, including generator and
bundled-runtime rejection controls. Older versions run fresh full-package
Core, mixed-module and fourteen-module QML consumers, plus version-specific
callback, model and protected-getter checks. Those older-version checks are
not described as the full Qt 6.12 canonical suite.

Successful validation permits creation of the package artifact. Failed jobs
still upload diagnostics where available. Artifacts are retained for seven
days. Package archives contain the bundled runtime, component licenses and
source information. Generated packages and embedded binary payloads are
excluded from the source repository.

Workflows use read-only repository permissions, immutable action revisions
and checkout without persisted credentials. They use ordinary `pull_request`
events for contributors. No job publishes to BendHub or creates a release.
Dependabot proposes updates to action revisions for review.

Standard hosted runners have a six-hour job limit and limited temporary
storage. The first clean runs establish whether the complete build fits. A
timeout or resource failure remains a failed build; it does not reduce the
required verification. Further compilation jobs must consume one shared API
and type-ID plan, preserving partition consistency.

The Action proofs cover returned-Result policy and CPS composition. Native
effects, scheduling and destruction remain integration-test obligations.
