# Coverage of the generated Qt package

The coverage target is the API exposed by PySide6 6.12 in the selected modules.
The current package does not yet claim complete coverage of that target.
The authoritative report is `packages/qt612/coverage.json`, generated alongside
the Bend and C files. A successful C++ compile verifies the emitted signatures;
it does not verify the behavior of every Qt API at runtime.

## Inventory and implementation

PySide6 6.12 type systems supply the API inventory. The generator verifies the
pinned source commit and records hashes of the discovered type-system files. The
profile selects modules instead of classes. A new Qt release requires updating
the maintainer baseline and its tests; installing a newer Qt 6 runtime does not
automatically add newer API to an existing generated package.

The report includes all discovered upstream modules and marks those selected.
For selected modules it lists extracted classes, excluded classes, generated
methods and backend exclusions. It also records Shiboken's own rejection logs.
Upstream removals and unknown or unsupported C++ declarations can limit what the
extractor exposes. Coverage is compared with the selected PySide inventory,
not with every declaration in Qt or the native graphics APIs.
Inherited names and overload variants are counted separately from native wrappers.
QVariant is a Bend representation adapter because PySide treats it as a primitive.

The report records public method/signal entries, shared native wrappers,
additional entry points that supply native Qt defaults, container instantiations
and signal payload types. Counts include inherited names and are not a percentage
of Qt coverage. Use the generated report for the current totals.

Recursive container conversion now covers lists, QStringList, maps, hashes,
multimaps, multihashes and pairs when their elements have supported conversions.
The generator also has a set converter. Bend uses Data lists and PairValue
records; generated scopes recursively release owning value copies. Signal
handlers accept multiple scalar, string, copied value, QObject pointer and
container arguments, and overloaded signals have typed connections. Argument
copies the handler does not keep, and failed output conversions, are released
when the handler returns. Qt integer aliases and
64-bit enum/flag representations are supported. Binary QByteArray helpers use
U32 lists with byte-range checks. QByteArrayView inputs borrow checked storage
for the native call, and returned views become owning QByteArray copies.

Signal arguments are converted when Qt calls the handler and are valid during
that call. QObject arguments are borrowed handles, including null. Values,
strings and byte views are copied, including storage supplied through Qt's
fromRawData APIs. A conversion failure fails the Bend-started Qt operation
during which Qt delivered the signal. QObject.destroyed passes an
ObjectIdentity, the handle word of the destroyed object, without exposing a
usable object pointer; its connection closes after that single call.

Custom signals accept arbitrary Bend Data through `Qt.arg(~Payload)`. One
opaque Qt metatype retains typed Bend values for signals, properties, named
methods, QVariant and QML round trips. QML can retain and forward them; exported
QObject properties or QVariant maps provide inspectable fields. The transport
checks the closed type witness before extracting a value. Native lifetime and
worker-thread release behavior remain integration-tested, outside the pure
Action proofs.

Runtime QObject schemas can be registered as creatable QML elements, attached
types, extension objects and singletons. Native placement construction precedes
the typed Bend initializer and QML binding evaluation. Dynamic metadata uses
Qt's moc format and public connection ABI. These features run in the same
version-pinned payload as all other bindings.

The legacy Charts/DataVisualization profile is validated separately from
Graphs, whose C++ type names conflict. Its module check compiles all supported
methods and override classes, then exercises line-chart signals and ownership,
and Scatter/Bar/Surface data arrays and independent snapshots. This verifies
generation and representative native behavior, not every graphical backend.

Supported temporary pointer payloads are copied on the emitting thread before
their storage can expire. The copies are queued for the main thread, and
closing the connection discards pending snapshots. A signal with mutable
arguments emitted on another thread waits for the main thread to fill the
reply, so the main thread must be running a Qt event loop.

The report also identifies output records, mutable references, operators and
retention adapters, including inherited names.

Mutable scalar, string and supported container references now return typed
output records. Mutable handle references update in place. Audited upstream
output-pointer templates generate scalar outputs without exposing pointers.
QObject parent changes and explicit supported transfers update registry ownership;
scopes preserve Qt-owned objects and take methods restore caller ownership.
Arithmetic, comparison and assignment operators are generated with `op_*` names.
PySide reference-count and parent-add annotations generate retention adapters
for QObject setters with matching getters. The generator also infers unannotated
instance `setX`/`x` properties, such as `QPushButton.setMenu`, when the setter has
exactly one input QObject pointer and a matching public pointer getter. It does
not infer indexed or other multi-input relationships; explicit annotations can
support one scalar index. Parent setters are excluded from this inference.
`QThread.setEventDispatcher` validates and records Qt's ownership transfer to an
unstarted thread. Its virtual handlers use the existing main-thread Bend bridge;
ordinary calls on the transferred dispatcher retain the affinity guard. A semantic observer
policy prevents lazy getters from changing the application
during reconciliation. The menu-bar and menu-widget setters share the
noncreating `menuWidget` observer. Known parent-owned objects with lazy getters
use native parent tracking instead, and platform screen setters do not add pins.
Explicit null-reset policies preserve APIs that replace null with a Qt default.
Wrapped or conditional getters use dedicated adapters, including style,
popup and calendar-widget replacement.
An observer confirms what the setter
stored; keyed row/column setters replace only their own dependency. Actual
QObject parents determine native ownership. Other stored pointers keep their
targets alive through retention. Known getters are rechecked after native calls
and their slots retargeted when the observed object changes. QDrag's native
deletion of MIME data is observed through QObject destruction observers.

Scoped cleanup defers retained owned objects. Explicit destruction returns
EBUSY when an external owner retains the object or a descendant. Removing the
dependency allows pending cleanup. Registry tables grow from 4,096 slots within
the handle format's 65,535-slot limit. Retention checks capacity before mutating
Qt and permits replacement at full capacity. Direct
retention cycles (including paths through parenting) return ELOOP; ordinary
QObject parent-tree cycles return EINVAL. Cycles introduced indirectly by native
code or QML stay alive until explicitly broken.

## Broad API generation

The default profile selects 57 modern Linux modules. Class discovery still
comes from PySide's definitions. The generator also processes the public
OpenGL headers listed by PySide and the version-bound RHI headers. The compact
seven-module profile remains available to maintainers. Charts and
DataVisualization use a separate profile because their C++ names conflict with
Graphs; combining those header families is not a supported Qt configuration.

The adaptation layer includes virtual-method overrides and stored-function
handlers, mutable signal replies, QObject and non-QObject ownership, retained
collections, model-index lifetimes, QML types and lists, metatype storage,
generic metaobject arguments, dynamic QVariant values, shared pointers, futures,
byte and typed views, mapped storage, OpenGL buffers and sync objects, image
backing storage, native event filters, plugin names and URL handlers.

Handlers run on the main thread; see [embedding](embedding.md) for the calling
model. Bend works with QObjects that live on the main thread, and generated
wrappers reject objects owned by another thread with EXDEV. A virtual method Qt
calls on another thread runs its handler on the main thread while the caller
waits. Scene-graph handlers run only under Qt Quick's main-thread render loop
and receive an explicit rendering context; on a render thread the C++ base
implementation runs.
Native owner-thread calls to runtime-defined QObject properties and methods
also wait for main-thread dispatch, including storage access and error
propagation. They do not access the registry on the worker thread.

RHI uses the payload built against the exact installed Qt 6.12.0 version.
The package has one complete payload and rejects other Qt versions at startup.
Rejection is tested with simulated version strings; it is not a test against
an unreleased Qt runtime. Native handles exposed through an explicitly named `unsafeAddress`
remain subject to the external API's lifetime and thread requirements.

Coverage remains an audit, not a percentage. In particular:

* Extraction omissions, upstream removals, template-only declarations and
  Python-only injected helpers are recorded separately from generated methods.
* An adapter for a raw-pointer API has a specific contract, such as a bounded
  buffer, owning copy or scoped borrow. It does not make arbitrary pointers safe.
* Qt marks some extracted declarations as internal or reserved. Their reasons
  and alternatives remain visible in the report.
* A Bend handler cannot safely run in QProcess's post-fork child modifier.
  That API is excluded; native UnixProcessParameters remain usable.
* Other platforms and Bend runtime versions are outside this target. Hardware,
  driver and service-dependent behavior needs testing on those actual systems.

Python-only injected code and synthetic methods require Bend implementations
when they provide useful behavior. Their presence in PySide XML is not evidence
that the underlying C++ signature exists. Unsupported cases stay in the report.
`findChild` and `findChildren` have typed per-class replacements, `T.findIn`,
`T.findAllIn` and `T.findAllMatchingIn`; the report lists them as alternatives.

The extended Vulkan experiment is archived on the `archive/vulkan-expansion`
Git branch. Native Vulkan instance, memory, semaphore, command and compute
capabilities are outside the active PySide coverage target. Their separate
registry discovery, custom lifetime adapters and verification gates are not
part of the active package. Qt's own rendering backends can still use Vulkan.
The generated exclusions distinguish unavailable native-handle contracts from
supported PySide APIs.

Additional conversions cover locale success outputs, raw font and glyph arrays,
IPv6 byte arrays, polygon coordinates, OpenGL border arrays, counted CBOR chunks,
image-reader outputs, matrix data views and optional directory permissions.
RHI dynamic buffer updates use bounded, expiring MemoryView handles and prevent
frame completion while a mapping remains active. Native vertex bindings validate
their count and resource domain before invoking Qt.

The raw-text QTextBoundaryFinder constructor uses owned UTF-16 text and aligned
working storage, with an explicit checked prefix length. Copies, assignment and
swap preserve the backing storage. The same paired-array admission table used by
glyph conversions rejects a negative or oversized text length; Qt's UTF-16
conversion and boundary detection remain native test responsibilities.

Bend calls Qt only on the main thread. `QObject.moveToThread` and
`QObject.deleteLater` are ordinary Qt methods; afterwards, calls on an object
owned by another thread fail with EXDEV, as do model indexes whose model lives
there. Mutable and output references containing scalar, string or container
values return copies. The native fixture overrides QValidator, returns both
changed reference arguments and its native result, and checks a handler
failure; the single-string output adapter used by QValidator.fixup works the
same way. A handler failure fails the Bend-started Qt operation during which Qt
ran it, and the first error survives later cleanup failures. A caught nested
error does not affect an outer successful call. ENOSYS (`Qt.Virtual.base`) is
the reserved request for the C++ base implementation of a nonabstract virtual.
String and byte arguments own their storage, recursively through containers,
rather than keeping shallow aliases to external raw storage.
`QMetaObject.newInstance__QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument_QGenericArgument` has checked generic-argument bindings. Constructing an
empty raw QMetaObject record and private base-class construction remain
unavailable. Pending deferred deletions run during application teardown.
Keyed RHI cleanup handlers use stable native keys and track the cleanup phase
without depending on handler order. Sampled-image handlers use the exact
shader-reflected array extent and validate every output before writing it.
QIconEngine's two documented ABI hooks use typed in/out values and the ordinary
handler path. Unspecified extension IDs do not expose arbitrary pointers.
Protected, nonvirtual destructors use an exact derived-type deleter for binding
constructions. Such objects remain marked as unobservable to external deletion.
Native tests cover QIODeviceBase construction and QStringConverter move
construction, including expiry of the consumed source alias.

QSGGeometry attribute sets own their attribute arrays and return owning snapshots.
Geometry construction and allocation check counts, strides and byte extents before
calling Qt. Retained layouts reject mutation. Render handler transform pointers
expire when the handler returns, including aliases in copied records. Public
metadata pointer fields retain observed metadata origins across aggregate copies.
The dependency closure also covers model indexes nested in public records,
including QStyleOptionViewItem.index. Copies preserve the model observation and
reject access after native model invalidation.

Lazy QStringEncoder and QStringDecoder result records are discovered from their
extracted template shape and public fields. They own their input backing and
retain the actual converter; conversion remains deferred until `.value()`.
Copies share converter state, so streaming input and one-time BOM behavior are
preserved. Native tests cover input destruction, copying, replacement, rollback
and cleanup. Canonical signed 64-bit chrono duration fields use their supported
tick codec, including QAbstractEventDispatcher::TimerInfoV2.interval.
QStringConverterBase.State.Cleanup supplies a checked one-shot alternative to
the native clearFn pointer. It passes a scalar snapshot to Bend, preserves
foreign cleanup and opaque storage and follows consuming native moves. Qt may
clear a state on any thread; the handler runs on the main thread. Tests check
handler failure and actual holder reclamation. Raw QMetaObject::Data construction remains unsupported;
its tables are private metadata layout, and reflection does not replace a
facility for creating arbitrary runtime methods or signals.

Custom video buffers have owned plane storage and checked mapping epochs.
MapData's data setter accepts four optional ImageBuffer values, and its getter
returns four optional bounded MemoryViews. Copies expire on unmap or native
buffer destruction, including an unmap on another thread before its cleanup
reaches the main thread.
QVideoFrame.fromVideoBuffer consumes an observed owned buffer using Qt's public
unique_ptr constructor. Shared frame copies keep that native buffer alive.
Mapped or adopted buffers reject incompatible direct mapping operations.
RGB and YUV layouts are checked before Qt reads them; opaque GPU sampler formats
and unobserved native plane pointers remain explicit limitations.
These restrictions, upstream removals and extractor omissions prevent a claim
of complete PySide6 coverage on the current target.

## Current verification

The expanded property and argument APIs are undergoing fresh package validation
on Qt 6.12.0 and Bend 2.0.40. Earlier package receipts predate these changes and
do not establish their completion. The current pure proof run checked 102 laws
and 65 negative controls. Native metadata, bindings, lifetime and QML behavior
require the complete regenerated-package gate below. Public Hub acceptance and
an actual newer Qt runtime remain unverified; nothing has been published to the
public Hub.

The agreed argument spelling is `Qt.int32()` for a native Qt descriptor and
`Qt.arg(~Payload)` for opaque custom Bend data. The native descriptor names
are implemented in the generator. Class descriptors such as
`Qt.QPushButton.arg()` preserve the concrete Bend type and native pointer type;
public copyable Qt metatype values use the same spelling. QVariantMap and
QVariantList descriptors reuse the existing container conversions. Unsupported
class descriptors remain visible in the custom-signal coverage inventory.
The packaged checks exercise custom-data retention, queued transport,
typed recovery, QVariant/QML round trips and final release, including release
from another thread. They also cover QML creation, attached and extension
factories, inherited extensions, factory failures and native worker-thread
property and method calls. The current receipt must cover the final artifacts,
bundled examples and actual local publication client.

The separate Charts/DataVisualization profile compiles every supported
method/signal entry in those two modules and runs representative consumer programs.
Its [receipt](../build/charts-module-check/receipt.json) records the complete-module
selection and native tests, including chart signals and Scatter/Bar/Surface
array ownership and snapshots. This is representative runtime coverage, not a
test of every graphical backend.

The required final gate is `python3 scripts/check-qt612.py --bundle
--generator-checks --reject-system-qt` after regeneration. It includes the proof
and source-identity checks, fresh Hub consumers, the native examples, native
lifetime, handler, signal, conversion, metatype and resource-bound checks
(some under ASan and UBSan), local publication through the actual Bend client
against a disposable registry, ABI checks, a separate Core/Gui/Widgets/Xml
extension profile and deterministic regeneration. Its
[combined receipt](../build/full-property-coverage/receipt.json) records
the final package and source hashes and references the canonical, final-package
and Charts/DataVisualization results. The
[canonical receipt](../build/qt612/check/receipt.json) retains each native check.
External Vulkan tests are archived and do not substitute for any of these checks.

The integration harness uses a temporary Hub manifest server and an empty Bend
cache. It builds with the standard `bend main.bend -o app` command while disabling
consumer C++ and Qt development lookup paths. It checks the resulting executable
for Qt or C++ link dependencies and verifies old-runtime rejection.

The examples exercise Widgets, scoped cleanup, parent destruction, stale and
mistyped handles, and Bend computations running during `QCoreApplication.exec`.
[Handler tests](../examples/qt612/callbacks.bend) cover abstract and pure
virtual methods, nested handlers, typed copies of answers, deletion guards,
handler failures, rejected waits and C++ base fallbacks. Thread-pool tests run
a QRunnable's handler on the main thread while its pool thread waits. The Quick example
loads QML, checks Unicode signal delivery and reads rendered pixels. It also
checks exact double bits through a QML real property and QVariant. The numeric
example checks decimal conversion, arithmetic, 64-bit integer/enum round trips,
integer alias ranges, native default arguments and invalid conversions. Container
tests cover Unicode, empty and shared lists, nested real/value pairs, unique and
duplicate map keys, hashes, malformed payloads, rejected elements, failure cleanup
and registry-exhaustion rollback. Signal tests cover two and three arguments,
nested lists, value arguments, disconnection and overloaded connections.
[Object signal tests](../examples/qt612/object-signals.bend) cover borrowed
identity, nulls, stale objects, generation reuse, bursts, scope ends and
cleanup of mixed object/value arguments. The native signal check delivers an
emission from another thread to the handler on the main thread, and covers
disconnection and sender destruction.
[Binary tests](../examples/qt612/bytes.bend) cover all 256 byte values, embedded
zeros, view copies surviving source mutation/destruction and invalid byte or
narrow-integer inputs.
Reference tests cover scalar outputs, status flags, mutated strings and cursor
positions, value swaps and aliases, stale-input rejection, assignment snapshots
and output-scope cleanup. Ownership tests cover parented construction, inner-scope
transfers, strict destroy errors, detachment, cycles, error cleanup, set/take
identity, cookie-jar adoption and delegate-factory parent ownership. Temporary-file factory tests copy a
Qt 6.12 built-in image through both overloads, check caller ownership and
verify automatic file removal. That image is a test fixture, not a package
runtime dependency. A separate host-lifetime case rejects
application adoption/destruction and leaves its one borrowed host entry alive
until Qt exits.
[Retention tests](../examples/qt612/retention.bend) cover deferred scoped cleanup,
getter-confirmed replacement, keyed slots, strict destruction, cycle rejection
and capacity checks.
[Parent and retention tests](../examples/qt612/retention-parent.bend) cover
native parenting, pointers retained without parents, observed native deletion,
lazy-getter regressions and resets to Qt defaults.
[Shutdown tests](../examples/qt612/shutdown-retention.bend) leave a pending model
and menu retained by application-owned objects. Native destruction observers
remain active during QApplication teardown, and collection runs again
afterward. With `BEND_QT_CHECK_SHUTDOWN` enabled, the harness requires
`QT612_SHUTDOWN_OK` and fails if owned entries survive. Ordinary fixtures require
empty registries before exit.
These are representative runtime tests, not exhaustive tests of every generated
signature or container instantiation. The set converter is not exercised by
the selected default API's native examples.

The shared pure sources are checked by `--verdict`, and type-correct negative
controls must be rejected. The proof receipt records the current law and
mutation counts. Source checks do not establish identity with older packaged
artifacts; the canonical packaged gate must run after regeneration.
Native decision tables are evaluated
from the actual proved Lifetime definitions. Generated per-type adapters,
dependency traversal, getter observations, signal argument conversion, handler
invocation, capacity checks and native destruction
remain outside those proofs. See [the proof boundary](action-proofs.md).
The harness additionally verifies deterministic output and adding QtXml to a
minimal module profile without a maintained class list. The full native harness leaves `CC` unset to
use Bend's default Clang 18 in this workspace. Bend rejects `CC=gcc` and falls
back to Clang, so that setting does not test GCC.
