# Qt binding generator

The generator reads Qt 6.12.0 headers through the unmodified Shiboken 6.12.0
ApiExtractor. A small C++ driver writes its class, method, argument and enum
model to JSON. The Python backend generates typed Bend functions, C++ wrappers
and a self-contained C effect for BendHub.

The active coverage target is documented Qt application APIs and useful binding
helpers within PySide6 6.12's selected modules. PySide's incidental exposure of
Qt-internal hooks is not automatically part of that target. The internal
`sharedPainter` hook is intentionally excluded from the public API at the user's
request. The [coverage audit](../docs/api-coverage-audit.md) distinguishes public
consumer APIs, private backend authoring and upstream unusable contracts.

The extended native Vulkan experiment is preserved on `archive/vulkan-expansion`.
Its registry-driven records, command forwarding and external resource ownership
are outside the active package and its required verification gates.

All commands in this document are maintainer commands. Consumers import the
generated package and use `bend main.bend -o app`. New distribution builds
embed their matching Qt runtime; an installed Qt is an explicit replacement
option. See [distributions](../docs/distributions.md) for selective module retention,
runtime replacement and the remaining release validation boundary.

## Setup and generation

On Ubuntu 24.04, the maintainer tools are Clang 19, CMake, Ninja, Git, Python
with venv support, `libclang-19-dev`, `llvm-19-dev`, `libstdc++-13-dev` and
`libxkbcommon-dev`. Clang otherwise uses the newest installed GCC's C++
library; native modules always use GCC 13's, Ubuntu 24.04's default, so
packages built on different machines are identical. Run from the workspace:

```bash
bash scripts/setup-qt-generator.sh
python3 scripts/ci-qt-build.py --qt-version 6.12.0 prepare
python3 scripts/ci-qt-build.py --qt-version 6.12.0 generate
python3 scripts/ci-qt-build.py --qt-version 6.12.0 verify
```

For repeated development, use the [maintainer workflow](../docs/maintainer-workflow.md)
to prepare an extraction, run explicitly selected fixtures, and resume final
generation and verification from checked stage receipts.

The runtime manifest must be prepared with matching source archives and notices
before full distribution generation. Extraction, emission and syntax modes do
not need a release manifest. See [release inputs](../docs/distributions.md#release-inputs).

For a bundled package, the final flag verifies that system Qt search paths do
not replace the bundle and that an already-loaded system Qt is rejected.
Repeat `--qt-root PATH` to test complete matching replacement runtimes and
`--reject-qt-root PATH` for incompatible replacements. Installed-runtime
maintainer fixtures retain their direct version-rejection controls.

Setup installs Qt 6.12.0's selected module archives and ICU in
`~/.cache/bend-qt-generator/Qt`, and builds the extractor under the same cache.
It selects LLVM LLD for native linking. If LLD is absent on Ubuntu, setup extracts
the distribution's `lld-19` package into the user cache without sudo. Set
`BQT_LINKER=system` to use the compiler's default linker, or provide an absolute
linker executable path. Changing linkers relinks objects without recompiling
unchanged C++ units.
It does not replace system Qt. The Shiboken source is pinned to
`f50facb83fc3dc5f3240c854668c7a6dd93871b2`. CMake verifies that commit.
The extractor links Qt Core and libclang, without building PySide or its
Python runtime. XML documentation generation is disabled.

`generate.py --help` exposes paths for the Qt kit, extractor, profile, output
and intermediate work. A different setup cache can be selected with
`BEND_QT_GENERATOR_CACHE`; pass corresponding `--qt-prefix` and `--extractor`
paths when generating or testing. All paths are passed as process arguments.
`--emit-only` writes the extraction and generated native source without compiling
or replacing the package.
Large profiles compile in separate operation units. The default builds one
unit at a time, with a 12 GiB address-space limit for each
compiler. `BQT_SHARD_JOBS=4` allows four units to compile concurrently; any
positive worker count is supported. Choose it from measured compiler memory
use and available host memory, rather than the logical CPU count alone.
Each profile compiles one complete payload for its pinned Qt runtime.
`BQT_COMPILER_AS_MIB` changes the per-process limit. These are maintainer
settings and do not change consumer commands.

`BQT_SHARD_KEEP_GOING=1` collects independent compilation failures while caching
successful units. A failed build never links or replaces package artifacts.
`native-build-progress.json` records completion and failed-unit logs in the work
directory. Interrupts still stop the active compiler processes.

Selective native modules also need semantic analysis to share mutable runtime
storage. Large inputs resolve the common declarations once, then analyze every
operation and helper body in bounded units through that precompiled header.
`BQT_STATE_JOBS` controls these workers and defaults to `BQT_SHARD_JOBS`.
`BQT_STATE_SOURCE_BYTES=0` forces this path for small regression fixtures.
References that would acquire visibility of a later declaration are rejected.

The semantic cache checks source bytes, flags, the parser binary, the analysis
implementation and every transitive header. It preprocesses each input again
before reuse, so a newly shadowing include also invalidates the cache. Changed
inputs during analysis prevent caching the result. This changes maintainer
build time without changing consumer compilation or Qt runtime behavior.

The default output is `packages/qt612/qt.bend`, `qt.c` and `coverage.json`.
Package files record Qt paths as `<QT>/include/...` and workspace paths
relative to the workspace. Generation and `scripts/check-qt-portable-package.py`
reject any package file, decoded native module or bundled runtime file that
names the build machine's Qt, workspace or home directory.
The default work directory is `build/qt612`. It retains the extracted API,
Shiboken rejection logs, generated C++, native payload and verification reports.
On WSL, native objects, precompiled headers and link intermediates for work
directories under `/mnt/<drive>` live in the Linux filesystem instead.
`native-workspace.json` records their location; logs and progress stay at the
requested workspace paths. Source paths and quoted includes retain their
original meaning. `BQT_NATIVE_WORKSPACE=off` disables relocation, while an
absolute directory selects another native cache root. Existing intermediates
are preserved; only objects with exact checked input identities are imported,
and serialized PCH paths are never rewritten.

Large constructor factories and runtime dispatch implementations compile in
separate units. Class definitions and template code still share a precompiled
header. The payload cache checks object bytes, actual linker dependencies,
library symlink targets, tool identities and loader sources before reusing a
linked and compressed ELF. `native-backend-resources.json` reports compilation,
object inspection, import validation and packaging times. These intermediates
and maintainer tools are not consumer dependencies.

Public Bend functions share internal foreign effects by their native argument
and result layouts. A shared effect is named `raw_Qt_<kinds>_to_<packer>`, for
example `raw_Qt_ws_to_word`, and takes the operation identifier and receiver
handle first. An effect that registers a handler also takes the handler's state
type `S` before them. The C effect checks the operation, receiver mode,
argument shapes and result packer before calling Qt. Sharing keeps Bend's
publication client from rereading the same C file for every public binding.
The layout inventory is recorded in `coverage.json` under `effect_transport`.

`scripts/check-qt612-effect-transport.py` exercises valid calls, a handler
round trip, and mismatched calls rejected before the native call.
`scripts/check-qt612-publication.py` runs the actual `bend --publish` client
against a temporary local registry and checks every uploaded byte. It does not
contact the public Hub or verify the public server's package-size policy.

## Runtime model

Qt and Bend share the process main thread. A Bend effect calls Qt directly and
returns Qt's answer. Qt calls Bend by running a Bend *handler* at once, on its
own stack, like a C++ slot or override. The handler re-enters the Bend
interpreter and Qt has its answer before the native call returns.

The native payload exports three functions, declared in `templates/abi.h` and
`templates/effects.c`:

- `bqt_abi_start(const BqtHost *)` starts the runtime; the program then constructs
  its application object (`QCoreApplication.new` and the GUI kinds).
  The first Qt effect calls it. It returns an error string or NULL.
- `bqt_abi_call(BqtRequest *)` runs one generated operation to completion.
  `BqtRequest` carries the operation, receiver handle, arguments, result,
  error code and message.
- `bqt_abi_stop()` tears Qt down after Bend's main returns and returns an
  exit status.

`BqtHost {argc, argv, invoke, release, sources, runnable, run, flush}` is what
the Bend side gives Qt. `invoke` runs a handler and answers done, an errno
value with its message, or that the handler waits. `release` hands a handler
back to Bend once Qt drops it. `sources`, `runnable`, `run` and `flush` let Qt
host Bend's waiting computations while a Qt event loop runs.

A handler is a closed top-level function plus a `Data` state value. Public
functions take them as template arguments, `~S: Data, ~f: S -> ... ->
Action(R)`, with the state as the last value argument. The C effect stores the
pair in a generation-checked handler table. Each invocation receives its own
copy of the state. `templates/handlers.bend` decodes Qt's request; a malformed
request fails with EINVAL.

Handler rules:

- Arguments are valid during the call. Value arguments are copies owned by the
  call; copy one again to keep it.
- A failing handler makes the Bend-started Qt operation during which Qt ran
  it fail with the same code and message. The native `CallFrame` keeps the
  first failure. An operation that only runs an event loop exits that loop at
  once.
- A handler that must return a value to Qt cannot wait. That Qt call fails
  with EWOULDBLOCK. A handler returning nothing may wait; its remainder then
  continues as an ordinary Bend computation.
- A handler may call Qt, which may run other handlers. Invocations nest.

Qt processes events only inside a Qt event loop that a Bend call starts:
`QCoreApplication.exec`, `QEventLoop.exec`, `QDialog.exec`,
`QCoreApplication.processEvents`, `Future_T.await` and similar waits. While
such a loop waits, `BendHost` in `templates/runtime.cpp` mirrors the
descriptors and nearest deadline of Bend's waiting computations into
QSocketNotifier and QTimer, and runs ready computations from event dispatch.
Spawned tasks, sleeps and sockets therefore keep running, and they may call
Qt, for example to exit the loop.

Bend runs on the main thread only. A Qt object must live there; a call on an
object that belongs to another thread fails with EXDEV. `QObject.moveToThread`
and `QObject.deleteLater` are ordinary Qt methods. A signal emitted on another
thread reaches its handler through Qt's queued delivery, when the main thread
runs a Qt event loop. A virtual method Qt calls on another thread runs on the
main thread while the calling thread waits.

Signal adapters copy temporary pointer inputs on the emitting thread, then
queue the copies for conversion and handler execution on the main thread.
Signals with mutable replies keep the emitter waiting until the main thread
has filled the reply. The main thread must be running a Qt event loop.
Queued pointer snapshots check the connection token before invoking a handler,
so disconnecting and reusing a connection slot cannot deliver an old snapshot
to a new handler.

## Upstream API discovery and Bend adaptation

`upstream.py` loads the unmodified PySide6 type systems at the pinned commit.
The profile selects Qt modules, the minimum runtime version and exceptional
method policies. There is no project class list or replacement type system.
Module dependencies and their public umbrella headers are discovered from the
upstream definitions. The extractor processes the XML, including its feature
conditions, removals and signature modifications. Python snippets are never
compiled into the Bend package.

RHI extraction follows the headers and types registered by the pinned PySide
inventory. The active package does not add unrelated native graphics APIs to
expand its coverage denominator.

The default profile selects 59 Linux modules and the version-bound RHI headers
declared by PySide. `generator/qt612-core` retains the compact Core, Gui,
Network, OpenGL, Widgets, Qml and Quick profile.
Charts and DataVisualization define C++ names that conflict with Graphs, so
their native groups set `separate_headers`: each is extracted and compiled with
its own headers, and the Bend interface names their classes `Qt.Charts.*` and
`Qt.DataVisualization.*`. They are checked with all supported methods and
override classes, plus consumer examples for chart signals and
Scatter/Bar/Surface data. Their adopting array APIs accept owning Bend lists;
the adapter copies the inputs and gives Qt independent native rows and arrays.
Run the module check on a production generation, with its public names:

```sh
python3 scripts/check-qt-callbacks.py --work build/charts-module-check \
  --name-lock generator/qt612/names.lock.json \
  --complete-module QtCharts --complete-module QtDataVisualization \
  --only legacy-charts --skip-examples
```

To add another module, install its maintainer headers and append its Qt module
name to `profile.json`. The extension test adds QtXml and uses QDomDocument
through a fresh Hub import without declaring any classes or methods.

`adapters.py` contains the Bend representation and ownership policies. The
backend handles scalar types, UTF-8 strings, checked QObject handles and copied
value handles. F64 stores all 64 IEEE-754 bits in two U32 fields, and Int64 and
UInt64 use the same storage width. QVariant has a checked owning handle with
explicit String, Bool and F64 conversions. QByteArray has UTF-8 and binary list
helpers. QByteArrayView parameters use checked QByteArray storage, and returned
views become deep copies with the same owning handle representation.
QObject classes receive checked downcasts and all handle classes receive scopes.
Value-class upcasts allocate a checked owning copy of the base value. Integer
arguments narrower than U32 are range-checked before calling Qt.

Constructors, static and instance methods, overloads and inherited methods are
generated. Inherited Bend names share native wrappers.

Signals support multiple scalar, string, value and container arguments.
`X.connect_signal(~S, ~f, object, state)` connects a typed Bend handler and
returns `Action(Connection)`. For example,
`QPushButton.connect_clicked(~S, ~f, button, state)` expects
`f: S -> Bool -> Action(Unit)`. No signal descriptor type is needed. Overloaded
signals use typed member pointers and distinct public names. Qt runs the
handler during the emission: `QPushButton.click` returns after the clicked
handler ran. QObject pointer arguments arrive as borrowed handles that follow
Qt's lifetime; null is preserved. A signal with mutable reference arguments is
handled by returning `Action(SignalReply_<types>)` with the new values.
`Connection.disconnect` and `Connection.with` end a connection;
`Runtime.liveConnections()` counts open
ones. QObject.destroyed passes an `ObjectIdentity`, the handle word of the
destroyed object. It is not a usable object handle. That connection closes
itself after its single delivery, so a later disconnect fails with ESTALE.

Bend can also declare signals on new QObjects. A closed `Signal.define`
declaration carries argument codecs and determines both the handler and emitter
types. `QObject.newWithSignals` creates an object with those real Qt signals;
`Signal.connect` and `Signal.emit` reuse the declaration. There is one
declaration type, not one public type per argument combination. See
[custom signals](../examples/qt612/custom-signals.bend).

Native primitive argument descriptors are `bool()`, `int32()`, `u32()`, `f64()`
and `string()`, called as `Qt.int32()` when the package is imported as `Qt`.
The generator also emits `Type.arg()` for selected QObject subclasses and
public, copyable Qt metatype values. `Qt.QPushButton.arg()` requires a
`Qt.QPushButton` in Bend and declares `QPushButton*` in Qt; it does not erase
the class to QObject. `Qt.QColor.arg()` similarly carries a native QColor.
`qobject()` and `variant()` alias `QObject.arg()` and `QVariant.arg()`.
`variantMap()` uses `List<&2, PairValue<String, QVariant>>`, and `variantList()`
uses `List<&2, QVariant>`. QML sees native object properties and map/list items.
The coverage report lists supported descriptors and excluded class reasons.
Custom data uses `Qt.arg(~Payload)`: its declared Bend type
determines the handler and emission types, and Qt carries the value opaquely.
It does not infer a native Qt codec or expose record fields to QML. Custom-data
retention and recovery use one opaque native metatype shared by all Bend Data
types. `QVariant.fromData(~Payload, value)` and `toData(~Payload, variant)`
pack and recover values with checked transport type identity. Copies retained
by Qt/QML hold the Bend value, including when their last copy is destroyed on
a worker thread. Actual heap drops run on the Bend thread. The pinned compiler
specializes the witness by closed type syntax: use the original Data declaration
consistently, since a type-level alias has a separate transport identity.
Signals return nothing; handlers return
`Action(Unit)`. Native Qt connections use a reference-counted dynamic slot to
copy arguments on the emitting thread and deliver Bend handlers on the main
thread. QObject arguments are borrowed, must belong to the main thread, and
are guarded against deletion before queued delivery, including object references
inside QVariantMap/Hash/List values. Null pointers are preserved. Value arguments
are callback-scoped native copies; copy them explicitly before retaining them
or waiting. Values referencing external storage retain Qt's lifetime rules.
Deletions, failed handlers, malformed input and cancelled queued deliveries
release native copies. Declarations
are fixed at object creation. Reusing a class name with different declarations
fails with EEXIST. Immutable class metadata remain cached until
native payload teardown. Class, member and argument counts follow Qt's native
metadata index range and available memory.

Runtime QObject classes use the native base's declaration function, for example
`Qt.QObject.define("Card", properties)` or
`Qt.QQuickItem.define("CardItem", properties)`. The generator supplies the
native class metadata and typed handle conversions internally. A Bend-defined
class can derive from another schema with
`Qt.ObjectType.derive(~Card(), "DetailedCard", properties)`. The declarations
return schemas; `ObjectType.new(~schema)` creates instances. See the
[QML creation example](../examples/qt612/qml-creatable.bend).

Property declarations cover every Qt property attribute, typed NOTIFY signals,
accessors, backing storage and Qt's binding engine. `withReset` and
`handleResetter` provide RESET; the metadata modifiers include revisions,
DESIGNABLE, SCRIPTABLE, STORED, USER, FINAL, REQUIRED, VIRTUAL and OVERRIDE.
`withBindable`, `bind` and `handleBinding` expose actual tracked bindings.
The native metadata writer uses Qt's true defaults for DESIGNABLE, SCRIPTABLE
and STORED. See the [property coverage table](../docs/property-system.md) and
[property examples](../examples/qt612/properties.bend).

The same argument descriptors supply properties, signals, methods and generic
QVariant boxing. They include native numeric types, public enums and flags,
typed QObject and non-QObject pointers, copied values, compiled containers,
runtime enums and arbitrary typed Bend Data. Unsupported native instantiations
remain explicit in the coverage inventory. Runtime enum metadata is available
before its QObject owner exists. Class and member names support Unicode.

Custom signal metadata uses the format emitted by Qt 6.12 moc, and dynamic
connections use public `QMetaObject::connect`. It does not import the private
QMetaObjectBuilder or QObjectPrivate connection helpers. These features work in
the complete version-pinned payload.
`Runtime.hasCustomSignals()` reports availability. This does not change the
consumer build command or require a consumer-side metadata compiler.
`scripts/check-qt-custom-signals.py` checks the real Qt/QML connections, typed
emission, handler failures and cleanup, rejects incompatible Bend programs, and
verifies that the complete payload has no private-builder imports, reusing the
native build already exercised by the focused consumers. The canonical gate includes
this check. Native metadata, activation,
scheduling and destruction remain integration-tested, outside the pure proofs.

QQmlComponent factory
results are owned by the caller, following Qt's documented contract. Other
return ownership rules use Shiboken's metadata. Explicit transfers of tracked
QObject arguments and observed native parent changes are supported.
`retention.py` derives supported QObject setter dependencies from upstream
lifetime annotations and matching getters. It also infers simple QObject
properties where upstream annotations are absent. Unsupported annotated
relationships remain explicit exclusions.

Coverage of the selected PySide6 API remains the target. The generated report distinguishes upstream
module inventory, selected classes, representation adapters, native method
counts, unsupported signatures and extractor omissions. Counts include inherited
Bend names and do not measure the percentage of the selected PySide API. Namespaces and global functions are generated too. Automatic virtual proxies,
QML composite type registration, non-QObject identities, bounded buffers and
scene-graph handlers have adapters. Remaining unsupported
signatures and lifetime policies are listed individually.
The report records excluded classes and signatures instead of hiding them.
`signature_restoration.py` also examines native declarations that PySide removed
or changed for Python. Restored declarations pass the same conversion and
lifetime rules as other methods. The name lock keeps existing Bend names.
The restoration check compiles their exact C++ signatures and tests accessible
output parameters, constants, move-only future results and retained setters.
`conversions.py` derives recursive QList/QVector/QStringList, QSet, map, hash,
multimap, multihash and pair adapters from extracted argument types. Bend lists
and PairValue records carry the data, and generated scopes release copied Qt
value elements. Input conversion completes before calling Qt. Partial output
conversion rolls back owned copies. `templates/codec.bend` supplies the shared
pure transport combinators. The report lists container instantiations and
signal payloads.
Value handles copy the C++ value; external objects referenced by a Qt value,
such as a model index, still have Qt's documented lifetime requirements.

Public effects return `Action(A)`, a scope-indexed fallible computation.
`templates/action.bend` supplies composition and cleanup using ordinary Bend
functions. The generator emits `Type.with` for every class handle and for
`Connection`, so newly discovered types receive scopes automatically. It calls
the checked release/disconnect operation and accepts ESTALE only during scope
cleanup. Scoped release preserves Qt-owned objects and defers deletion of owned
objects with tracked dependants. Explicit destroy and disconnect remain strict.
`Qt.run` opens a root resource scope; each native request carries its scope ID.
New owned handles and connections join it automatically. `Qt.scoped` opens a
nested scope. `.moveToParentScope` transfers cleanup to its parent and fails at
the root. `.detachFromScope` removes automatic cleanup, leaving the caller
responsible for release. Both require the current scope to own cleanup; they
cannot claim cleanup that belongs to an ancestor or is outside the pool. Cleanup attempts all
resources in reverse acquisition order and preserves the original body error.
The scope ID is internal; ordinary Action blocks use the same generated APIs.

Shiboken sometimes strips unknown defaulted parameters. The backend compares
its model with the original signature and excludes changed parameter lists.
Register the missing types to expose those methods; it never casts a shortened
signature to the original C++ member function type. A trailing QPrivateSignal
marker is handled by Qt's typed connect machinery and is not a Bend payload.
The extractor retains original C++ defaults separately from PySide's defaults.
Default variants supply those native defaults after N explicit arguments and
are named as ordinary overloads. Typed casts select the intended overload.
Numeric adapters also cover Qt integer aliases, WId on this
64-bit platform and 64-bit enums/flags. These include uchar, ushort, uint16_t,
qlonglong, qulonglong and ulong. Narrow inputs are range checked. Binary helpers
reuse the proved U32-list codec, with native checks for byte values from 0 to 255.

## Public names

`overload_names.py` names every generated entry per receiver class and base
name; its module documentation states the rules. In order: default variants
are ordinary overloads; a subclass declaration hides base overloads with the
same Bend arguments, as C++ name lookup does; Bend-equivalent overloads collapse
to the one C++ resolution prefers for an owned value; a group with one Bend
argument list keeps the plain name; remaining collisions spell C++ parameter
types. An overload that passed every policy but still lacks a conversion keeps
its siblings suffixed, so supporting it later adds a name instead of taking one.
Ambiguity is a generation error, never a hash.

`callback_names.py` applies the same plain-name and suffix rules to handler
families after `callbacks.prepare`: `Type.Virtual.method` (`.handle` installs
a handler), `Type.Handler.method` (the function type a method stores),
`Type.methodWithHandler` and `Type.newOverride`. Virtual overloads are never
merged, because each needs its own override. Their numeric method identifiers
stay inside native code. `overload_names.finalize` then checks ordinary and
handler names together against the lock.

`qt612/names.lock.json` pins each published name to its C++ identity and Bend
shape. It is a generation input and only a complete generation updates it,
after the package artifacts are written. New names are appended automatically.
A vanished identity becomes a tombstone that keeps its name reserved. A new
identity with exactly the removed Bend shape inherits the name, which covers
Qt's source-compatible signature replacements. Tombstones are breaking changes:
`check-overload-names.py`, part of the generator checks, fails until a
maintainer regenerates with `--acknowledge-removed-names`. Focused fixture
profiles read the lock but never write it. Deterministic regeneration must
leave the lock unchanged.

## Reference and ownership adaptation

The extractor records removed arguments, array modifications, expanded upstream
snippets and lifetime policies. Expanded snippets are inspected as metadata;
Python/C API glue is never compiled or executed. Audited `fix_bool*` and
`fix_number*` template families identify scalar output pointers. Audited typed-local output snippets also cover Qt output APIs beyond those
templates. Bounded buffer adapters validate explicit sizes; unknown allocation
and length contracts remain exclusions.

Mutable scalar, string and container references use native temporaries and
return updated values in `Outputs_*` records. The ordinary result precedes
outputs in source argument order; void results are omitted. Mutable checked
value/QObject handles preserve aliasing and update in place. Native reference
returns become copied values or checked QObject aliases. Generated scopes own
only new value copies, never mutable input handles. Output conversion can fail
after Qt has mutated native state; there is no rollback promise for that state.

The registry snapshots native QObject parents. Parented construction is already
Qt-owned, and subsequent adoption/detachment updates ownership. Reconciliation
runs before and after every Qt call. Supported explicit
transfers commit before output marshalling. `own` preserves identity when a
returned object already has a handle. Return parent-removal metadata and the
Qt-documented main-window/scroll-area take contracts restore ownership, while
native-parented return values remain Qt-owned. The PySide delegate-factory
parent-wrapper annotation is adapted separately because native createEditor
does not take ownership of its input parent. QTemporaryFile native-file factory
results are caller-owned; QDrag source/target getters remain borrowed despite
PySide wrapper-ownership annotations. Original native parameter positions are
kept separately from Bend input slots when output pointers are omitted.
Parenting cycles are checked before
supported direct parenting and generated adoption calls.

`retention.py` adapts reference-count annotations and parent-add setters when
a matching getter can confirm the stored QObject pointer. Without an annotation,
it infers an instance `setX`/`x` property only when the setter has exactly one
input, a tracked QObject pointer, and a public getter returns that pointer type.
This covers unannotated methods such as `QPushButton.setMenu`. Parent setters,
constructors and static methods are excluded from inference. Indexed setters
and other methods with multiple inputs require explicit upstream relationship
metadata; supported annotations allow one i32/u32 key in addition to the pointer.
`QThread.setEventDispatcher` has an explicit ownership adapter. Install a
parentless dispatcher before the thread has one. The adapter checks outstanding
dependencies, verifies Qt's transfer and records native thread ownership.
Generated virtual handlers still run on the Bend main thread. Ordinary operations
on the transferred dispatcher return EXDEV; Qt destroys it when its thread ends.

Getter matching is subject to semantic policies. The observer must not create
or replace native objects. `QMainWindow.setMenuBar` and `setMenuWidget` share the
noncreating `menuWidget` observer and one slot. Known lazy getters for setters
with native parent ownership, including `setStatusBar`, are not polled;
adoption preflight and parent reconciliation handle their lifetimes. Platform
screen setters do not create retention pins. Explicit null-reset policies for
text documents, graphics-widget styles and QML file selectors accept Qt's default
replacement when null is passed, while releasing the previous dependency.
`QWidget.setStyle` tracks the explicit style separately from Qt's private
stylesheet wrapper. `QCompleter.setPopup` and `QDateTimeEdit.setCalendarWidget`
have dedicated adapters for their lazy or conditional getters. These are method
policies, not a class discovery list.

Each dependency is
identified by its owner, property and optional row or column key. A replacement
updates that slot rather than accumulating references. The runtime reserves
capacity and checks cycles before calling the native setter, then uses its
getter to confirm the result. Reconciliation checks existing getters after
other native calls and retargets their slots when the observed object changes.
An unregistered observed target keeps a watch slot until its handle is registered;
a null result removes the slot.

An actual QObject parent controls ownership. A setter that stores a pointer
without reparenting instead pins the target through a retention edge. Scoped
cleanup marks a retained owned target for later collection; strict destroy
returns EBUSY if an external owner retains it or a descendant. Native QObject
destruction invalidates handles and removes dependencies. This also handles
QDrag's native ownership of its MIME data. Constructors, receiver dependencies,
non-QObject values and collections use their supported native lifetime policies.
Cases without a known ownership or observation contract remain in the coverage
report instead of assuming that a raw pointer stays alive.

Object, connection and retention tables grow together from 4,096 slots to the
16-bit token-index range. Stable deque entries keep native-call pins valid
across reentrant growth. Sidecar tables grow before any token from the new
range is issued. Capacity failure returns ENOSPC before mutating Qt; replacing
an existing slot still works at capacity. Scope resource lists grow and compact
without a separate fixed resource quota. Direct
retention cycles, including paths through native parenting, return ELOOP before
the call. Ordinary QObject parent-tree cycles return EINVAL. Cycles introduced
indirectly through native code or QML remain alive and need an explicit break.
They are not resolved by guessing a destruction order.

`bqt_abi_stop` runs after Bend's main returns. No handler runs from then on.
It closes open connections, marks owned entries for collection and releases
those whose dependencies allow it. Native QObject destruction observers remain
active while QApplication destroys its children. A final collection runs after
application destruction. A program that ends through `IO.exit` ends like a C++
program calling `exit()`: Qt is not torn down. The maintainer-only
`BEND_QT_CHECK_SHUTDOWN` diagnostic reports surviving owned entries and fails
the test if any remain.

`templates/lifetime.bend` defines the pure decisions. `lifetime.py` evaluates all
Boolean inputs with Bend and emits native tables. The proof gate checks the
shared source, evaluated metadata and emitted C++ tables. Scoped decisions leave,
delete or defer; collection requires a pending, owned and unretained entry.
Native graph traversal, parent and getter observation, table translation,
capacity handling and destruction remain integration-test concerns.

Arithmetic, comparison and assignment operators receive stable `op_*` names.
Conversions and unsupported signatures still pass through the same policy
filters. Output-bearing methods keep all public inputs explicit for now.

## Native code packaging

The maintainer compiles generated C++ using the baseline Qt headers. The
compiler handles inline methods, templates, layouts and calling conventions.
The backend verifies every imported symbol against the baseline libraries,
then links a native ELF shared object that exports only the three ABI
functions. It rejects unplanned dependencies, maintainer library paths, text
relocations and unknown relocation families. The stripped ELF is compressed
and embedded as data inside `qt.c`.

The C effect decodes the payload into a file in the per-user Qt cache, named by
the payload's content, and loads it with `dlopen`. Later starts reuse the file
while it matches its stat stamp. There is no consumer installation step, SDK or
C++ compilation. Linux's dynamic loader handles constructors, exception
unwinding, RTTI and thread-local storage. The cache entry and loaded libraries
remain held until process exit so handlers Qt holds and native finalizers
remain valid.
Dispatch translates allocation failure to ENOMEM and other native exceptions
to EFAULT; partial conversions use RAII rollback. This backend supports Linux
x86-64 only. Its cache checks the source location, compiler, flags, generated
source, every included header and object hash before reusing a native compilation.

For generated sources larger than 8 MB, `native_shards.py` splits the generated
operations into translation units and compiles a shared precompiled header.
Libclang identifies namespace declarations in the shared runtime. C++17 inline
definitions preserve one registry, one handler table and every function-local
static across every unit. The dispatcher, ABI entry points,
proxy trait section and moc output appear in one runtime unit. The backend
partially links the objects before running the normal ELF validation.

Each unit has a checked cache that includes its source, compiler flags, shared
header and all included dependencies. Changing one operation rebuilds its unit
and the combined object. Compilation failure stops peer compilers and cannot
replace the checked payload. `shards/manifest.json` records source hashes and
unit boundaries, and `native-resources.json` records actual wall time plus
separate compiler durations and memory peaks. It does not measure the combined
memory peak of concurrent compiler processes. `BQT_SHARD_OPERATIONS` sets the operation limit per unit; setting it
to zero selects the original single-unit compiler for small diagnostic runs.

Run `BQT_SHARD_JOBS=2 python3 scripts/check-qt-native-shards.py` for the native
identity and cache checks. The test also exercises exceptions and RTTI across
units, and rejects deliberate duplicated-state and invalid-compilation cases.
These are native integration checks, outside the Bend law/proof guarantee.

The first Qt effect loads Qt, rejects any version other than 6.12.0,
resolves all required symbols and starts the runtime; the program constructs
the application object.
`BEND_QT_LIBRARY` overrides the path of the Qt Widgets library it opens. The
effect renames Bend's generated `main` with a macro and calls it from its own
`main`, which then runs `bqt_abi_stop`, so Qt is torn down before the C
library's exit handlers. This depends on Bend 2.0.40 emitting `main` directly
after foreign C. Upgrading Bend requires revalidation of the effect/runtime
interface.

The default profile also includes RHI, whose headers explicitly do not promise
the ordinary Qt minor-version ABI. `abi_cohorts.py` packages one complete
payload for Qt 6.12.0. There is no reduced fallback for other runtimes.
Support for another Qt release requires another maintainer build and normal
Bend recompilation by the consumer. The loader rejects mismatched versions
before loading the native payload.
Public renderer vtables can mention RHI pointers without using their layouts.
The import audit permits those opaque pointer parameters only for symbols with
the public `Qt_6` ELF version. RHI member calls, values, references and private
helpers remain rejected. The cohort test covers both acceptance and rejection.
Newer version strings are tested for rejection; that is separate from
running against an actual newer Qt installation.

The pinned Qt3D library exports two public `QRasterMode` members under the
`Qt_6_PRIVATE_API` ELF version label. The loader preserves those symbol versions.
They must be revalidated when producing a package for another Qt runtime.

## Verification

`scripts/check-qt612.py` serves an unpublished package using the Hub manifest
format on loopback. A fresh consumer cache fetches it and stock Bend compiles
the examples. No generator or C++ build is invoked by the consumer, and ldd
must show no Qt or C++ link-time dependency.
With `--bundle`, one consumer imports the example modules and selects a fixture
at startup. Every fixture runs in a new process with its own working directory.
Separate main, Quick and Action smoke builds still check independent imports.
Omit `--bundle` to compile every example independently.
The full native harness leaves `CC` unset and uses Bend's default Clang 18 in
this workspace. Maintainer generation still uses Clang 19. `CC=gcc` is rejected
by Bend and falls back to Clang, so a run with that setting is not evidence of
GCC compatibility.

The examples exercise Unicode, inherited methods, signals, a timer, signed
values, parent destruction, handle identity/generation/type checks and signal
string copying. They check that object, connection and retention registries
return to zero live entries, apart from fixtures that deliberately keep
Qt-owned objects until application shutdown. Generation
checks also verify deterministic output and declarative profile extension.
`examples/qt612/actions.bend` checks acquisition failure, skipped operations,
success/failure cleanup, error precedence, nested cleanup order and a failing
handler that fails the Qt call during which it ran.
`examples/qt612/numbers.bend` checks exact decimal conversion, F64 arithmetic,
64-bit integer and enum round trips, alias ranges, native defaults and invalid
QVariant conversions. Container and signal examples cover nested strings,
pairs, maps/hashes with duplicates, copied values, shared Bend inputs, rejected
elements, registry exhaustion rollback, multi-argument handlers, overloaded
connections, nested lists and disconnection.
`examples/qt612/object-signals.bend` covers borrowed handle identity, nulls,
generation reuse, disconnection and scope end, mixed QObject/value arguments,
argument cleanup and stale borrowed handles.
`examples/qt612/bytes.bend` covers all byte values, binary view inputs, owning
view results, source mutation/destruction and invalid inputs.
`scripts/check-qt612-signal-native.py` compiles an emitted signal connect with
the shared runtime and checks null and live payloads, emission from another
thread, disconnection and sender destruction. It is a maintainer test and does
not change consumer requirements. The regular
examples use Action blocks and generated scopes with one outer IO.try.
`examples/qt612/quick.bend` loads a Qt Quick window from QML, receives a Unicode
signal and verifies exact qreal bits through QVariant and a QML property. It
reads the rendered image and checks its size and background pixels. The tests
use offscreen Qt with its software renderer. GPU rendering and interactive
WSLg behavior are not covered by these tests.

`scripts/check-qt-callbacks.py` builds the handler examples and fixtures
against a focused profile. They cover handlers that run during the emitting
call, nested Qt calls, handler failures, handlers run by nested event loops,
waits rejected where Qt needs an answer, mutable reference replies, factory and
retained pointer results, and module-specific virtuals. `--only NAME` selects
fixtures.

[Retention tests](../examples/qt612/retention.bend) exercise deferral, replacement,
keyed dependencies, strict destruction, cycle checks and capacity exhaustion.
[Parent and retention tests](../examples/qt612/retention-parent.bend) exercise
setter ownership, native deletion of retained objects, lazy-getter regressions
and null resets that install Qt defaults.
[Shutdown tests](../examples/qt612/shutdown-retention.bend) keep a model and menu
pending behind application-owned retainers, then require the native
`QT612_SHUTDOWN_OK` marker after QApplication destruction.

`LAWS.bend` and `PROOF.bend` prove 102 laws, including 101 Qt laws of the
actual Action, Codec and Lifetime sources. They cover scoped composition,
returned-error precedence, pure transport round trips, ownership, retention
and admission decisions. `bend PROOF.bend --verdict` reports ALL PROOFS CHECK.
The native harness runs `scripts/check-qt-action-proofs.py --mutation-checks`,
which checks the shared packaged sources and rejects 64 deliberately
incorrect, type-correct implementations before building consumers. Use
`--example actions` for focused native scope tests. See
[the proof boundary](../docs/action-proofs.md).

Bend's module checker reports that foreign effects are outside its proof
guarantee. The check script accepts only that exact diagnostic and rejects
other errors. The generated native code has not been formally verified.

Shiboken's source and Qt headers retain their upstream licenses. The extractor
is built from its external pinned checkout; no upstream source files are
vendored here. Generated native payloads include Qt inline/template compiler output.
No public Hub publication is performed by setup, generation or verification.

## Expanded adapters

`native_objects.py` measures copyability, abstractness and destructor access
against the actual Qt headers. Non-QObject identities use generated base-pointer
casts and observable derived destructors where the C++ contract permits them.
Classes with inaccessible destructors can expose borrowed handles. They cannot
be allocated or destroyed through an inaccessible base destructor.

`native_lifetimes.py` covers item/model trees, take operations and observed
native deletion. `retention.py` covers constructors, receiver dependencies,
collections, streams, painter devices and visual parents. Unknown native-created
aliases without a reliable deletion observer remain rejected.

`child_lookup.py` replaces PySide's Python-only `findChild` and `findChildren`,
which take a Python type object. It adds static `findIn`, `findAllIn` and
`findAllMatchingIn` entries to every selected QObject class. They pass through
the ordinary pipeline; only the native call expression (`native_call`)
instantiates Qt's member templates. Classes without `Q_OBJECT` are matched by
`dynamic_cast`, because Qt's lookup compares their base class's metaobject.

`qt_objects.py` builds runtime QObject schemas using the existing native
subclass proxies. Typed Property, Signal and Method descriptors provide native
metadata, named invokables, storage, notify signals and optional Bend accessors.
Native bases retain their inherited properties, methods and virtual handlers.
Dynamic pointer metatypes preserve concrete Bend class identity. Metadata uses
the Qt 6 moc format and public connection ABI. Immutable definitions remain
valid for process-lifetime Qt/QML caches.
Creatable QML classes use the generated proxy's placement constructor, native
size and interface offsets. A default constructor supplies the ordinary path;
`Qml.handleConstructor` can select another constructor through `Base.newAs`.
QQmlPropertyMap constructs its open metadata on the runtime schema. Qt cannot
use that open metadata as QML extension metadata; registration rejects that
combination. Typed initializers run before QML bindings. Attached
and extension factories receive their target and return typed QObject instances,
which become target children before the callback pool closes. Distinct factory
identities use W^X closure pages on the supported Linux x86-64 target, with
separate writable contexts and immutable executable code. There is no fixed
per-signature type or factory pool. QML singleton registrations retain state until their
engines end, and transfer factory-created objects to engine ownership before
the callback scope closes. The old numeric bridge lives under Internal.Qml.
Consumers need no moc, source generator or SDK.

`representations.py` discovers concrete shared-pointer and future carriers.
Shared carriers preserve their C++ control blocks and reject independent raw
pointee deletion. `futures.py` supplies nonblocking result access and
`Future_T.await`, which runs a Qt event loop until the future finishes.
`QThreadPool.awaitDone` and `awaitDoneFor` similarly pump Qt/Bend events while
pool jobs finish; Qt's native `waitForDone` retains its blocking semantics.
Standard optional values map to Maybe. Character, Latin-1, binary
standard strings, chrono durations, matrices and QJsonObject conversions are
also generated where their storage contracts are known.

`Future_T.takeResult` consumes completed results, including move-only values.
Its admission table comes from the proved `Lifetime.future_take` function.
Native tests check unfinished computations, stored exceptions, shared aliases,
watcher aliases and repeated consumption. The proof establishes the admission
decision from the supplied state, while the tests check Qt's shared state and
the resulting destruction.

## Handlers

`callbacks.py` discovers overridable virtuals and generates typed argument
records (`CallbackArgs_*`) and reply codecs. `X.newOverride(args...)` creates an
override object. `D.Virtual.method.handle(~S, ~f, obj, state)` installs the
handler for one virtual method on it, where `D` declares the method; installing
again replaces it. A virtual without a handler runs the C++ base
implementation, and so does a handler that fails with 38
(`Virtual.base(R)`). A pure virtual without a handler makes the current Qt
operation fail with ENOSYS. Receivers and borrowed arguments are pinned for
the duration of the call. Mutable references return a `CallbackReply_*` record
and commit only after the entire reply validates. Native factories transfer
ownership only under an explicit contract; borrowed pointer replies retain
tracked objects until the proxy is destroyed, and `CallbackResult_*` codecs
release the handles of retained results.

`callback_functions.py` restores typed `std::function` parameters from upstream
signatures and snippets. `X.methodWithHandler(~S, ~f, self, args..., state)`
passes a handler where Qt stores a function; `Owner.Handler.method` names that
function's type. The Qt object owning the stored function owns the handler.
`message_handlers.py` binds `MessageHandler.install`, which receives messages
logged on the main thread. Messages logged on other threads, or while the
handler runs, go to the previously installed handler.
`QStringConverterBase.State.Cleanup.install` attaches a one-shot cleanup handler
to converter state.

Rendering handlers, such as `updatePaintNode`, scene-graph virtuals and Quick
framebuffer or RHI item renderers, run only when Qt renders on the main thread.
`Render.useGuiThread()` selects Qt's basic render loop and must run before any
Quick window exists. Scene-graph operations require an active render handler.
With Qt's default threaded loop, those handlers use their native fallback.
`runnable_jobs.py` adapts QThreadPool jobs and QQuickWindow render jobs: the
runtime schedules a wrapper so the program's handle stays valid and pinned
while a job is queued or running.

`rhi_cleanup.py` binds QRhi's native keyed and unkeyed cleanup registrations as
`QRhi.addCleanupHandler` and `addCleanupHandlerUnkeyed`. The first native
cleanup invocation begins cleanup, and the last handler finishes registry
invalidation. This counts handlers instead of depending on QHash iteration
order. `Lifetime.cleanup_access` checks causal resource access.

`callback_sampled_images.py` uses Qt shader reflection to bound QSGTexture pointer
arrays. It checks reply length and every texture before committing any output.
Replacement textures retain their existing ownership and remain registered until
the shader releases them. The fixture uses Qt's shader preparation code to verify
the actual reflected array length, with no private shader API in the consumer
adapter. Protected configuration hooks are available only on generated proxies.

`icon_hooks.py` adapts QIconEngine's two documented ABI hooks to their owning
payload types. Both direct calls and handlers preserve the initial in/out
value. Unknown native hook IDs use Qt's base implementation; they are not
exposed as arbitrary pointers in Bend.

`webview_runtime.py` checks public plugin metadata before direct QWebView
construction. The v6.12.0 QtWebView factory otherwise aborts when no backend is
installed. Backend installation is part of the Qt runtime setup, never an extra
binding SDK or consumer build step. The handler fixtures exercise both an absent
backend and the installed official WebEngine backend.
The pinned Linux Qt archive omits that plugin. Maintainer setup runs
`scripts/setup-qt-webview-backend.sh` to build and install only the official
QtWebView WebEngine plugin from the pinned source. Its build directory stays on
the Linux filesystem. This setup needs `libxkbcommon-dev`; it does not replace
the kit's Qt libraries or add a consumer build step. The plugin links with its
installed RPATH, not the build tree's, because the linker hashes the RPATH into
its build ID; the plugin is then identical on every machine. The script stamps
its own digest and rebuilds the plugin when it changes; release preparation
accepts only a plugin built by the current script.
