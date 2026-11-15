import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected native pointer rejection")

def device() -> Qt.Property:
  Qt.Property.define("device", Qt.QPaintDevice.arg())

def painter() -> Qt.Property:
  Qt.Property.define("painter", Qt.QPainter.arg())

def event() -> Qt.Property:
  Qt.Property.define("event", Qt.QEvent.arg())

def nativePointers() -> Qt.Signal:
  Qt.Signal.define("nativePointers", [Qt.QPainter.arg(), Qt.QPaintDevice.arg(), Qt.QSGNode.arg()])

def eventReady() -> Qt.Signal:
  Qt.Signal.define("eventReady", [Qt.QEvent.arg()])

def Holder() -> Qt.QtObject:
  Qt.QtObject.withSignals(Qt.QObject.define("NativePointerHolder", [device(), painter(), event()]), [nativePointers(), eventReady()])

type Observer is Data:
  Observer{probe: Qt.QObject, painter: U32, device: U32}

def identity(actual: U32, expected: U32) -> Qt.Action(Unit):
  match expected:
    case 0: Qt.Action.pure(Unit, Unit{})
    case expected: require(U32.is_eq(actual, expected), "Native pointer alias changed identity")

def received(state: Observer, painter: Qt.QPainter, device: Qt.QPaintDevice, node: Qt.QSGNode) -> Qt.Action(Unit):
  match state:
    case Observer{probe, expected_painter, expected_device}:
      do Qt.Action<Unit>:
        +paint: Qt.QPainter = painter
        +target: Qt.QPaintDevice = device
        identity(Qt.QPainter.word(paint), expected_painter)
        identity(Qt.QPaintDevice.word(target), expected_device)
        require(U32.is_eq(Qt.QSGNode.word(node), 0), "Nullable native pointer changed")
        active: Bool <- Qt.QPainter.isActive(paint)
        drawing: Bool <- Qt.QPaintDevice.paintingActive(target)
        require(Bool.not(active || drawing), "Inactive native pointer arguments changed")
        Qt.QObject.setObjectName(probe, "pointers")

def forbidden(state: Unit, painter: Qt.QPainter, device: Qt.QPaintDevice, node: Qt.QSGNode) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 99, "A stale queued native pointer reached Bend")

def immediate(+self: Qt.QObject, +paint: Qt.QPainter, +target: Qt.QPaintDevice, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connect(~nativePointers(), ~Observer, ~received, self,
      Observer{probe, Qt.QPainter.word(paint), Qt.QPaintDevice.word(target)})
    Qt.Signal.emit(~nativePointers(), self, paint, target, Qt.QSGNode{0})
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "pointers"), "Native pointer signal handler did not execute")

def worker_direct(+self: Qt.QObject, +paint: Qt.QPainter, +target: Qt.QPaintDevice, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connectWith(~nativePointers(), ~Observer, ~received, self,
      Qt.Qt.ConnectionType.DirectConnection(), Observer{probe, Qt.QPainter.word(paint), Qt.QPaintDevice.word(target)})
    Qt.CallbackProbe.nativePointerFromWorker(self, paint, target, True{})
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "pointers"), "Worker direct pointer signal missed its Bend handler")

def worker_queued(+self: Qt.QObject, +target: Qt.QPaintDevice) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +paint: Qt.QPainter <- Qt.QPainter.new()
    connection: Qt.Connection <- Qt.Signal.connect(~nativePointers(), ~Unit, ~forbidden, self, Unit{})
    Qt.CallbackProbe.nativePointerFromWorker(self, paint, target, False{})
    Qt.QPainter.destroy(paint)
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCoreApplication.processEvents())
    expected(Unit, failed, 116)

def unregistered(+self: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connect(~nativePointers(), ~Observer, ~received, self, Observer{probe, 0, 0})
    Qt.CallbackProbe.nativePointerUnregistered(self, False{})
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "pointers"), "Synchronous unregistered native pointers were not borrowed")

def unknown_queued(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connectWith(~nativePointers(), ~Unit, ~forbidden, self,
      Qt.Qt.ConnectionType.QueuedConnection(), Unit{})
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.CallbackProbe.nativePointerUnregistered(self, True{}))
    expected(Unit, failed, 116)

def property_cases(+self: Qt.QObject, +paint: Qt.QPainter, +target: Qt.QPaintDevice) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~painter(), self, paint)
    Qt.Property.set(~device(), self, target)
    actual_painter: Qt.QPainter <- Qt.Property.get(~painter(), self)
    actual_device: Qt.QPaintDevice <- Qt.Property.get(~device(), self)
    require(U32.is_eq(Qt.QPainter.word(actual_painter), Qt.QPainter.word(paint)) &&
      U32.is_eq(Qt.QPaintDevice.word(actual_device), Qt.QPaintDevice.word(target)), "Native pointer property lost identity")
    Qt.Property.set(~painter(), self, Qt.QPainter{0})
    actual_painter: Qt.QPainter <- Qt.Property.get(~painter(), self)
    require(U32.is_eq(Qt.QPainter.word(actual_painter), 0), "Null native pointer property changed")
    +temporary: Qt.QPainter <- Qt.QPainter.new()
    Qt.Property.set(~painter(), self, temporary)
    Qt.QPainter.destroy(temporary)
    stale: Result<&1, &1, U32 & String, Qt.QPainter> <- Qt.Action.attempt(Qt.QPainter, Qt.Property.get(~painter(), self))
    expected(Qt.QPainter, stale, 116)
    +event_value: Qt.QEvent <- Qt.QEvent.new(Qt.QEvent.Type.User())
    Qt.Property.set(~event(), self, event_value)
    Qt.CallbackProbe.nativePointerDeleteEvent(event_value)
    dead: Result<&1, &1, U32 & String, Qt.QEvent> <- Qt.Action.attempt(Qt.QEvent, Qt.Property.get(~event(), self))
    expected(Qt.QEvent, dead, 116)
    Qt.QCoreApplication.processEvents()

def inspect_boxed_list(values: List<&2, Qt.QVariant>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}:
      do Qt.Action<Unit>:
        pointer: Qt.QPaintDevice <- Qt.QVariant.toValue(~Qt.QPaintDevice.arg(), value)
        active: Bool <- Qt.QPaintDevice.paintingActive(pointer)
        require(Bool.not(active), "Copied boxed native pointer changed")
    case _: Qt.Action.fail(Unit, 1, "Boxed native pointer container changed")

def boxed_list(value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    values: List<&2, Qt.QVariant> <- Qt.QVariant.toValue(~Qt.variantList(), value)
    inspect_boxed_list(values)

def event_forbidden(state: Unit, value: Qt.QEvent) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 99, "A queued pointer aliased a new object at the old address")

def address_reuse(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +old: Qt.QEvent <- Qt.CallbackProbe.nativeFixedEvent()
    old_word: U32 = Qt.QEvent.word(old)
    connection: Qt.Connection <- Qt.Signal.connectWith(~eventReady(), ~Unit, ~event_forbidden, self, Qt.Qt.ConnectionType.QueuedConnection(), Unit{})
    Qt.Signal.emit(~eventReady(), self, old)
    Qt.QEvent.destroy(old)
    +current: Qt.QEvent <- Qt.CallbackProbe.nativeFixedEvent()
    require(U32.is_ne(old_word, Qt.QEvent.word(current)), "Reused address retained an old token generation")
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCoreApplication.processEvents())
    expected(Unit, failed, 116)
    value: Qt.QEvent.Type <- Qt.QEvent.type(current)
    require(U32.is_eq(Qt.QEvent.Type.word(value), 1000), "The replacement native event became stale")

def boxed() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +image: Qt.QImage <- Qt.QImage.new()
    +target: Qt.QPaintDevice <- Qt.QImage.as_QPaintDevice(image)
    +value: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QPaintDevice.arg(), target)
    +container: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.variantList(), [value])
    +copy: Qt.QVariant <- Qt.QVariant.copy(container)
    Qt.QImage.release(image)
    Qt.QVariant.clear(value)
    Qt.QVariant.clear(container)
    Qt.scoped(Unit, boxed_list(copy))
    Qt.QVariant.clear(copy)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    holder: Qt.QtObject.Instance(Holder()) <- Qt.QtObject.new(~Holder())
    +self: Qt.QObject = Qt.QtObject.as_QObject(~Holder(), holder)
    +probe: Qt.QObject <- Qt.QObject.new()
    +paint: Qt.QPainter <- Qt.QPainter.new()
    +image: Qt.QImage <- Qt.QImage.new()
    +image_device: Qt.QPaintDevice <- Qt.QImage.as_QPaintDevice(image)
    Qt.scoped(Unit, property_cases(self, paint, image_device))
    Qt.scoped(Unit, immediate(self, paint, image_device, probe))
    +button: Qt.QPushButton <- Qt.QPushButton.new()
    +widget_device: Qt.QPaintDevice = Qt.QPushButton.as_QPaintDevice(button)
    Qt.scoped(Unit, immediate(self, paint, widget_device, probe))
    Qt.scoped(Unit, worker_direct(self, paint, image_device, probe))
    Qt.scoped(Unit, worker_queued(self, image_device))
    Qt.scoped(Unit, unregistered(self, probe))
    Qt.scoped(Unit, unknown_queued(self))
    Qt.scoped(Unit, address_reuse(self))
    Qt.scoped(Unit, boxed())

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    Qt.QCoreApplication.processEvents()
    observations: U32 <- Qt.CallbackProbe.nativePointerObservationCount()
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(observations, 0) && U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Native pointer identities or handlers leaked")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_POINTER_ARGUMENTS_OK values=1 aliases=1 properties=1 worker=1 stale=1 temporary=1 boxed=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
