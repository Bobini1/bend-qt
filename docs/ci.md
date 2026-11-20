# Automatic builds

The `Checks` workflow runs Python syntax checks, setup examples and Bend
proofs on pushes to `main` and pull requests. The `Qt builds` workflow builds
Qt 6.10.3, 6.11.3 and 6.12.0 concurrently when generator, test or build inputs
change. Both can be started manually. A documentation-only change runs Checks.

Each version uses Ubuntu 24.04 runners, its matching Qt binaries and pinned
PySide source revision from `generator/qt_targets.json`. LLVM 19, Bend 2.0.40
and Lean 4.34.0 are explicit dependencies. The Bend download is checksum-checked.
The shared `.github/actions/qt-toolchain` action installs them. SDK, source and
extractor caches are separated by version and build inputs. Downloaded Ubuntu
packages are cached weekly, because the mirror has delivered them at 100 kB/s.
Each apt step has a time limit and up to three attempts, because a stalled
mirror once held a runner for its whole six hours.
Native compiler and analysis concurrency are each limited to two workers on
the standard 16 GB runner. The canonical check's timeouts, sized for a 32-core
workstation, are multiplied by six there through `BQT_CHECK_TIMEOUT_SCALE`.
Builds and checks run at a lower CPU priority than
the runner, which is exempt from the OOM killer. A check that exhausts memory
then fails with its logs, instead of the runner losing its connection.
Diagnostics include a memory log and the kernel log.

`scripts/ci-qt-build.py` exposes preparation, generation and verification as
separate steps. Preparation checks corresponding sources and notices before
creating the runtime manifest. Generation compiles every selected native group.
All preparation steps use the maintainer virtual environment, including its
pinned REUSE resolver. If GitHub's public source-tree API is rate limited,
source preparation obtains the same pinned submodule revisions through Git.
Archive and source checksums remain mandatory with either transport.
Qt 6.12 runs the complete canonical check, including generator and
bundled-runtime rejection controls. It needs more memory and time than one
standard runner has, so it runs in parts. One runner generates the package and
uploads it with its work directory. Seven runners restore that generation and
each run one part of `scripts/check-qt612.py` with `--part`. A separate runner
generates the same inputs again, in place of the in-place regeneration part.
The final job requires every part receipt for the same package, check sources
and options. The second generation's digest must match the package exactly. It
then writes the complete receipt with `--combine`. Generation does not depend
on the machine: package files name no build directory, native modules use GCC
13's C++ library, and bundled file modes come from their content. A
maintainer's generation from the same sources therefore matches CI's package.
Older versions run fresh full-package Core, mixed-module and fourteen-module
QML consumers, plus version-specific callback, model and protected-getter
checks on one runner.
Those older-version checks are not described as the full Qt 6.12 canonical suite.

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
storage. A timeout or resource failure remains a failed build; it does not
reduce the required verification. Further compilation jobs must consume one shared API
and type-ID plan, preserving partition consistency.

The Action proofs cover returned-Result policy and CPS composition. Native
effects, scheduling and destruction remain integration-test obligations.
