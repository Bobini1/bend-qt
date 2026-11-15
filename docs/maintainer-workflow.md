# Maintainer build workflow

Run these commands in Ubuntu-24.04 WSL as `bobini`, from
`/mnt/t/Bend2/Proj1`. Install the pinned maintainer tools once with
`bash scripts/setup-qt-generator.sh`. Consumers still import the package and
use `bend main.bend -o app`; they do not use this workflow.

## Iterate with explicit focused checks

Prepare the reusable Qt API metadata once:

```bash
python3 scripts/maintain-qt612.py prepare
```

This runs ApiExtractor and the metadata supplements. It does not collect the
binding API, emit the full wrappers or compile native wrappers. Its receipt
binds the API files to their extraction sources, pinned PySide checkout, Qt kit
and native toolchain.

Select the regression fixtures for the change:

```bash
python3 scripts/maintain-qt612.py focus --only properties
python3 scripts/maintain-qt612.py focus --only transition-constructors --module QtStateMachine
```

Repeat `--only` and `--module` when needed. Add `--rhi` for the existing
version-bound RHI checks. The focused checker emits and compiles its selected
bindings; it does not regenerate the production package or run every fixture.
Its result is explicitly a focused result, not final package verification.

Runtime-template and ordinary emitter edits reuse the prepared extraction.
Changes to extraction code, profiles, Qt headers or pinned upstream inputs
invalidate it. A focused invocation then asks for an explicit `prepare`; it
never silently starts production generation. `prepare` also reuses its result
when its content identities still match.
Edits to the monolithic generator driver conservatively invalidate extraction.
Changing native job counts, shard sizes, compiler memory limits, native work
location or linker selection does not invalidate extraction. Extraction still
checks ApiExtractor, its libclang/Qt dependencies, the Qt kit including moc,
headers, upstream sources and relevant environment variables. Final package
validation retains the complete native toolchain and build settings.

## Validate one stable source state

When the implementation is ready, run:

```bash
python3 scripts/maintain-qt612.py final --runtime-manifest build/qt612/runtime-release.json
```

Production generation collects the full API once. The name preflight runs
inside that same pass, before acknowledgement and native compilation. The
default reviewed-removal set is empty. Any new public-name removal stops the
build before native compilation.

For deliberately reviewed removals, supply a JSON file containing pairs:

```json
{"reviewed": [["NativeOwner", "PublicOwner.removedMethod"]]}
```

The current full-scope validation, including legacy Charts/DataVisualization
and the setup examples, can be run with:

```bash
python3 scripts/maintain-qt612.py final \
  --reviewed-removals build/full-property-coverage/reviewed-name-removals.json \
  --runtime-manifest build/qt612/runtime-release.json \
  --charts --setup-examples
```

`--charts` prepares a separately attested legacy extraction and runs the
existing fixture gate with both `--complete-module QtCharts` and
`--complete-module QtDataVisualization`. Its fixtures include `legacy-charts`
and `properties`. It remains separate from the conflicting Graphs module
family in the production profile.

The required final check remains:

```bash
python3 scripts/check-qt612.py --bundle --generator-checks --reject-system-qt
```

The workflow invokes that command without reducing its checks. Its required
deterministic regeneration is retained. Custom Qt/extractor paths are forwarded
through the checker's supported arguments; the canonical checker still uses
`clang++-19` and its default pinned PySide checkout.

Licensed distribution builds require the verified runtime manifest described in
[release inputs](distributions.md#release-inputs). The workflow passes it to
generation and canonical regeneration, and includes its runtime/source input
identities in the stage cache. The canonical checker can also recover that path
from the completed generation receipt. A focused fixture does not need release
archives and cannot establish that the distribution is ready to publish.

## Resume without repeating valid work

Repeat the same `final` command after a failure or interruption. A valid
production package is reused while a failed canonical or Charts stage runs
again. A changed validation script reruns validation without rebuilding an
unchanged package. A changed generator input, package artifact, native header,
library, toolchain or recorded symlink target invalidates the affected result.

Receipts use SHA-256 identities, not modification times. Native dependency
manifests cover compilation and linking, including library search-directory
contents and linker environment. The selected linker and the Qt kit are also
identified. Missing or inconsistent dependency evidence prevents reuse.
The Python/kernel/host identity is recorded too; a copied receipt does not
certify native tests on another host.

Canonical regeneration refreshes name-lock history and cache diagnostics.
Those updates do not by themselves invalidate an otherwise identical generated
package. The completed public-name lock, package bytes, generator sources and
dependency records remain checked.

To rerun the canonical check deliberately while retaining a valid package:

```bash
python3 scripts/maintain-qt612.py --force-stage canonical final
```

`--force` reruns all selected workflow stages. It does not delete native caches.
The native backend still decides whether individual compilation/linking units
have valid cached inputs and outputs.

`focus --jobs 2` and `final --jobs 2` also default native compilation to two
workers by setting `BQT_SHARD_JOBS=2` in child processes when it is unset.
The same `--jobs` value controls the existing fixture runtime builds. An
explicit caller `BQT_SHARD_JOBS` value takes precedence for native compilation.

The workflow defaults to `BQT_SHARD_OPERATIONS=512` and
`BQT_SHARD_KEEP_GOING=1` when those variables are unset. Explicit caller values
are preserved. `BQT_SHARD_JOBS` and `--native-jobs` remain separate controls;
their concurrency multiplies. Use the memory measurements in the native build
reports when choosing them.

## Logs and verification boundaries

The default state directory is `build/qt612-maintain`. Per-stage logs and
receipts are under `stages/`; `receipt.json` marks the requested final scope
complete only after every required stage and a final identity check pass.
Use global `--state-dir` and `--source-work` before the subcommand to select
other workflow-state or extraction locations. Production artifacts and the
canonical checker retain their established project paths.

A failed or interrupted stage retires its prior success record. Source or
dependency changes during a command prevent that result from being reused.
Focused results never set final verification complete. The workflow never
publishes to the public Hub; canonical publication tests use the existing
temporary loopback registry.

The cheap workflow regression gate is:

```bash
python3 scripts/check-qt-maintenance-workflow.py
```

It tests stage orchestration with synthetic files and subprocesses. It does not
replace native integration, the Action proofs or the full canonical check.
