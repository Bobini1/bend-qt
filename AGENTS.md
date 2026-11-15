# Bend2 workspace

This workspace contains a Shiboken-based Qt binding generator and its
generated package for Bend 2.0.40.
Packages must be usable through BendHub and the standard Bend
workflow, without an external SDK, separate build tool or binding-specific
companion install.
Having Qt installed is explicitly acceptable. The active package uses
dlopen from a packaged C effect. Qt and Bend share the process main thread:
effects call Qt directly, and Qt runs Bend handlers synchronously for
signals, virtual-method overrides and stored functions. Do not continue the
rejected SDK direction. Read `generator/README.md`
and `packages/qt612/README.md` for implementation and limitations. The active
runtime is exactly Qt 6.12.0, on Linux x86-64. Each Qt runtime version gets a
matching complete package build; do not package a reduced public-ABI fallback.
Publication has not been requested.

Native libraries are not inherently excluded by BendHub packaging. A fresh
import of bend-kit-sqlite@0.1.0.1 was built with stock Bend 2.0.40 and returned
42 from an in-memory SQL query using the installed system libsqlite3. It uses
dlopen/dlsym in a packaged C effect. The Qt package works the same way through
a fresh Hub-format import with ordinary native compilation. Its C effect
renames Bend's generated `main` so Qt is torn down before the C library's exit
handlers run. The package in `packages/qt612`
is generated using the unmodified, pinned Shiboken 6.12.0 ApiExtractor.
Maintainer tooling is acceptable; consumers must not need the generator.
Discover classes from the pinned upstream PySide type systems. Keep API
coverage within PySide6's binding scope. Extended Vulkan capabilities are
archived on `archive/vulkan-expansion`; do not restore them to the active
package. Preserve Qt Quick's internally managed rendering backends. Keep module
selection in the profile and Bend conversions/policies in adapters.py. Do not
reintroduce a per-class allowlist. Public names follow `overload_names.py` and
are pinned in `generator/qt612/names.lock.json`, which only a full generation
writes. Do not hand-edit it; accept a removed name only with
`--acknowledge-removed-names` when the break is intended. Change these inputs and regenerate; do not hand
edit `qt.bend`, `qt.c` or `coverage.json` in the package. Value handles use
owning C++ copies; values referencing external data retain Qt lifetime rules. Unsupported signatures must remain visible
in the coverage report. The packaging backend must reject unsupported
relocations rather than silently depending on consumer linker flags.
Public bindings return `Action(A)`. Keep its shared implementation in
`generator/templates/action.bend` and generate `Type.with` scopes for all
class and connection handles. Scopes clean up on Done and Fail; body errors take
precedence over cleanup errors. Accept ESTALE only in scoped cleanup, while
explicit destroy/disconnect remain strict. Examples use Action blocks with
IO.try at the application boundary, so failure cannot bypass scope cleanup.

Use Ubuntu-24.04 in WSL as user `bobini`. The workspace is
`/mnt/t/Bend2/Proj1`. Read `bend guide` before writing Bend and
`bend guide effects` before changing a native effect.

Keep agreed requirements in `LAWS.bend` and their proofs in `PROOF.bend`.
Qt.Action laws import the actual standalone source in
`generator/templates/action.bend`, which is also inlined into the package.
Run `python3 scripts/check-qt-action-proofs.py --mutation-checks` to check
`--verdict`, source identity and negative controls. The native Qt check runs
this gate too. State the proof boundary explicitly: returned-Result policy
and CPS composition are proved; native effects, scheduling and destruction
still rely on integration tests. Do not weaken an agreed law to make a proof
pass. Parallelize independent work when its granularity and
balance justify it.

Run `bash scripts/check.sh` for the setup examples. Run
`bend PROOF.bend --verdict` before committing proof changes. Native effects
are outside the proof guarantee, and their runtime interface is version
specific. Recheck it before upgrading Bend.

For the active generator, use `bash scripts/setup-qt-generator.sh`, then
`python3 generator/generate.py`. Verify with
`python3 scripts/check-qt612.py --bundle --generator-checks --reject-system-qt`.
The last flag applies to this workspace's older system Qt; omit it when
system Qt matches 6.12.0. These are maintainer/test commands only.
Consumers use a Hub import and `bend main.bend -o app`. The module checker
reports foreign effects as outside its proof guarantee; the verification
script accepts only that exact diagnostic, not arbitrary checker failures.
The verification uses a temporary loopback registry and never publishes to
the public hub.

## Documentation

Use Context7 MCP for library, framework, SDK, API, CLI and cloud service
questions, including setup, configuration and library-specific debugging.
Do not use it for general programming, business logic, refactoring or code
review that does not require those APIs.

1. Start with `resolve-library-id` unless an exact `/org/project` ID was given.
2. Select the best match by name, relevance, source reputation, snippet coverage
   and score. Prefer a version-specific ID when a version was requested.
3. Call `query-docs` for one concept at a time. Split independent topics into
   separate calls.
4. Use the fetched documentation. Inspect the installed version or official
   source when the indexed docs are missing or disagree with actual behavior.
