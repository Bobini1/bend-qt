# Bend Qt

Qt bindings for Bend 2.0.40 on Linux x86-64. The generator uses the matching,
pinned PySide Shiboken ApiExtractor and upstream type systems. Supported build
targets are Qt 6.10.3, 6.11.3 and 6.12.0.

Each generated distribution bundles its matching Qt runtime. Consumers use a
BendHub import and `bend main.bend -o app`, without a separate binding SDK,
generator or Qt development headers. Public BendHub publication is pending.
The intended Hub name is `bend-qt-bindings`; the import alias is `Qt`.

Qt and Bend share the process main thread. Signals and virtual-method handlers
run synchronously through the generated `Action` API. Scopes release handles
and connections on success and failure. See the [API examples](packages/qt612/README.md),
[embedding model](docs/embedding.md) and [application feature tests](docs/application-features.md).

The API target is the pinned PySide binding scope for the selected modules.
Generated coverage reports keep unsupported signatures visible. Native tests
cover callbacks, ownership, dynamic properties, QML registration, custom
materials, image providers and mixed Charts/Graphs/DataVisualization consumers.
Focused passes do not establish full release readiness.

## Build and verify

Maintainers need Ubuntu 24.04, Clang/LLVM 19, Python 3.12, CMake, Ninja,
Bend 2.0.40 and Lean 4.34.0. Consumers do not need these maintainer commands.

```bash
bash scripts/setup-qt-generator.sh --qt-version 6.12.0
python3 scripts/ci-qt-build.py --qt-version 6.12.0 prepare
python3 scripts/ci-qt-build.py --qt-version 6.12.0 generate
python3 scripts/ci-qt-build.py --qt-version 6.12.0 verify
```

Preparation downloads corresponding source and gathers the original license
notices before packaging the runtime. See the [generator instructions](generator/README.md),
[distribution policy](docs/distributions.md) and [CI documentation](docs/ci.md).
Generated packages and Qt payloads are build artifacts and are not stored in Git.

## Automatic checks

GitHub Actions runs setup examples and proofs on pushes and pull requests.
Changes to bindings, tests or build configuration also start independent builds
for all three Qt versions. Each version has its own runner and cache. Manual
builds are available through the Actions page. Builds upload packages and
diagnostics; they do not publish to BendHub.

Qt 6.12 requires the complete canonical gate:

```bash
python3 scripts/check-qt612.py --bundle --generator-checks --reject-system-qt
```

The Action proofs cover returned-Result policy and CPS composition. Native
effects, scheduling and destruction rely on integration tests. A generated
package is ready only after its required fresh consumer and validation checks
pass. See [proof boundaries](docs/action-proofs.md).

## Licensing

The original generator and Bend glue use [MIT](LICENSE). Qt, PySide, Shiboken
and bundled third-party components retain their own licenses and notices.
Optional native modules and runtime assets are retained according to use;
Core-only applications must omit the optional GPL module groups. See the
[distribution policy](docs/distributions.md) for the implementation and checks.
