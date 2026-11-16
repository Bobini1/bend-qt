import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected expired metadata rejection")

def metadataReady() -> Qt.Signal:
  Qt.Signal.define("metadataReady", [Qt.QMetaProperty.arg()])

def Host() -> Qt.ObjectType:
  Qt.ObjectType.withSignals(Qt.QObject.define("MetadataSignalArguments", [Qt.Property.define("payload", Qt.string())]), [metadataReady()])

def named(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, "payload"), "A metadata signal changed its property")
    case None{}: Qt.Action.fail(Unit, 1, "A metadata signal lost its property name")

def received(probe: Qt.QObject, value: Qt.QMetaProperty) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(value)
    named(name)
    Qt.QObject.setObjectName(probe, "metadata")

def forbidden(state: Unit, value: Qt.QMetaProperty) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 99, "Expired metadata reached its signal handler")

def property(+map: Qt.QQmlPropertyMap) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    +value: Qt.QVariant <- Qt.QVariant.fromString("Bend")
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "payload", value)
    +meta: Qt.QMetaObject <- Qt.QQmlPropertyMap.metaObject(map)
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "payload")
    Qt.QMetaObject.property(meta, index)

def delivered(probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "metadata"), "Queued metadata signal did not reach Bend")

def released_source(+self: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    +source: Qt.QMetaProperty <- property(map)
    connection: Qt.Connection <- Qt.Signal.connectWith(~metadataReady(), ~Qt.QObject, ~received,
      self, Qt.Qt.ConnectionType.QueuedConnection(), probe)
    Qt.Signal.emit(~metadataReady(), self, source)
    Qt.QMetaProperty.release(source)
    Qt.QQmlPropertyMap.release(map)
    Qt.QCoreApplication.processEvents()
    delivered(probe)

def invalidated_source(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    +source: Qt.QMetaProperty <- property(map)
    connection: Qt.Connection <- Qt.Signal.connectWith(~metadataReady(), ~Unit, ~forbidden,
      self, Qt.Qt.ConnectionType.QueuedConnection(), Unit{})
    Qt.Signal.emit(~metadataReady(), self, source)
    +value: Qt.QVariant <- Qt.QVariant.fromString("changed")
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "afterCapture", value)
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCoreApplication.processEvents())
    expected(failed)

def native_worker(+self: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    +source: Qt.QMetaProperty <- property(map)
    connection: Qt.Connection <- Qt.Signal.connect(~metadataReady(), ~Qt.QObject, ~received, self, probe)
    Qt.QObject.setObjectName(probe, "waiting")
    Qt.CallbackProbe.metadataSignalFromWorker(self, source)
    Qt.QMetaProperty.release(source)
    Qt.QCoreApplication.processEvents()
    delivered(probe)

def unknown_worker(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connect(~metadataReady(), ~Unit, ~forbidden, self, Unit{})
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.CallbackProbe.unknownMetadataSignalFromWorker(self))
    expected(failed)

def immutable_worker(+self: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connect(~metadataReady(), ~Qt.QObject, ~received, self, probe)
    Qt.QObject.setObjectName(probe, "waiting")
    Qt.CallbackProbe.immutableMetadataSignalFromWorker(self)
    Qt.QCoreApplication.processEvents()
    delivered(probe)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    host: Qt.ObjectType.Instance(Host()) <- Qt.ObjectType.new(~Host())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Host(), host)
    +probe: Qt.QObject <- Qt.QObject.new()
    Qt.scoped(Unit, released_source(self, probe))
    Qt.scoped(Unit, invalidated_source(self))
    Qt.scoped(Unit, native_worker(self, probe))
    Qt.scoped(Unit, unknown_worker(self))
    Qt.scoped(Unit, immutable_worker(self, probe))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    Qt.QCoreApplication.processEvents()
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Metadata signal leases leaked")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_SIGNAL_ARGUMENTS_OK source_release=1 epoch=1 native_worker=1 unknown=1 immutable=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
