# Qt 6.12 API coverage audit

This audit compares the package with the pinned PySide6 6.12.0 binding scope on
Linux x86-64. It records functional equivalents as well as missing native
signatures. A generated method name or a parser accepting a schema does not
establish working native support.

The generated package inventory inspected on 2026-11-14 predates the current
adapter changes. Its counts are historical input to this audit. Fresh generation
and the canonical package check must establish the final counts and test status.
The `full_coverage` field must not be changed solely because a focused test passes.

## Python additions

The historical package has 9,266 exclusions described as Python additions. They
contain 302 distinct full signatures and 222 distinct names. Inherited QObject
connect, disconnect, emit, findChild, findChildren and tr signatures account for
8,261 rows. Counting those rows as separate missing features substantially
overstates the work.

The complete signature matrix is in
[`api-coverage-signatures.json`](api-coverage-signatures.json).
Each record includes its source signature, affected classes, equivalent Bend
entries, explanation and source paths. Its input is
`build/api-gap-audit-python-only.json`, with SHA-256
`cf6dbaa16bf46b14d873174e78b8c55a3c92d28a1f769b1039af2e60336e3a2a`.
These are local audit receipts, not consumer dependencies.

| Feature group | Bend interface or disposition |
| --- | --- |
| QObject connections and signal emission | One `Signal` declaration per native signal, such as `QSlider.rangeChanged()`, and per Bend-declared signal; `Signal.connect`, connection modes, method connections and `Signal.emit` for both. |
| Finding children | Typed class `findIn`, `findAllIn` and regular-expression searches. Explicit Qt child-search options have a separate regression fixture. |
| Translation | Native class `tr` uses that class's static metaobject. `ObjectType.tr` uses the declared runtime schema. |
| Python callable action and shortcut constructors | Construct the QAction or QShortcut, configure it and connect its ordinary typed signal. |
| Python bytes, buffers and NumPy inputs | Use owning byte, numeric and point lists, or checked native views. Python array strides and pickle protocols are not Qt values. |
| Directory iteration | `QDirListing.entries` returns owning QFileInfo snapshots. Native DirEntry values borrow iterator internals. |
| QRangeModel construction | `fromValues`, `fromRows` and schema constructors own the native ranges. Current cell leases are replaced with their values. |
| OpenType font tags | Checked optional `QFont.Tag.fromString` and `fromValue` factories. |
| HTTP Range values | Optional signed 64-bit bounds, checked range construction and native range-set snapshots. |
| JavaScript conversion and singleton lookup | `QJSEngine.toScriptValue` and descriptor-typed `QQmlEngine.singletonInstance` lookup. |
| System locale and action menus | `QLocale.system` and typed `QAction.menu` restore functions hidden behind Python or C++ template wrappers. |
| Wizard fields | `QWizardPage.registerField` exposes the native widget property, mandatory-field and change-signal behavior. |
| Audio buffers | `QAudioBuffer.bytes` copies the current bytes. `setBytes` checks the exact native size and uses Qt's writable detach. |
| QDataStream primitive helpers | Named adapters call the actual signed/unsigned widths and floating-point overloads. Pinned PySide `readString` and `writeString` are QString aliases. |
| Easing and accessibility function pointers | Typed native function handles preserve stored copies and native ownership. Their runtime tests include more registrations than a fixed callback slot array can hold. |
| REST callbacks | Typed callback overloads deliver QRestReply with context cancellation. Native reply methods and finished-signal composition also remain available. |
| HTTP server, permission and Canvas callbacks | Typed adapters cover request-to-string routes, response mutation, permission delivery and owning Canvas readback images. Their separate runtime fixtures remain part of final validation. |
| QHostInfo and timer callables | Typed lookup and singleShot handlers preserve native lookup ids and optional QObject context cancellation. Native receiver/member composition is also available. |
| Thread-pool Python callables | `QRunnable.newOverride`, its typed `Virtual.run` handler and native QThreadPool scheduling provide the operation. |
| QMetaMethod invocation and Q_ARG | Retained MetaStorage and QGenericArgument/QGenericReturnArgument holders provide native invocation and return assignment. |
| Qt Quick Test launchers | `QuickTest.run` and `runWithSetup` call the native test runner. Setup is an ordinary QObject with applicationAvailable, qmlEngineAvailable and cleanupTestCase methods. |
| Global Qt logging functions | QMessageLogger supplies the same severity and optional QLoggingCategory behavior. |
| QML decorators | Explicit runtime schemas and QML registration operations replace Python class decorators. QObject factories, QJSValue factories and source-URL registration are distinct contracts. |
| Python frame and JSON list conveniences | Frame traversal uses mainFrame, children and name. JSON object-list conversion uses array access plus QJsonValue.toObject. |
| Python remote replica type objects | acquireDynamic exposes the remote native metadata. Python repc-generated class objects themselves are not Bend values. |
| Context managers, repr and pickle | Native handles use Action scopes. Python protocol compatibility is a separate language feature. |

The matrix records source adapters and differences in representation. It does
not count every composition as an identical overload. Source implementation,
Bend type checking, native tests and fresh package verification are separate
evidence levels.

The helper-class audit also checks PySide classes absent from ApiExtractor's
native class model. `QMutexLocker` and `QRecursiveMutexLocker` own the two real
native QMutexLocker specializations and return a concretely typed mutex.
`unlock`, `relock`, `isLocked`, `swap`, `keep` and Action scopes preserve the
mutex lease through the locker lifetime. This includes a mutex borrowed from
future state: replacement is rejected while a native consumer retains the view.
`QOverrideCursorGuard.new(cursor)` pushes one native cursor override and restores
it once on explicit restoration or scoped cleanup. Nested guards follow the
ordinary Qt cursor stack. Cleanup defers until an active native cursor-view call
unwinds before popping its storage.

Both helper fixtures pass strict Bend checks. The tracked
[native helper control](../scripts/check-qt-mutex-lockers.py) passes normally and
under ASan/UBSan, including real worker-thread lock exclusion, lease replacement,
injected failure cleanup and the native GUI cursor stack. It accepts
`--cursor-guards` for the cursor control. These helper controls use a minimal
registry, so the full generated effect/Action integration is still a separate
pending gate.

Its 302 records classify 154 signatures as adapters, 44 as native equivalents,
71 as compositions of native operations, 14 as language adaptations, seven as
Python runtime operations, nine as application-architecture differences, one as
a platform-specific interface and two as resource compiler ABI hooks. These
are source classifications. An adapter entry does not assert that its final
combined native fixture has passed.

## Native signatures

The historical native inventory contained five entries classified as binding
gaps. Their dispositions are explicit below.

| Signature | Disposition |
| --- | --- |
| `QMetaObject()` | Usable native metadata comes from a QObject or QMetaType. An empty metadata object has no generated tables. See the pinned runtime controls below. |
| `QMetaObject::SuperData::operator->()` | The metadata arrow adapter restores the native operation. |
| `QProcess::failChildProcessModifier` | Qt permits this only inside the matching child modifier. Pinned PySide does not expose that modifier callback. See the boundary evidence below. |
| `QRhi::setQueueSubmitParams` | The typed native-handle adapter preserves the selected RHI backend and its native lifetime requirements. |
| `QThread::setEventDispatcher` | The explicit transfer adapter preserves thread ownership and rejects invalid transfers. |

Five of the six historical partial signatures already had typed callback
alternatives. They cover RemoteObjects name filters, WebEngine text search and
WebView JavaScript results. The sixth is QGlyphRun.setRawData. Its explicit
snapshot API owns the two counted arrays. It does not promise aliasing of
externally mutable native arrays.

Nine historical class-exclusion rows are dependency-only templates or internal
aliases. Concrete CBOR string/byte results, DBus replies, futures and fixed
matrix specializations have their own generated representations. The excluded
template declarations must remain visible in the report.

A later full-profile source pass admitted protected APIs rather than treating
their C++ access as a coverage exclusion. It covers all 57 selected modules
using complete cached native traits. Its receipt is
`build/current-full-coverage-audit.json`; the method, class and exclusion counts
in that receipt describe its own capture. It is regenerated as adapters change,
so earlier counts must not be presented as the current package inventory.

The internal native plumbing includes tagged-state QBasicReadWriteLock helpers,
raw resolveInterface accessors and QDBusAbstractInterface property helpers.
Qt explicitly marks the DBus helpers
internal and implements them through ordinary QObject property operations.
The lock helpers manipulate the private tagged lock state. The native-interface
macro documents its typed accessor while generating a protected raw resolver.
The corresponding public lock, property and typed native-interface APIs remain
available. These source classifications do not hide the excluded signatures.

Other audit rows exposed concrete pointer, output, buffer and retention work.
They include style options, Modbus data units, NMEA parsing, OAuth request
mutation, native event buffers and model-index identities. Their source
adapters and tests must be included in the fresh final inventory and gate.

The extraction receipt contains 7,993 additional omission rows. Its groups are
5,843 declarations disabled by the type system, 849 types absent from the type
system, 640 unmatched return types, 493 unmatched argument types, 153 unmatched
operators and 15 unmatched fields. These groups include private implementation
types, native templates, compiler hooks and separately restored adapters.
Those totals alone do not establish PySide parity. Remaining candidates require
comparison with the pinned PySide runtime or source.

## Protected native APIs

Protected C++ access does not mean that PySide hides the operation. A systematic
runtime attribute inventory found 1,767 protected method declarations with a
PySide attribute, including overrides. It found 80 without one. This is an
availability filter, not proof that every overload accepts the same arguments.
Private overrides can inherit a public or protected contract, which needs a
separate access path through that base contract.

The inventory is in `build/protected-api-classification.json`. It includes exact
argument and result types, native source locations, access flags, protected enum
dependencies and mutable container references. No protected owner in that
inventory is a C++ final class.

Ten isolated constructor controls passed in the pinned PySide runtime. They
cover QFileDevice, QStyleOptionButton with an explicit version, QEvent and
QCloseEvent copies, QCanvasGradient, QStringConverter, QTextCharFormat,
QAbstractOpenGLFunctions, QDBusAbstractAdaptor and QRemoteObjectReplica with its
constructor tag. The receipt is `build/pyside-protected-constructors.json`.
These controls establish a constructor gap beyond ordinary public constructors.
They do not establish that all 125 protected source constructors have usable
Python argument forms.

Protected enum dependencies include item-view state and cursor types, slider
changes, satellite parsing status, remote-replica construction and SQL result
binding syntax. A legal derived access alias can name these types. The private
QPixelFormat Field and FieldWidth types are absent from PySide and remain
outside that contract.

The protected-field inventory contains 93 distinct fields. Pinned PySide exposes
89; the four absent fields are internal QBasicReadWriteLock constants. Nine
exposed fields are bitfields in QPaintEngine and QSGOpaqueTextureMaterial.
An actual Qt-created material accepts their reads and writes in PySide, so a
binding cannot assume they apply only to Python-created subclasses. The receipt
is `build/pyside-foreign-bitfields.json`.

Borrowed fields need more than access syntax. QStringDecoder.state returns the
same mutable State view; assigning a different State fails in pinned PySide.
QPaintEngine.state changes from null to a borrowed state while painting, then
back to null after QPainter.end. Its lifetime therefore depends on the current
field identity and painting activity. The controls are in
`build/pyside-converter-state-field.json` and
`build/pyside-paintengine-state-field.json`.

The current source exposes ordinary protected fields through legal derived
member pointers applied to the actual base object. Bitfields use masks calibrated
on a genuinely constructed native probe, then access only the corresponding
unsigned-char representation bits. No foreign object is downcast to the probe.
Borrowed member views preserve identity and check their current source pointer,
owner chain and existing native origin guards before dereferencing storage.

The tracked [protected field check](../scripts/check-qt-protected-fields.py)
passes with the pinned Qt libraries in both its normal and ASan/UBSan runs.
It covers all nine bitfields on real foreign Qt objects, addressable fields,
mutable converter state and nested native aliases. Removing ancestor validation
from the alias guard reproduces a heap-use-after-free in the negative control.
The [Bend fixture](../scripts/fixtures/protected-fields.bend) passes strict type
checking. Its latest combined generated-package native result is still pending.

## Property and native getter checkpoint

The [property-system matrix](property-system.md) maps every Qt 6.12 property
attribute, including real BINDABLE storage, revisions, REQUIRED and the
FINAL/VIRTUAL/OVERRIDE metadata. Descriptors cover the selected native metatypes,
typed QObject pointers, runtime enums, supported native container instantiations,
authored QQmlListProperty values and opaque Bend Data. Dynamic properties use
the ordinary QObject QVariant APIs. Per-property snapshots preserve metadata and
external-data origins while QObject pointers remain borrowed. Native change
events update already observed properties before user handlers run. Independent
returned copies survive replacement; stale values can still be removed.
Python descriptor documentation and deletion hooks are language behavior rather
than extra Qt property attributes.

The [dynamic-property control](../scripts/check-qt-dynamic-properties.py) passed
normally and under ASan/UBSan with real Qt metadata, native raw mutation,
reentrant events, outgoing copies and repeated removal. Its minimal origin
registry does not exercise the full generic codecs or effect transport.
The corresponding [consumer fixture](../scripts/fixtures/dynamic-properties.bend)
passes strict Bend checking; its fresh combined native result is pending.

An owning native property value needs a copy constructor. Default construction
and copy assignment are not required for ordinary reflected reads; the reference
read protocol supplies such values. A typed native bindable additionally needs
copy assignment for its QPropertyData/QBindable value operations. Unsupported
native container instantiations remain explicit in the inventory. The pinned
PySide controls in `build/property-bindings/pyside-property-views.json` report
invalid metatypes and unusable reads for QStringView, QLatin1StringView,
QAnyStringView and QByteArrayView properties, so these excluded view descriptors
do not represent a working PySide property family omitted from Bend.
The separate write-only control in `build/property-bindings/pyside-writeonly.json`
distinguishes Python assignment from native property writes: direct assignment
calls the setter, while QMetaProperty.write and QObject.setProperty report true
without doing so. It is not a working additional native property mode.

An independent pointer-result audit checks generated methods that would otherwise
fall through to an untracked native borrow. The current source adds checked
getters for native icon and editor factories, accessibility facets, layout
spacers, Help items, HTTP routers, QML controllers and interceptors, SQL results,
SCXML data, sensor filters, WebEngine/WebView settings and scripts, text storage,
future mutexes and Qt3D callbacks. A getter rechecks the current native identity
or list membership after validating its owner. Help model views retain a
persistent index and a reset epoch. Static factories use scoped descriptors.

QSqlDriver.createResult returns an owning result and retains that result's actual
driver. QSqlQuery adopts the result once; query copies and QVariant snapshots
retain independent driver origins. Replacing native result storage expires
previous views without dropping the query's own driver lease. The Qt contract
still requires the database connection to remain open while queries use it.

Provider snippets compile against the installed Qt headers, and the
[native result fixture](../scripts/fixtures/native-result-views.bend) has strict
Bend type checks. The source audit, isolated native controls, fixture type checks
and final integration run are separate evidence levels. The fresh combined
native results for these getter families and the canonical package gate remain
pending; these changes do not establish a new full-coverage total.

## Omitted private signal payloads

Three apparent extraction candidates fail in PySide itself. Connecting a
Python callback to QQuickWindow.closing fails to convert QQuickCloseEvent*.
The two QAreaSeries gradient-change signals fail to convert
QQuickShapeGradient*. Those failures were triggered by actual native window
closure and QML-created gradient assignments. Their receipt is
`build/pyside-omitted-signals.json`. The corresponding QObject properties remain
usable through QML and reflective property access. A handler that takes no
arguments can still observe those notifications. A native QObject connection to
a Bend-authored zero-argument method provides that operation without converting
the private payload type.

## Native metadata and process setup

The isolated pinned PySide controls in
`build/pyside-meta-process-boundaries.json` produced these results:

| Control | Result |
| --- | --- |
| Construct `QMetaObject()` | Construction succeeds. |
| Call className on that object | The child process exits with SIGSEGV, code -11. |
| Call propertyCount on that object | The child process exits with SIGSEGV, code -11. |
| Inspect QProcess.setChildProcessModifier | The Python attribute is absent. |
| Inspect QProcess.failChildProcessModifier | The Python attribute is present. |

Qt documents use of failChildProcessModifier outside the matching child modifier
as undefined behavior. Its normal callback runs between fork or vfork and
execve. Qt also documents restrictions on locks and ordinary Qt calls in that
callback. The extraction log rejects the setter's std::function argument.
The package's declarative UnixProcessParameters interface remains available.
These are established upstream and process-lifecycle boundaries.
See the [Qt 6.12 process source](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/corelib/io/qprocess.cpp)
and [QProcess documentation](https://doc.qt.io/qt-6/qprocess.html#failChildProcessModifier).

QAbstractProxyModel.createSourceIndex does not share createIndex's Python-object
convenience. The pinned runtime rejects a dict, None and a plain integer
address. An explicit Shiboken VoidPtr succeeds. The resulting index can recover
the object while its storage stays alive. The receipt is
`build/pyside-source-index-payload.json`. Bend's ModelData adapter currently
represents an origin-checked opaque identity, rather than an arbitrary payload.

The pinned value-pointer controls in `build/pyside-value-pointer-scope.json`
confirm in-place style-option and Modbus data-unit mutation. Satellite parsing
accepts an explicit QByteArray but leaves the supplied Python lists unchanged.
Its advertised bytes-and-length overload rejects those inputs. An exposed
signature alone is therefore insufficient evidence of useful output conversion.

## JavaScript singleton factories

Pinned PySide supports qmlRegisterSingletonType without a QObject type argument.
Its callback returns a QJSValue. Two independent QML engines read an object
returned by that factory in `build/pyside-script-singleton.json`; the factory
runs once for each engine.

`Qml.registerScriptSingleton` exposes that operation with a typed Bend factory
and a registration handle. Managed results must originate from the requesting
engine; primitives have independent copies. The engine retains the registration
while using it. QJSValue origin leases preserve the engine and any external
data retained by its conversions. The focused regression fixture checks actual
QML reads, separate engines, strict cleanup, callback failure and a foreign
engine result. Its final combined native result remains part of the gate below.

## Native platform interfaces

The pinned PySide runtime exposes QX11Application with connection and display.
It exposes QWaylandApplication with compositor, display, keyboard, lastInputSeat,
lastInputSerial, pointer, seat and touch. All these methods have corresponding
Bend entries. Bend returns checked native capabilities, with an explicit
unsafeAddress operation for foreign interop.

The local offscreen run returned QX11Application. The Wayland run returned
QWaylandApplication. QScreen.nativeInterface returned None in both runs, which
matches PySide's Windows-only screen-interface conversion. The xcb run could
not start because this environment lacks libxcb-cursor0. That failure is recorded
in `build/pyside-native-interfaces.json`; it is not evidence against the API.
The pinned conversion code is in PySide's `glue/qtgui.cpp`, lines 900 through
938. Windows and macOS platform APIs are outside this package's Linux target.

## Resource compiler hooks

The raw qRegisterResourceData and qUnregisterResourceData functions are the ABI
used by generated RCC code. The public resource header does not declare them.
RCC generates local declarations and passes its own tree, name and data tables.
Its Python output calls the PySide wrappers for that same compiler format.

Bend exposes QResource.registerResource and unregisterResource for owning RCC
archives and filenames. This provides public resource registration without
claiming direct compatibility with Python resource-module internals.
The evidence is in the [Qt resource header](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/corelib/io/qresource.h),
the [resource runtime](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/corelib/io/qresource.cpp)
and the [RCC generator](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/tools/rcc/rcc.cpp).

## Callback coverage boundary

The [callback audit](callback-coverage-audit.json) classifies every unique
contract in the remaining callback-exclusion snapshot. The 1,026 inherited
rows reduce to 62 distinct contracts. This is a source and pinned-runtime
audit, separate from the final generated-package tests.

The target includes documented Qt application APIs and useful binding helpers.
It does not automatically include every undocumented hook exposed by PySide.
For example, Qt explicitly marks `QPaintDevice.sharedPainter` internal. Its
109 inherited rows describe one hook. The user requested removing this hook
from the public API. A reverse-binding prototype was saved in the build-only
archive `build/shared-painter-prototype.patch` and removed from active sources;
the generator also excludes forward access. Other existing internal methods
and fields are outside this specific removal. The unused
accessibility ABI extension hook and the render-state extension reserved for
future use have separate dispositions in the audit.

Documented renderer-resource consumption remains supported. Applications
obtain Qt's renderer interface from `QQuickWindow.rendererInterface` and query
its graphics resources. A complete scan of the extracted API and installed
headers found no public parameter or field that accepts a replacement
`QSGRendererInterface`. Qt supplies that object through its private
`QSGContext`; its backend plugin interfaces are also private. Python can
construct and manually call a custom provider, but that does not establish a
public workflow for installing it in Qt Quick. Replacement backend authoring
is outside this package's requirement to preserve Qt Quick's managed backends.
The audit preserves that distinction instead of treating resource consumption
as an excluded internal API.

The audit also found a documented constructor defect: the default-parent
forms of `QAbstractTransition` and `QEventTransition` were rejected because
retention planning tried to retain a parent argument that had not been
supplied. Empty constructor calls now require no argument leases. The new
`transition-constructors` fixture passed both default and explicit-parent
factories, native virtual dispatch, parent identity, strict borrowed/stale
guards and child invalidation, with zero remaining handles. Its fresh
Hub-format consumer built with stock `bend main.bend -o app`, without the
generator or a build-time Qt/C++ link. The receipt is
`build/transition-constructors/native/receipt.json`. This focused pass does not
replace the fresh full-profile package gate below.

Private and upstream-removed reverse contracts are classified using pinned
Shiboken's generation policy and native-to-Python dispatch controls. The
matrix also identifies owning-value composition alternatives for image and
pixmap proxy construction, platform wrappers disabled by upstream, and raw
provider returns that the pinned Python wrappers cannot use safely. These
dispositions do not claim byte-for-byte PySide parity or support for every
possible private backend implementation.

## Verification

The [native return audit](native-pointer-return-audit.json) gives an individual
source disposition for 193 pointer or reference return declarations. It maps
148 to lifetime or factory adapters, 28 to retained input identities, ten to
receiver identities, four to owning keyframe traversal alternatives and two
to authored backend-mapper results. The remaining original row is
`sharedPainter`, intentionally excluded by user policy. Its historical inherited
names are retained in the report as snapshot evidence, not current bindings.
The scan separately accounted for existing
RHI, accessibility, native-view and metadata policies. The report records source
hashes and the protected-renderer ownership boundary. These are source
dispositions; native tests must still establish the resulting behavior.

The separate [helper-class inventory](pyside-helper-class-audit.json) records
all 42 names found by importing the 57 pinned PySide modules and comparing
their class objects with the earlier extracted and synthetic class inventory.
Seventeen are inherited nested aliases and seven are shared-pointer carriers.
The other rows name their native adapter, owning traversal alternative or
Python-specific boundary. These rows are separate from the 302 Python-added
function signatures above.

Seven QObject/interface helper bases are now discovered from the pinned
registered `qpy*.h` declarations. Their native `Q_OBJECT` and `Q_INTERFACES`
metadata is compiled with the maintainer's moc. The unmodified ApiExtractor
reads the same definitions, so constructors, inherited virtuals, interface
casts, runtime object schemas and QML registration use the ordinary generator.
There is no dependency on the PySide runtime. Actual extraction and a native
Qt 6.12 control passed for all seven; the public regression fixture also
passes Bend checking. Its combined native package run remains required.

Public forwarding headers are now discovered from upstream registrations.
The extraction uses the `QT_*_LIB` definitions supplied by the selected Qt
CMake targets. This exposes `QExtensionFactory` and the header-only
`QSqlRelationalDelegate`, which was guarded by `QT_WIDGETS_LIB`.

The touch-sequence adapter uses Qt's native `QTest::QTouchEventSequence`.
It retains its target and pointing-device views, supports both window and
widget coordinate spaces, and commits pending events when its Action scope
closes unless automatic commit is disabled. A native Qt 6.12 control delivered
window press, move and release events and widget press and release events,
and checked a deleted native target. This control is separate from the
generated-package integration gate.

The native Quick Test reuse control in `build/quicktest-adapter/probe.log`
passed three tests and returned zero while preserving the same QApplication
instance. The tracked range-template control instantiates flat and table
construction, row insertion and column insertion. Both are focused native
evidence, not final package receipts.

The final gate is a fresh generation followed by
`python3 scripts/check-qt612.py --bundle --generator-checks --reject-system-qt`.
The returned-Result and Action composition laws are checked separately against
the actual Action source. Native effects, scheduling and destruction rely on
integration tests.
