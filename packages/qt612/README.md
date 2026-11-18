# Qt 6.12 bindings for native Bend

This distribution targets exactly Qt 6.12.0, Bend 2.0.40 and Linux x86-64.
Its release version is `qt@6.12.0.1`. It bundles the matching Qt libraries,
plugins and QML assets for the 59 selected modules, including both Charts and
Graphs. System libraries and graphics/platform drivers remain required.
Use an ordinary BendHub import and native Bend compilation:

```bash
bend main.bend -o app
./app
```

The API target is PySide6 6.12 for the selected modules. `coverage.json`
records generated bindings and the remaining unsupported contracts. The
extended native Vulkan experiment is archived separately and is not part of
this package. Qt may still use Vulkan internally for rendering.

Native groups and their runtime assets are retained through Bend's ordinary
reachability. The shared group holds Qt Core and the modules that need no GUI:
Concurrent, D-Bus, Network, QML, Remote Objects, SCXML, WebChannel,
WebSockets and XML. Gui, Widgets, Quick, QuickWidgets (with QuickTest and
Labs StyleKit), WebEngine, Multimedia, Qt3D, Pdf, Designer, Location and
Connectivity are separate groups, as are the GPL-only modules. A program built
on `QCoreApplication` is about 40 MB; with `QGuiApplication` about 63 MB, with
`QApplication` about 72 MB, and a Qt Quick Controls program about 96 MB.

Referencing an optional native type or API retains its group and the groups it
builds on. `QQmlApplicationEngine` belongs to the Quick group, so a QML program
using it has QtQuick. For other QML-only usage, call the corresponding action,
such as `Modules.Quick.load()` for `import QtQuick` with a plain `QQmlEngine`,
`Modules.Multimedia.load()` for `import QtMultimedia` or `Modules.Graphs.load()`,
before loading the QML.

The original generator and Bend glue use MIT. Bundled Qt and third-party
components retain their own licenses; see `LICENSE` and the bundled component
notices and corresponding-source information.

The consumer needs no binding generator, C++ compiler invocation, Qt
development headers, adapter library or custom build command. Bare
`bend main.bend` uses Bend's JavaScript backend, which this package does not
implement. This workspace has not published a public Hub release.

For a local example, put this beside `qt.bend`:

```python
import Base
import ./qt.bend as Qt

# Qt runs this handler inside exec when the button is clicked.
def clicked(code: U32, checked: Bool) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

def run_loop(connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    return Unit{}

def run_button(+button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.setText(button, "Click to exit")
    Qt.QPushButton.show(button)
    Qt.Connection.with(Unit, Qt.QPushButton.connect_clicked(~U32, ~clicked, button, 0), run_loop)

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button => run_button(button))))
```

## Actions and scopes

`Action(A)` composes fallible operations while carrying a resource scope.
All generated public effects return it. `Qt.run(A, action)` evaluates it and
returns `IO(Result<&1, &1, U32 & String, A>)`. A `do Qt.Action<T>` block stops
at the first failure. Use `IO.try(A, Qt.run(A, action))` at the application
boundary.

Owned handles and connections created in that block are registered
automatically. `Qt.run` releases them in reverse acquisition order on success
or returned failure. There is no pool token to pass to constructors.
`Qt.scoped(A, action)` creates a shorter nested scope. `Type.moveToParentScope(value)`
transfers cleanup to its parent scope and fails with EINVAL at the root.
`Type.detachFromScope(value)` removes automatic scope cleanup and leaves the
caller responsible for releasing it. Both require the current pool to own
cleanup. A handle with no cleanup in that pool, including one owned by an
ancestor pool, returns EPERM. Neither changes
Qt parenting or retention. Borrowed getters remain borrowed.
These operations affect the automatic `Qt.run`/`Qt.scoped` pools; an explicit
`Type.with` still releases its resource when the body returns.
Each forked computation should use its own `Qt.run`, and must finish before
any resources it borrows from another computation are released.

Every generated handle type has `Type.with(A, acquire, body)`. It runs the
acquisition action, passes the resource to the body, and waits for cleanup
before returning the body's result. Bend-owned objects and values are released;
deletion is deferred while a tracked Qt dependency needs an object.
Connections are disconnected. Nested scopes release the inner resource
first. Acquisition failure skips the body and cleanup. Cleanup runs after
both success and failure. If only cleanup fails, its error is returned; if
both fail, the original body error takes precedence and the cleanup error is
discarded. A resource already released explicitly or by parent destruction
is accepted during scope cleanup (ESTALE). Explicit `destroy` and
`Connection.disconnect` calls remain strict, and scope cleanup still reports
other errors such as a wrong handle type.

Use object/value scopes with acquisitions that transfer ownership, such as
constructors and returned value copies. Do not scope a borrowed getter result
or put the same owned object in overlapping scopes. Copying a handle does not
create another ownership claim. After cleanup it may be stale, or remain alive
temporarily because Qt owns or retains the object. Runtime checks enforce
validity; the type system does not enforce a lexical lifetime. Join work using
a scoped resource before its scope ends.

Additional composition helpers are ordinary Bend functions:

* `Action.lift(A, io)` includes an `IO(A)` operation such as `IO.print`.
* `Action.fail(A, code, message)` returns a recoverable error.
* `Action.attempt(A, action)` returns the action's `Result` as a value, allowing
  a block to inspect a failure and continue.
* `Action.finally(A, body, cleanup)` runs a cleanup action after either result.
* `Action.using(R, A, acquire, release, body)` supplies custom cleanup for a
  copyable resource. Generated `Type.with` helpers use this function.

Cleanup applies when an action returns `Done` or `Fail`. `IO.die`, `IO.exit`,
process termination and a body that never completes do not unwind scopes.
Keep `IO.try` outside the scopes and use `Action.fail` within them.

## Ownership and retention

QObject construction with a parent leaves native ownership with that parent.
Reparenting an existing object or an explicit supported ownership transfer also
leaves it with Qt. `Type.release` is the typed scoped operation: it destroys an
unretained Bend-owned object, defers a retained owned object, and succeeds
without destruction for a Qt-owned object. `Type.destroy` rejects Qt-owned
objects with EPERM and retained owned objects with EBUSY. The EBUSY check also
protects descendants retained by an owner outside the object's subtree, and
objects that are running one of their handlers. Detaching an object
restores Bend ownership. Supported take methods return ownership to Bend and
preserve an existing handle's identity. Native parent destruction invalidates
all registered child aliases. Overlapping scopes still require care: handles
are copyable and do not encode separate ownership claims.

Supported constructors, setters and collections track objects that Qt keeps
for later use. Observable getters confirm dependencies after replacement,
removal or movement between collections. The policies also cover native item
trees, models, layouts, stream backing storage and scene graph ownership.
For example, `QPushButton.setMenu` retains its menu, while a supported item
insertion transfers ownership to the native container. `QWidget.setStyle`,
`QCompleter.setPopup` and `QDateTimeEdit.setCalendarWidget` use dedicated
lifetime policies. An object cannot be transferred while another active call
or incompatible owner needs it. Known dependencies are rechecked after native
calls, including changes made through QML. Native deletion, including QDrag
deleting its MIME data and `QObject.deleteLater`, invalidates the
corresponding handles.

Direct retention cycles, including cycles through native parenting, fail with
ELOOP before changing Qt. Ordinary QObject parent-tree cycles fail with EINVAL.
Cycles introduced indirectly by native code remain alive and must be broken
explicitly. Object, connection and retention registries grow together without
moving live entries. Object and connection tokens have a 16-bit index, allowing
65,535 simultaneous handles in each registry; retired generations are never
reused. Dependencies fail with ENOSPC before changing Qt if the native token
range is exhausted. `Runtime.liveRetentions` reports active dependencies. See the
workspace's [retention](../../examples/qt612/retention.bend),
[parent and retention](../../examples/qt612/retention-parent.bend) and
[shutdown](../../examples/qt612/shutdown-retention.bend) examples.

Explicit QObject exposure through `QJSEngine.newQObject` and supported QML
context properties retains the object until the engine is destroyed. Releasing
the direct QJSValue or context wrapper does not remove that dependency, since
JavaScript may have stored another reference. Arbitrary object references
hidden inside native plugins or JavaScript graphs remain outside the tracked
boundary.

## The main thread and event loops

Qt and Bend share the process main thread. A Bend effect calls Qt directly and
has Qt's result when it returns. The first Qt effect loads Qt. As in C++, the
program then constructs its single application object, which receives the
program's command-line arguments:

```bend
def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QGuiApplication.with(Unit, Qt.QGuiApplication.new(), app => body())))
```

`QCoreApplication.new`, `QGuiApplication.new` and `QApplication.new` choose
the kind, and only the chosen kind's modules are retained. A second `new` fails
with EEXIST. Constructors and static functions of QtGui and QtWidgets classes,
and of classes deriving from them, fail with ENXIO before the GUI application
they need exists, instead of Qt aborting the
process; static setters of global defaults, such as
`QSurfaceFormat.setDefaultFormat` or `QQuickWindow.setGraphicsApi`, and
`QtWebEngineQuick.initialize` work beforehand, as Qt documents. The package
owns the application: the handle is released at the end of the scope, and the
object lives until `Qt.run` ends. If Qt cannot be loaded, or the loaded Qt
version differs from 6.12.0, that effect fails with ELIBACC and a message,
which `IO.try` reports. When the Bend `main` returns, the package destroys the
objects Bend still owns and then the application. `IO.exit` ends the process
without that teardown.

Qt processes events only inside a Qt event loop: `QCoreApplication.exec()`
(which returns the exit code as an `Int32`), `QEventLoop.exec`, `QDialog.exec`
and `QCoreApplication.processEvents`. Timers, queued signals, deferred
deletions and window updates therefore happen only while one of these runs.
While a Qt loop waits, Bend's other computations keep running: tasks started
with `IO.fork` or `IO.spawn`, sleeps, sockets and channels. They may call Qt,
for example to exit the loop. A typical program connects a handler that calls
`QCoreApplication.exit__Int32`, then calls `exec()`. `Future_T.await` and
`QQmlIncubationController.incubateWhile` wait the same way.

## Handlers

Qt calls Bend through handlers. A signal, an overridden virtual method or a
stored function runs its Bend handler at once, on Qt's own stack, like a C++
slot or override. Qt has the handler's answer before the native call returns.

A handler is a closed top-level function `f` plus a `Data` state value. Each
API that installs one takes them as `~S: Data, ~f: S -> ... -> Action(R)`, with
the state as its last value argument. `f` receives the state first, then Qt's
arguments. It must be a top-level definition or a closed lambda, and its
parameters must be plain (no `+`). Each call gets its own copy of the state.
Put whatever the handler needs, such as object handles, in the state. To make
a result visible outside the handler, change a Qt object, for example set the
name of a probe object passed in the state, and read it afterwards. The
package releases a handler once Qt drops it: a closed connection, a
destroyed override object or a destroyed stored function.

* Arguments are valid during the call. Strings are copied. Value arguments
  such as QModelIndex and QVariant are copies owned by the call: copy one
  again to keep it. QObject pointers become borrowed handles, with zero
  representing null; receiving one does not acquire ownership or retain its
  object.
* A handler may call Qt, which may run other handlers. Its call-token table
  grows with nesting within the handle format's 65,535-slot limit. Expired
  token generations are retired rather than reused.
* A handler that fails makes the Qt operation it ran under fail with the same
  code and message. That operation is the innermost Qt call started by Bend
  that is running: `QPushButton.click` fails with 44 when its clicked handler
  fails with 44. A failure during `exec` or `QEventLoop.exec` also ends that
  loop at once. A failure during a nested `processEvents` belongs to
  `processEvents`, not to an outer call.
* A handler that must answer Qt cannot wait (sleep, channel, socket or other
  waiting IO): its Qt operation fails with EWOULDBLOCK (11). A handler that
  answers nothing may wait. Qt then continues without it, and its remainder
  runs later as an ordinary Bend computation.
* `IO.spawn` inside a handler starts a computation that runs afterwards.

See [main](../../examples/qt612/main.bend),
[signals](../../examples/qt612/signals.bend),
[callbacks](../../examples/qt612/callbacks.bend) and the
[nested event fixture](../../scripts/fixtures/callback-events.bend).

### Signals

`X.connect_signal(~S, ~f, object, state)` connects the Bend handler `f` and
returns `Action(Connection)`. The generated function checks the handler's
argument types: `f: S -> A1 -> A2 ... -> Action(Unit)`. No signal descriptor
type is needed. Overloaded signals have type suffixes, for example
`QCompleter.connect_activated__String` and
`QCompleter.connect_activated__QModelIndex`. For example:

```python
def range_changed(probe: Qt.QObject, low: Qt.Int32, high: Qt.Int32) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "range")

def slider_case(+probe: Qt.QObject, +slider: Qt.QSlider) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QSlider.connect_rangeChanged(~Qt.QObject, ~range_changed, slider, probe),
    connection => connected_slider(slider, probe, connection))
```

A signal emitted on the main thread runs its handlers during the call that
emits it: `QSlider.setRange` returns after `range_changed` has run.
`Connection.disconnect` closes a connection, and `Connection.with` scopes it.
`Runtime.liveConnections()` counts open connections; the registry grows up to
65,535 slots. Destroying the sender closes its connections.

For signals with mutable reference arguments, the handler returns
`Action(SignalReply_<types>)` with the new values, which Qt reads before the
signal returns. For example, a handler connected through
`QNetworkAccessManager.connect_authenticationRequired` returns
`Qt.SignalReply_QAuthenticator{authenticator}` after filling in the
credentials.

If a signal with mutable arguments is emitted on another thread, that thread
waits for the main thread to run the handler and fill the reply. The main
thread must be running a Qt event loop. Supported temporary pointer payloads,
such as volume texture data, are copied during emission and queued for the
main thread. Closing the connection discards a pending pointer snapshot.

`QObject.connect_destroyed` takes a handler receiving an `ObjectIdentity`, the
handle word of the destroyed object, without access to the dying object. The
connection closes itself after that one delivery, so a later
`Connection.disconnect` fails with ESTALE, which `Connection.with` accepts.
Copied values such as QModelIndex retain their native validity rules: model
changes or destruction can make a received value stale. See
[object signals](../../examples/qt612/object-signals.bend) and
[destruction](../../examples/qt612/destruction.bend).

### Signals declared in Bend

Declare a signal once in a top-level function. Its argument witnesses determine
the types required by both `Signal.connect` and `Signal.emit`:

```python
def progressChanged() -> Qt.Signal:
  Qt.Signal.define("progressChanged", [Qt.int32(), Qt.string()])

def received(probe: Qt.QObject, percent: Qt.Int32, title: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, title)
```

Create the owning object with
`QObject.newWithSignals("Task", [progressChanged()])`. It returns an owned
`QObject`; use `QObject.with` to scope it. Then connect and emit with the same
closed declaration:

```python
Qt.Signal.connect(~progressChanged(), ~Qt.QObject, ~received, object, probe)
Qt.Signal.emit(~progressChanged(), object, Qt.Int32{42}, "Loading")
```

The connection returns `Action(Connection)` and uses the usual connection
scope. On the main thread the handler runs before emission returns. Other Qt
code can discover the signal through the object's meta-object, connect it to
Qt slots, or observe it through QML `Connections`. See the
[complete scoped example](../../examples/qt612/custom-signals.bend).

Use `Qt.bool()`, `Qt.int32()`, `Qt.u32()`, `Qt.f64()` or `Qt.string()`
for native primitive arguments. Each supported Qt class has an argument
descriptor, for example:

```python
def buttonReady() -> Qt.Signal:
  Qt.Signal.define("buttonReady", [Qt.QPushButton.arg()])

def ready(state: Unit, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.QPushButton.setText(button, "Ready")
```

The handler receives `QPushButton` directly and the native signature contains
`QPushButton*`. QObject subclasses and public, copyable Qt metatype values have
these generated descriptors; unsupported class reasons are in `coverage.json`.
Use `Qt.QColor.arg()` for QColor, `Qt.variant()` for QVariant,
`Qt.variantMap()` for a string/QVariant entry list
(`List<&2, Qt.PairValue<String, Qt.QVariant>>`), and `Qt.variantList()` for
`List<&2, Qt.QVariant>`. QML can inspect the native object properties and map
keys. `Qt.qobject()` intentionally declares a general QObject reference.

QObject arguments are borrowed and do not transfer ownership. They must belong
to Bend's main thread. Queued handlers reject objects deleted before delivery,
including QObject references nested in QVariant maps or lists. Null is
preserved as a handle with word zero. Value arguments are native copies owned
by the callback scope, including values nested in maps; explicitly copy values
to keep them after the handler returns or first waits. External data referenced
by Qt values still follow Qt's lifetime rules.

Custom Bend data uses
`Qt.arg(~Payload)`, with a handler that receives `Payload` directly. This
spelling denotes opaque Bend data; QML can retain and forward it, while field
access uses a QVariant map or a QObject with exported properties. For example:

```python
type Payload is Data:
  Payload{number: U32, text: String}

def delivered() -> Qt.Signal:
  Qt.Signal.define("delivered", [Qt.arg(~Payload)])

def received(state: Unit, value: Payload) -> Qt.Action(Unit):
  match value:
    case Payload{number, text}: Qt.Action.lift(Unit, IO.print(text))
```

`Qt.QVariant.fromData(~Payload, value)` and
`Qt.QVariant.toData(~Payload, variant)` pack and recover the same Data type.
Records, lists and generic Data types work without defining a Qt metatype for
each payload. A mismatched transport type fails with EINVAL. Qt and QML copies
retain the payload; releasing their last copy on another thread defers the Bend
heap release to its main thread. Use the original closed Data declaration in
the codec: the pinned Bend compiler gives type-level aliases a distinct
transport identity. See the [typed-data example](../../examples/qt612/typed-data.bend).

An empty list declares a signal with
no arguments. Handlers return `Action(Unit)`; declarations do not add mutable
reply arguments. A class's declarations are fixed when it is first created,
and a different declaration list for the same class name fails with EEXIST.
The runtime caches immutable class metadata until shutdown. Counts follow Qt's
native metadata index range and available memory.

Dynamic metadata uses Qt 6.12's moc format and public Qt connection APIs.
Signals and QObject schemas use the same complete payload as other APIs.
Consumers use ordinary Bend
compilation and need no generator or Qt development tools.

### Virtual methods

`Type.newOverride` constructors create objects whose virtual methods can run
Bend handlers. The zero-argument form uses the default constructor; the
others are named by their arguments, as in `QObject.newOverride__QObject` for
a parent. Unsupported native pure-virtual methods can make an override
constructor return ENOTSUP.

`D.Virtual.method.handle(~S, ~f, object, state)` installs the handler for one
virtual method of one override object. `D` is the class that declares the
method, so pass the object upcast, as in `Qt.QAbstractListModel.as_QAbstractItemModel(model)`.
Installing again replaces the handler. `f: S -> args... -> Action(R)`, where
`R` is the method's result (`Unit` for void). Overloaded virtual methods use
the ordinary overload suffixes, as in `QStyle.Virtual.polish__QWidget`. Only
objects made by `newOverride` run handlers.

```python
def row_text(state: Unit, index: Qt.QModelIndex, role: Qt.Int32) -> Qt.Action(Qt.QVariant):
  Qt.QVariant.fromString("Bend handler value")

def base_header(state: Unit, section: Qt.Int32, orientation: Qt.Qt.Orientation, role: Qt.Int32) -> Qt.Action(Qt.QVariant):
  Qt.Virtual.base(Qt.QVariant)
```

A handler that fails with 38, which `Qt.Virtual.base(R)` returns, runs the
C++ base implementation instead, as an override calling its base class does.
A virtual method without a handler also runs the base implementation. A pure
virtual method has none, so calling it without a handler fails the current Qt
operation with ENOSYS (38).

Methods with mutable reference parameters return a generated
`HandlerReply_*` record: the result, if any, followed by the new values. For
example, a `QValidator.Virtual.validate` handler returns
`HandlerReply_QValidator_State_String_Int32{state, text, position}`. The
reply is validated as a whole before Qt's references are written. A returned
object transfers ownership only when the native contract requests it.
Borrowed object results are retained by the override object until it is
destroyed. See [callbacks](../../examples/qt612/callbacks.bend),
[mutable references](../../examples/qt612/mutable-callbacks.bend),
[factories](../../examples/qt612/factory-callbacks.bend) and
[retained results](../../examples/qt612/retained-callbacks.bend).

### Stored functions, QML, logging and cleanup handlers

Qt methods that take a `std::function` have a
`X.methodWithHandler(~S, ~f, self, args..., state)` form, for example
`QWebEnginePage.runJavaScriptWithHandler__String(~Qt.QObject, ~javascript, page, "String(21 * 2)", probe)`.
Qt owns the stored function, and destroying it releases the handler. Its
arguments are copied for the call. Generated helpers named
`Owner.Handler.method.*` decode those arguments; programs do not call them.
See the [function fixture](../../scripts/fixtures/function-callbacks.bend).

Typed child searches use `Class.findIn(root, name)`, `findAllIn` and
`findAllMatchingIn`. Their `With` variants accept Qt child-search options as the
last argument, including direct children only. Results preserve Qt ownership.
See [the convenience adapters](../../docs/qt-convenience-apis.md).

### Bend types in QML

`QObject.define(name, properties)` declares a class and returns an `ObjectType`
schema. Use another native base's `.define` function to select that base.
`ObjectType.Instance(schema)` is the type of its instances.

`Property.define`, `Signal.define` and `Method.define` describe the members.
Their argument and result types use `TypeDescriptor` values, such as `string()`,
`int32()`, `variantMap()` and `QPushButton.arg()`.

`ObjectType.new(~schema)` uses the default constructor. A generated
`Base.newAs(~schema, ...)` selects another constructor. `ObjectType.attachUsing`
supports advanced attachment to an acquired native object.
`ObjectType.get`, `set`, `call`, `handle`, `emit` and `connect` accept the typed
instance directly. `Property.set` calls a property's setter;
`Property.writeStorage` updates its storage and emits change notifications.

A `list(~element)` property is a native `QList`. QML reads it as an array and
uses it directly as a `Repeater` or `ListView` model; setting it from Bend
refreshes those views. Elements can be numbers, strings, Bend-declared classes
(`list(~ObjectType.arg(~Card()))`) and values, or further lists.

`Qml.registerType` and the singleton registration functions return a
`Qml.Registration(schema)` controller, which is distinct from an instance.
Schema-free registrations use `Qml.RegistrationHandle`.
`ValueType.define` declares a QML value type whose instances copy independently.

The [Bend types in QML guide](https://github.com/Bobini1/bend-qt/blob/main/docs/bend-qml-types.md)
covers properties, methods, signals, values, enums, inheritance, registrations,
singletons and factories, with examples and lifetime rules.

### Logging and cleanup handlers

`MessageHandler.install(~S, ~f, state)` with `f: S -> LogMessage ->
Action(Unit)` receives Qt's log messages; `MessageHandler.restore()`,
`lastError()` and `format(message)` complete it. Messages logged on another
thread, or while the handler runs, go to the previous handler. A failed
logging handler never fails the Qt call that logged; the message then goes to
the previous handler. See the
[message handler fixture](../../scripts/fixtures/message-handlers.bend).

`PostRoutine.add(~S, ~cleanup, state)` registers `cleanup: S -> Action(Unit)`
with Qt's application destructor. Registrations have application lifetime and
run in reverse order after Bend main returns. `remove` cancels early, and
`PostRoutine.with` cancels at the end of its body. Cleanup must finish without
waiting. A failure preserves later cleanup and supplies the exit status when
main otherwise succeeds. See [cleanup callbacks](../../docs/qt-convenience-apis.md)
for the pinned Bend runtime boundary.

`QStringConverterBase.State.Cleanup.install(~S, ~f, state_object, state)`,
`.remove` and `.installed` manage a converter state's cleanup function. RHI
cleanup and readback handlers are described below.

## Other threads

Bend runs on the main thread only. Bend effects may use objects that live
there; a call on an object owned by another thread fails with EXDEV (18).
`QObject.moveToThread` is an ordinary Qt method, so moving an object away
makes it unavailable to Bend calls.

* A signal emitted on another thread is delivered through Qt's queued
  connection. Its handler runs on the main thread when that thread runs a Qt
  event loop.
* A virtual method that Qt calls on another thread runs its handler on the
  main thread while the calling thread waits (a blocking queued call). The
  main thread must be inside a Qt event loop to take the call.
* Native reads, writes and named method calls on a runtime-defined QObject
  use the same dispatch. Its owning thread waits while the main thread accesses
  Bend storage and runs its handlers. Direct Bend calls on worker-affine native
  objects still return EXDEV.
* Rendering virtual methods that Qt calls on its render thread skip their
  handler; see `Render.useGuiThread` below.

`QThreadPool` jobs use `QRunnable.newOverride` with a
`QRunnable.Virtual.run.handle` handler. The package keeps the QRunnable and
its handle registered until the job finishes, and it applies Qt's auto-delete
on the main thread afterwards. While a job is queued or running,
`QRunnable.destroy`, `setAutoDelete`, a second start and a running job's
`tryTake` are refused (EBUSY, or false for `tryTake`). `tryTake` and `clear`
return queued jobs as Qt does. `QThreadPool.waitForDone` behaves like Qt and
does not process events, so it cannot finish a job whose handler needs the
main thread. `QThreadPool.awaitDone(pool)` runs the event loop until completion;
`awaitDoneFor(pool, Int32{milliseconds})` returns whether the pool finished
before its timeout. Zero polls and a negative timeout waits indefinitely.
These operations also propagate job-handler failures. A job awaiting its own
pool fails with EDEADLK. The
[await example](../../examples/qt612/thread-pool-await.bend) shows the usual flow;
the [thread pool example](../../examples/qt612/thread-pool.bend) also exercises
Qt's lower-level blocking waits, reservations and cancellation.

## Proof boundary

The shared Action, Codec and Lifetime definitions have laws checked with
Bend 2.0.40's `--verdict`. They cover returned-error precedence, scope
sequencing, cleanup normalization, word/string list round trips, pair,
optional and fixed-array framing, wide scalar bit preservation, and pure
ownership, retention, incubation, future consumption, RHI cleanup access and
texture reply decisions. Returned-Result policy and CPS composition are
proved. A maintainer check verifies that this package contains the same
definitions. Native effects, scheduling and destruction rely on integration
tests, as do generated per-type codecs, native conversions, dependency
tracking, Qt's ABI and GPU execution. Fatal exits do not unwind scopes.

## API names and coverage

The API inventory comes from PySide6 6.12's unmodified type-system definitions.
The package discovers classes across the selected Qt modules automatically,
including QQmlEngine, QQmlComponent, QQmlProperty, QQuickItem and QQuickWindow.
A method that can be called with only one Bend argument list keeps its plain
name, such as `QObject.setProperty`. Otherwise each name spells the Bend
argument types it takes: `QPushButton.resize__Int32_Int32` and
`QPushButton.resize__QSize`. Zero-argument forms keep the plain name.
Trailing C++ default arguments produce shorter forms named the same way:
`QUrl.new__String(text)` and `QUrl.toString(url)` supply Qt 6.12's original
C++ defaults for the omitted arguments. Python-specific replacement defaults
are not applied. Each definition in `qt.bend` is preceded by a `# C++:` comment
with the bound signature and any defaults it supplies.

C++ overloads that Bend cannot tell apart are one binding. For example, the
`QString`, `QAnyStringView`, `const char *` and rvalue forms of a parameter all
take a Bend `String`. The binding calls the overload C++ itself would choose
for an owned value: the owning type over a view, a const reference over an
rvalue, the wider number and the non-const member. A method hidden by a
subclass declaration is bound as C++ name lookup sees it, so
`QApplication.setFont__QFont` calls `QApplication::setFont`. When overloads
with the same Bend arguments return different types, the names spell their
C++ parameter types instead, as in `QDataStream.readBytes__charPtr_qint64`.
No public name contains a hash.

Published names are pinned in the generator's name lock. A newly supported
overload never renames an existing binding, and a Qt signature replacement
with the same Bend shape keeps its name. A removed name is never reused for a
different function. `coverage.json` records exact generated names, merged
overloads with the binding that serves them, removed names, excluded classes
and signatures, and Shiboken extraction omissions. Inherited methods also
appear on derived classes, while their native wrappers are shared.

Mutable QString, scalar and supported container references return their updated
values in generated `Outputs_*` Data records. The ordinary return value is
`arg0` when the native method is non-void, followed by updated/output arguments
in original parameter order. Void methods return only their outputs. For example,
`QColor.getRgb` returns four Int32 fields; `QTransform.inverted` returns a copied
QTransform followed by a Bool. Use the record's `.with` scope when it contains
owned value copies. Mutable value and QObject references update the existing
checked handle in place; the result record never owns an input-handle alias.
Native reference returns use copied values or checked aliases according to
the method's storage contract.

Removed pointer parameters become scalar outputs only when an audited upstream
Shiboken template establishes that convention. Other pointer methods have
explicit buffer, view, output or lifetime adapters where the native contract
provides enough information.
Output-bearing methods currently take every public input explicitly. Inputs
are validated before invoking Qt, but native mutations are not rolled back if
output conversion fails. Arithmetic, comparison and assignment operators use
names such as `op_add`, `op_equal` and `op_assign`, with normal overload suffixes.

The coverage report records remaining unsupported signatures and their reasons.
Bounded raw buffers, native object identities, model/item ownership, generated
virtual subclasses and Bend-backed QML composite types have adapters.
Arbitrary pointers and unspecified native allocation/lifetime contracts remain
excluded. Modules outside the selected set are listed in the report. Loading
an ordinary QML document and interacting with its existing Qt objects works
through the same generated API and consumer build command.

## Values and conversions

Qt's signed `int` is represented by `Int32{bits: U32}` because Bend has no
built-in signed integer. Use `Int32{42}` for a nonnegative value,
`Int32.neg(7)` for -7, and `Int32.word` to read its two's-complement bits.
Enums and flags have distinct types with 32-bit or 64-bit storage according to
their native representation. Qt integer aliases are converted with range
checks for 8-bit and 16-bit inputs. `QCborTag{lo, hi}` preserves 64-bit tags.
Strings and string views are copied through UTF-8. `QByteArray.fromBytes` and
`toBytes` use `List<&2, U32>` and preserve every byte, including embedded zeros.
`fromBytes` rejects values outside 0 to 255. A native `QByteArrayView` input uses
a checked `QByteArray` handle for the duration of the call. A returned view
becomes an owning `QByteArray` copy that can outlive its source, so use its usual
scope. These conversions do not infer lengths for raw C pointers.

`F64{lo, hi}` preserves all bits of Qt's double/qreal. `F64.fromString`,
`toString`, `add`, `subtract`, `multiply`, `divide` and `equal` return Actions.
Int64 and UInt64 preserve two's-complement or unsigned bits in the same two-field
form. No additional Hub dependency is needed. C++ float arguments are narrowed
to float by the native call, while qreal arguments retain double precision.
`QVariant.fromF64` and `toF64` preserve the exact value; mismatched QVariant
conversions return an error. String and Bool conversions are also provided.

Containers convert automatically from extracted template arguments. QList,
QVector, QStringList and QSet use `List<&2, T>`. QMap, QHash, QMultiMap and
QMultiHash use `List<&2, PairValue<K, V>>`; std::pair and QPair use
`PairValue<A, B>`. Conversions recurse through nested containers. Lists retain
order and duplicates. Qt sets remove duplicates, unique maps replace earlier
entries with the same key, and multimaps retain duplicates. QMap orders keys;
hashes and sets do not promise iteration order. No proof claims that these
native container transformations preserve an arbitrary input list unchanged.

Value elements returned inside a container are owning copies. Use generated
container scopes such as `List_QUrl.with` or `List_Pair_F64_QColor.with` to
release them, including nested value elements. Input value handles remain
owned by their existing scopes. Borrowed QObject elements are not destroyed
by container cleanup. Cleanup visits every element even when an earlier
release fails. Failed native output conversion rolls back copies already
allocated; input conversion validates all elements before calling Qt.

## Handles

Object and value references are typed, copyable handles, validated on every
native use. Constructors produce Bend-owned objects unless Qt acquires native
ownership, for example through a parent. A `Type.with` scope releases them
according to ownership and retention; explicit `destroy` enforces the stricter
rules above. When the program ends, remaining owned objects are collected as
their dependencies disappear, including after QApplication destroys its
children. Unbroken native dependency cycles can prevent collection. Dropping a
Bend handle does not destroy its Qt object. Parent destruction invalidates
child handles. Stale, mistyped and disconnected handles return errors. A zero
object handle represents null only where the Qt API accepts a null pointer.
All other Qt method preconditions still apply.

The registries grow up to 65,535 object slots and 65,535 connection slots. A
generation counter prevents a stale handle from referring to a reused slot;
exhausted generations retire their slots. References
returned to existing objects preserve identity. Getter results are borrowed
unless an ownership rule states otherwise. QQmlComponent.create and
beginCreate return owned roots, as does QQmlIncubator.object when creation is
ready. Use QObject.with for those roots. `Derived.cast(object)` checks the
dynamic type and preserves identity without acquiring ownership. QObject
upcasts are pure handle aliases. Value-class upcasts return Actions that
allocate an owning copy of the base value when that base is a copyable value.
Native object bases preserve a checked alias. Place the owning root's scope
inside the engine and component scopes.

Model indices, text values and iterators are checked against their native
origin. Structural model changes can invalidate an ordinary `QModelIndex`;
use `QPersistentModelIndex` when Qt's persistent-index behavior is needed.
Indexes do not keep a destroyed model alive. Text edits can invalidate text
values and iterators. Copying a handle or a value does not remove those
dependencies, and scopes can still release stale owned copies. See
[model indices](../../examples/qt612/model-indices.bend) and
[iterators](../../examples/qt612/iterators.bend).

Const native getters create read-only handles when no mutable alias is known.
Mutation fails with EPERM. A later explicitly mutable native getter can establish
writable storage for that identity. Pure Bend upcasts never change this state.
Classes with inaccessible native destructors support borrowed access. Where a
protected virtual destructor permits a derived owner, generated constructors
use that owner and its checked deleter. Foreign objects still cannot be deleted
through an inaccessible base destructor.

## Bundled Qt and native payloads

The default runtime comes from this package. It is extracted into a private,
content-addressed cache, `$XDG_CACHE_HOME/bend-qt/<id>` or
`~/.cache/bend-qt/<id>`, where `<id>` covers the package's runtime files and
the native groups the program uses. Files are checked by SHA-256 when they are
written. Later starts compare a stamp of every file's inode, size, mode and
modification time; any difference makes that start check and repair the
directory by content again. Each native group's library is decoded once into a
directory of its own there, named by its content, and later starts load it
without decoding while it matches its stamp. A running program holds its
directories, and a starting program removes, at most once a day, directories
that no program has used for a week. Library, plugin, QML and WebEngine paths point
into that runtime. A system Qt update cannot replace
these bundled libraries, and there is no automatic system-Qt fallback.

`BEND_QT_RUNTIME` selects an explicit complete replacement installation with
the matching native ABI. Qt or ICU already loaded from a different installation
is rejected. `BEND_QT_LIBRARY` is reserved for installed-runtime maintainer
fixtures.

The package also exposes RHI and a few explicitly identified private helpers.
These have a stricter ABI contract than ordinary Qt APIs. The complete package
therefore requires its matching Qt 6.12.0 runtime, including the matching
plugins. `Runtime.hasRhiBindings()` reports the profile's RHI availability.
There is no reduced compatibility fallback. To target another Qt release,
use a package built for that release and recompile the Bend application.
Another Qt version can coexist on the system while the application continues
to use its bundled 6.12.0 runtime.

The package embeds separate compressed native ELF payloads in its C effects.
The first start decodes each payload into the per-user Qt cache, and later
starts load it from there; consumers do not compile C++ or install a companion
library. C++ exceptions are translated into Action errors.
RTTI is enabled for Qt code that dynamically inspects generated native
subclasses. The package supports one Qt package and one Bend runtime per
process. GPU execution of Bend, other architectures and reusable runtime
embedding are not implemented.

The generator uses the unmodified
[Shiboken ApiExtractor 6.12.0](https://github.com/pyside/pyside-setup/tree/v6.12.0/sources/shiboken6_generator/ApiExtractor)
and Qt 6.12.0 headers. The generated package includes compiler output from
Qt inline/template code; upstream copyright and license terms apply to that
code. The extractor and its dependencies are maintainer tools, not consumer
dependencies.

## Finding child objects

Qt's `findChild<T *>` and `findChildren<T *>` are C++ templates, so every
QObject class `T` has typed static entries instead:

* `T.findIn(root, name)` returns `Maybe(T)`: the first `T` below `root`;
* `T.findAllIn(root, name)` returns every `T` below `root`;
* `T.findAllMatchingIn(root, pattern)` matches object names against a
  `QRegularExpression`.

The search covers all descendants, as Qt's default does. An empty name matches
every object. Results are borrowed handles, like `QObject.children`: the
parent still owns and destroys them. This is how a Bend program reaches widgets
that `QUiLoader` built from a Qt Designer form, as in
`examples/qt612/child-lookup.bend`:

```python
button: Maybe<&2, Qt.QPushButton> <- Qt.QPushButton.findIn(root, "okButton")
edits: List<&2, Qt.QLineEdit> <- Qt.QLineEdit.findAllIn(root, "")
```

## Qt Quick and scene graphs

The workspace's `examples/qt612/quick.bend` demonstrates QML loading, a
handler for a title change made by a QML timer inside `exec`, exact qreal
property access and rendered-image inspection. The matching Qt Quick QML
runtime is bundled. An explicit replacement must contain the required QML
modules and plugins. The consumer still runs `bend main.bend -o app`.

Call `Render.useGuiThread()` before creating any Quick window to select Qt's
basic render loop, which renders on the main thread. Bend rendering handlers,
such as an `updatePaintNode` handler, then run while Qt keeps the correct
rendering context active; for example, `grabWindow` synchronizes the scene
graph and runs `updatePaintNode` inside it. The choice changes the rendering
thread, not the selected graphics API. Without it, Qt renders on its own
thread, rendering virtual methods called there skip their Bend handler, and
scene graph operations outside a render handler fail with EPERM. The
`scenegraph-callbacks.bend` example draws a rectangle and inspects rendered
pixels. `QQuickWindow.scheduleRenderJob` accepts a `QRunnable.newOverride` job
in this mode; Qt owns and deletes each job after running or discarding it. See
the [render jobs example](../../examples/qt612/render-jobs.bend).

`QSGRendererInterface.getResource__QQuickWindow_String(interface, window, key)`
and its enum overload return `NativeRenderResource`, as does
`QSGRenderNode.RenderState.get`. Query `isValid` or `isNull` inside the
originating render handler, and scope the returned handle. The handle expires
when that handler returns, even if the window survives. `unsafeAddress` exposes
the native address only while the handle is valid; external native code must
still obey the backend's pointer, thread and lifetime rules. A resource query
can return a valid handle containing a null pointer.

## RHI resources, frames and readbacks

The RHI helpers use the exact Qt 6.12.0 payload described above. Start with
`QRhi.newNull()` for CPU-side checks, or a typed backend constructor such as
`QRhi.createWithGles2(parameters, flags)`. Backend parameters retain the
supported Qt objects they reference. An OpenGL fallback surface remains owned
by its normal scope, and the RHI instance keeps it alive while needed.

`QRhi.withOffscreenFrame` begins a frame and supplies its borrowed command
buffer to the body. It closes an open pass and ends the frame after either
`Done` or `Fail`, preserving the body's error when cleanup also fails.
For example, this records an empty frame on the Null backend:

```python
def offscreen() -> Qt.Action(Unit):
  Qt.QRhi.with(Unit, Qt.QRhi.newNull(), rhi =>
    Qt.QRhi.withOffscreenFrame(Unit, rhi, command =>
      Qt.Action.pure(Unit, Unit{})))
```

Use `QRhiBuffer.with`, `QRhiTexture.with` and the other resource scopes for
objects returned by `QRhi.new...`. Resources retain their RHI instance.
Descriptor copies retain the resources they reference, and mixing resources
from different RHI instances fails. A command buffer expires at frame end.
Submitting a resource update batch consumes its handle, while releasing an
unsubmitted batch returns it to Qt's pool. Explicit resource destruction
during an active frame is rejected; scoped release can defer destruction.

`QRhiResourceUpdateBatch.readBackBufferAsync(~S, ~f, batch, buffer, offset,
size, state)` and `readBackTextureAsync(~S, ~f, batch, description, state)`
install a readback handler. Qt runs it when the frame completes, with a
`QRhiReadbackResult` that is valid during the call; its `Fields.data` getter
returns an owning QByteArray copy. A batch released before submission never
runs its handler. Texture formats, transfer flags, sample counts and backend
feature requirements remain Qt preconditions. See the
[Qt readback contract](https://doc.qt.io/qt-6/qrhiresourceupdatebatch.html).
`QRhi.onDestroyed(~S, ~f, rhi, state)` returns a `Connection` whose handler
receives the destroyed instance's `ObjectIdentity`.

`QRhi.addCleanupHandler(~S, ~f, rhi, key, state)` installs a cleanup handler
that Qt runs before its backend teardown; `f` receives the U32 key.
Registering the same key replaces the handler, and
`QRhi.removeCleanupHandler(rhi, key)` removes it.
`QRhi.addCleanupHandlerUnkeyed` handlers cannot be removed individually.
Native handler order is unspecified. During native cleanup, only the running
handler may access that RHI's resources. Registering or removing handlers
during cleanup returns EBUSY. Normal root destruction still respects resource
retention. See the [cleanup fixture](../../scripts/fixtures/rhi-cleanup.bend).

Supported native record helpers, such as `QRhi.nativeGles2Handles`, return
checked copies. Raw native graphics handles remain subject to the exclusions
in `coverage.json`.
The returned record copy retains its native origin. A command record expires
at frame end, `finish`, or a pass or external-recording transition that may
replace Qt's native command buffer. Its QRhiCommandBuffer wrapper can remain
usable within the same frame. These records do not acquire ownership of
external graphics objects. Arbitrary external pointer lifetimes and Qt
Quick's own frame lifecycle are not covered by the explicit frame scopes.
Qt's external recording preconditions still apply. Start the pass with
`ExternalContent` before calling `beginExternal`, and do not issue ordinary
draw or set commands until `endExternal`. The binding does not validate that
entire native subphase contract.
The [RHI fixture](../../scripts/fixtures/rhi-lifetimes.bend) exercises Null and
OpenGL creation, readback, batch consumption, descriptor retention and errors.
It also contains maintainer probes for native deletion.

## Accessibility

An accessibility `interface_cast` handler returns an `AccessibleFacet`.
Use a typed constructor such as `AccessibleFacet.fromActionInterface`, or
`AccessibleFacet.none()` when the requested interface is unavailable. The
binding checks that the returned facet matches the requested interface kind
and retains the specialized interface for the override object's lifetime. The
specialized interface can be a separate Bend implementation. See the
[accessibility fixture](../../scripts/fixtures/accessible-facets.bend).

## Values and native storage

Registered, copyable Qt values have generated `QVariant.from_Type` and
`QVariant.to_Type` converters, such as `QVariant.from_QModelIndex`.
The `to_Type` converter requires the exact native metatype. `QVariant.copy`,
`assign` and `swap` preserve tracked dependencies, including model-index validity.
Use owning scopes for the returned QVariant and value copies.

`MetaStorage` owns aligned storage for a Qt metatype. `MetaStorage.fromVariant`
creates initialized storage, while `MetaStorage.allocate` leaves it uninitialized
until a supported `QMetaType.construct` call succeeds. `MetaStorage.toVariant`
copies independent initialized storage. Borrowed storage views keep their source
lifetime and cannot always be converted to owning values. Typed storage also
supports gadget properties,
`QGenericArgument.fromStorage` and `QGenericReturnArgument.fromStorage`.
The binding checks type, initialization, mutability and lifetime before native
access. See [metatypes](../../examples/qt612/metatypes.bend) and
[generic invocation](../../examples/qt612/generic-invocation.bend).

`ImageBuffer.new` allocates stable pixel storage, and `ImageBuffer.fromBytes`
copies a QByteArray into new pixel storage.
Pass it to `QImage.fromBuffer` or `QImage.fromBufferWithStride`, and use
`ImageBuffer.bytes` for a scoped `MemoryView` of the bytes. Qt image copies keep
the storage alive after the ImageBuffer handle is released. The
`fromReadOnlyBuffer` variants preserve Qt's detach-on-write behavior.
Dimensions, extent and scanline alignment are checked before construction.
See [image buffers](../../examples/qt612/image-buffers.bend).

`QStringBuffer` supplies mutable storage for retained QString pointers, including
QTextStream's string constructor and `setString`. Its `new`, `value` and `replace`
methods use Bend strings. `QTextBoundaryFinder.withWorkingBuffer` owns both its
text and its optional working buffer, and copies preserve that backing storage.

## Shared and asynchronous values

`QFormLayout.TakeRowResult` manages the items returned by `takeRow`. Copies share
ownership of those items, and `Fields.labelItem` and `Fields.fieldItem` return
borrowed handles. Field setters can adopt independently owned layout items or
share an item held by another aggregate. Clearing a field releases its claim.
`takeLabelItem` and `takeFieldItem` transfer an item to the caller, but return
EBUSY while another aggregate field or copy shares it. Release a transferred
item with `QLayoutItem.with`. Widget items retain their referenced widgets.
See the [taken-row fixture](../../scripts/fixtures/taken-rows.bend).

Concrete `QSharedPointer<T>` signatures produce `Shared_T` carriers with `clone`,
`data` and `isNull`. Clones preserve Qt's shared ownership. A raw pointee handle
cannot be destroyed or transferred independently; when the last tracked holder
is released, its borrowed aliases expire. Keep a holder alive while using them.

Concrete `QFuture<T>` signatures produce `Future_T` and watcher carriers.
`Future_T.await` runs a Qt event loop until the future finishes, so Qt keeps
processing events and other Bend computations keep running.
`resultAt` returns a ready copy or an error; it never waits for the result.
`takeResult` consumes a completed result, including a move-only payload. It
returns EAGAIN while the computation is unfinished and ENODATA when no result
remains. Native stored exceptions become Action errors. Consumption invalidates
the result through all copies of the future and its watcher aliases, and
discards any remaining results. `FutureWatcher_T.future()` returns a shared
alias of the watched future. Move-only payloads have no copying result accessor.
See the [consumption fixture](../../scripts/fixtures/future-take.bend).
`std::optional<T>` maps to Bend Maybe with checked empty/single-value
transport. The `shared.bend`, `optional.bend` and future examples show these APIs.

`IncubationFlag.new`, `load` and `store` control QML creation through
`QQmlIncubationController.incubateWhile(controller, flag, msecs)`. The call
runs a Qt event loop while it waits and retains its flag and engine until
completion. Setting the flag to false, for example from a forked Bend
computation, stops the wait. A duration of zero or minus one means no overall
deadline; positive durations limit the wait. Individual Qt creation steps are
not preempted. Changing the engine/controller association during a wait
returns ESTALE. See [incubation](../../examples/qt612/incubation.bend).

## Shader texture arrays and WebView

`QSGMaterialShader.updateSampledImage` exchanges a list whose length is exactly
`combinedImageSamplerCount(binding)`. Its handler must return that many
non-null textures. The adapter validates the whole reply before changing the
native array. New texture identities are retained by the shader, without
transferring ownership to Qt. These operations require a render handler
running on the main thread after `Render.useGuiThread`. Bend-created shader
override objects expose the protected subclass hooks through
`configureShaderFile`, `configureShaderFileViews` and `configureShader`. These
checked calls reject ordinary native shader instances. The QShader value form
requires the matching RHI ABI cohort. See the
[sampled-image fixture](../../scripts/fixtures/sampled-images.bend).

`QWebView.runJavaScriptWithHandler(~S, ~f, view, script, state)` copies its
QVariant result before calling the handler. The ordinary
`QWebView.runJavaScript__String` form uses Qt's empty result callback. QWebView
is a native window and stays on the main thread. The bundled runtime includes
its matching WebView backend plugin. Direct constructors check for missing or
unloadable plugins and return ENOTSUP. Backend initialization failures inside
a plugin and arbitrary QML construction still follow Qt's native behavior. See
the [WebView fixture](../../scripts/fixtures/webview-callbacks.bend).

The cleanup access and texture reply decisions have laws and proofs over their
input flags. Native event delivery, handler ordering, plugin loading and
resource destruction require integration tests.
