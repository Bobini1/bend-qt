# Qt convenience adapters

These adapters cover public Qt operations whose C++ templates or raw function
pointers do not have a direct Bend signature. They use the same native runtime
and `Action` error handling as ordinary generated methods.

## Child lookup

Every selected QObject class supplies typed child lookup:

```python
Qt.QPushButton.findIn(root, "saveButton")
Qt.QPushButton.findAllIn(root, "")
Qt.QPushButton.findAllMatchingIn(root, pattern)
```

The `With` variants take `Qt.Flags_Qt__FindChildOption` as the last argument.
For example, `QPushButton.findAllInWith(root, "", Qt.Flags_Qt__FindChildOption{0})`
searches direct children only. The ordinary variants use Qt's recursive default.
An empty name matches every name. The requested class still filters results.
`findIn` follows Qt's preference for the nearest matching child; returned handles
borrow the objects and preserve their existing Qt ownership.

## Application cleanup callbacks

`PostRoutine.add(~State, ~cleanup, state)` registers `cleanup : State -> Action(Unit)`
with Qt's actual `qAddPostRoutine` list. Qt calls it from the application
destructor, after Bend's main computation returns, in reverse registration order.

```python
def cleanup(message: String) -> Qt.Action(Unit):
  Qt.Action.lift(Unit, IO.print(message))

def register() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    registration: Qt.PostRoutine <- Qt.PostRoutine.add(~String, ~cleanup, "Qt is closing")
    return Unit{}
```

The registration has application lifetime. Ending the registering Action scope
preserves it. `PostRoutine.remove(registration)` cancels it early;
`PostRoutine.with` cancels when its body ends, including a failed body.
Removing an expired registration returns ESTALE; scoped cleanup accepts ESTALE.
A callback may register another callback, following Qt's native cleanup ordering.

Cleanup must finish synchronously. Waiting before its acknowledgement returns
EWOULDBLOCK; there is no running Qt event loop during application destruction.
Qt objects already released by earlier scopes remain expired. A cleanup failure
does not skip the remaining callbacks. It supplies the process exit status when
main otherwise succeeds. As with Qt applications in C++, `IO.exit` terminates the
process without unwinding this application destructor.

The native adapter relies on the pinned Bend 2.0.40 runtime retaining its heap
until process exit. The C entry point tears Qt down before exit handlers and
flushes output from cleanup callbacks. This version-specific behavior is covered
by native integration tests and is outside the pure Action proofs.

## JavaScript singletons

Use `Qml.registerScriptSingleton` when QML should receive a JavaScript object
instead of a QObject with a declared schema:

```python
def makeSettings(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QJSValue):
  do Qt.Action<Qt.QJSValue>:
    dark: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.bool(), True{})
    settings: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.variantMap(), [Qt.PairValue{"darkMode", dark}])
    Qt.QJSEngine.toScriptValue(Qt.QQmlEngine.as_QJSEngine(engine), settings)

def register() -> Qt.Action(Qt.Qml.RegistrationHandle):
  Qt.Qml.registerScriptSingleton(~Unit, ~makeSettings, "Example.Settings", 1, 0, "Settings", Unit{})
```

QML can then use `import Example.Settings 1.0` and `Settings.darkMode`. Qt calls
the factory once per engine. Use the supplied engine to create managed values.
Returning a value from another engine fails with EXDEV. Factory failures retain
their original Action error.

The returned `Qml.RegistrationHandle` controls the registration. Keep it alive until the
registration is no longer needed. An engine that uses the singleton retains the
registration; destroying it while that engine is alive returns EBUSY. After
the engines and returned QJSValue handles are released, destroying the
registration unregisters the type and releases its factory state.

`QQmlEngine.singletonInstance(~QJSValue.arg(), engine, uri, name)` retrieves the
same value from Bend. Its handle retains the engine. External data passed
through `QJSEngine.toScriptValue` keeps its normal origin leases until engine
destruction. A script singleton does not declare QObject properties or notify
signals; use `registerSingletonFactory` with an `ObjectType` schema for those.

## QObject interface helpers

The native helper bases support the Qt interfaces that require a QObject and
an interface together. For example, create `QPyTextObject.newOverride()` and
use its pure `as_QTextObjectInterface` cast to install the normal
`QTextObjectInterface.Virtual.intrinsicSize.handle` and `drawObject.handle`
handlers. Pass `QPyTextObject.as_QObject(value)` to the document layout's
`registerHandler`. Qt discovers the interface through real `Q_INTERFACES`
metadata.

The same generated constructors, virtual handlers and `ObjectType.define`
schemas are available for `QPyQmlParserStatus`, `QPyQmlPropertyValueSource`
and the four `QPyDesigner*Extension` QObject/interface bases. Install parser
handlers in a QML constructor handler so `classBegin` can run before the
component's properties are assigned. The public fixture
`scripts/fixtures/qobject-interface-helpers.bend` shows this lifecycle.

## Touch event sequences

Use Qt's native touch synthesis inside an Action scope:

```python
def tap(window: Qt.QWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    device: Qt.QPointingDevice <- Qt.QTest.createTouchDevice()
    +point: Qt.QPoint <- Qt.QPoint.new__Int32_Int32(Qt.Int32{20}, Qt.Int32{30})
    +sequence: Qt.QTest.QTouchEventSequence <- Qt.QTest.touchEvent(window, device)
    Qt.QTest.QTouchEventSequence.press(sequence, Qt.Int32{0}, point)
    accepted: Bool <- Qt.QTest.QTouchEventSequence.commit(sequence)
    Qt.QTest.QTouchEventSequence.release(sequence, Qt.Int32{0}, point)
    accepted: Bool <- Qt.QTest.QTouchEventSequence.commit(sequence)
```

Closing the scope commits any pending events and cleans up the sequence.
`touchWidget` targets a QWidget. The `pressInWindow`, `pressInWidget`, move
and release variants select a coordinate space explicitly. `stationary`
preserves a previous touch point. `commitWith(sequence, False{})` skips
event processing after dispatch. The `WithAutoCommit` factories accept an
explicit cleanup policy. The sequence retains its target and device views;
Qt owns devices created by `createTouchDevice`. `destroy` closes a sequence
explicitly, while `releaseHandle` is its scoped handle cleanup operation.
