import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Dynamic property error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An invalid dynamic property operation succeeded")

def put(+self: Qt.QObject, name: String, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Bool <- Qt.QObject.setProperty(self, name, value)
    require(Bool.not(result), "Dynamic setProperty changed Qt's false return convention")

def number(+self: Qt.QObject, name: String, wanted: U32) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QObject.property(self, name), value => do Qt.Action<Unit>:
    actual: Qt.Int32 <- Qt.QVariant.toValue(~Qt.int32(), value)
    require(U32.is_eq(Qt.Int32.word(actual), wanted), "Dynamic property value changed")
  )

def remove(+self: Qt.QObject, name: String) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.new(), value => put(self, name, value))

def repeat(count: Nat, +self: Qt.QObject) -> Qt.Action(Unit):
  match count:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{7}), value => put(self, "repeat", value))
        remove(self, "repeat")
        repeat(rest, self)

def simple() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject <- Qt.QObject.new()
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{1}), value => put(self, "counter", value))
    number(self, "counter", 1)
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{2}), value => do Qt.Action<Unit>:
      result: Bool <- Qt.CallbackProbe.dynamicSet(self, "counter", value)
      require(Bool.not(result), "Raw native dynamic setProperty returned true")
    )
    number(self, "counter", 2)
    remove(self, "counter")
    repeat(32n, self)
    Qt.QVariant.with(Unit, Qt.QObject.property(self, "repeat"), value => do Qt.Action<Unit>:
      valid: Bool <- Qt.QVariant.isValid(value)
      require(Bool.not(valid), "Removing a dynamic property kept its cached value")
    )
    leases: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(leases, 0), "Repeated dynamic property removal leaked origins")

def named(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, "objectName"), "Dynamic metadata changed")
    case None{}: Qt.Action.fail(Unit, 1, "Dynamic metadata name disappeared")

def from_meta(+meta: Qt.QMetaObject) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "objectName")
    Qt.QMetaObject.property(meta, index)

def descriptor(+map: Qt.QQmlPropertyMap) -> Qt.Action(Qt.QMetaProperty):
  Qt.QMetaObject.with(Qt.QMetaProperty, Qt.QQmlPropertyMap.metaObject(map), meta => from_meta(meta))

def insert_value(+self: Qt.QObject, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    put(self, "descriptor", value)
    result: Bool <- Qt.CallbackProbe.dynamicSet(self, "descriptor", value)
    require(Bool.not(result), "Raw native metadata setter returned true")

def insert_metadata(+self: Qt.QObject, +map: Qt.QQmlPropertyMap) -> Qt.Action(Unit):
  Qt.QMetaProperty.with(Unit, descriptor(map), property => Qt.QVariant.with(Unit,
    Qt.QVariant.fromValue(~Qt.QMetaProperty.arg(), property), value => insert_value(self, value)))

def metadata() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject <- Qt.QObject.new()
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    Qt.scoped(Unit, insert_metadata(self, map))
    +boxed: Qt.QVariant <- Qt.QObject.property(self, "descriptor")
    +property: Qt.QMetaProperty <- Qt.QVariant.toValue(~Qt.QMetaProperty.arg(), boxed)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(property)
    named(name)
    remove(self, "descriptor")
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQmlPropertyMap.destroy(map))
    expected(Unit, held, 16)
    Qt.QMetaProperty.destroy(property)
    Qt.QVariant.destroy(boxed)
    Qt.QQmlPropertyMap.destroy(map)
    +next: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    Qt.scoped(Unit, insert_metadata(self, next))
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{9}), value => Qt.QQmlPropertyMap.insert__String_QVariant(next, "epochChanged", value))
    stale: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QObject.property(self, "descriptor"))
    expected(Qt.QVariant, stale, 116)
    remove(self, "descriptor")
    Qt.QQmlPropertyMap.destroy(next)

def pointers() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject <- Qt.QObject.new()
    +peer: Qt.QObject <- Qt.QObject.new()
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.qobject(), peer), value => put(self, "peer", value))
    Qt.QObject.destroy(peer)
    stale: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QObject.property(self, "peer"))
    expected(Qt.QVariant, stale, 116)
    remove(self, "peer")
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.qobject(), self), value => put(self, "self", value))
    Qt.QObject.destroy(self)

def reenter_value(+self: Qt.QObject, armed: Bool) -> Qt.Action(Bool):
  match armed:
    case False{}: Qt.Action.pure(Bool, False{})
    case True{}:
      do Qt.Action<Bool>:
        Qt.QObject.setObjectName(self, "observed")
        number(self, "counter", 1)
        Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{2}), value => do Qt.Action<Unit>:
          result: Bool <- Qt.CallbackProbe.dynamicSet(self, "counter", value)
          require(Bool.not(result), "Reentrant native setter returned true")
        )
        return False{}

def reenter_kind(+self: Qt.QObject, dynamic: Bool) -> Qt.Action(Bool):
  match dynamic:
    case False{}: Qt.Action.pure(Bool, False{})
    case True{}:
      do Qt.Action<Bool>:
        phase: String <- Qt.QObject.objectName(self)
        reenter_value(self, String.eq(phase, "armed"))

def reenter(self: Qt.QObject, event: Qt.QEvent) -> Qt.Action(Bool):
  do Qt.Action<Bool>:
    kind: Qt.QEvent.Type <- Qt.QEvent.type(event)
    reenter_kind(self, U32.is_eq(Qt.QEvent.Type.word(kind), Qt.QEvent.Type.word(Qt.QEvent.Type.DynamicPropertyChange())))

def fail_event(state: Unit, event: Qt.QEvent) -> Qt.Action(Bool):
  Qt.Action.fail(Bool, 73, "Dynamic property event failure")

def reentrant() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject <- Qt.QObject.newOverride()
    Qt.QObject.setObjectName(self, "armed")
    Qt.QObject.Virtual.event.handle(~Qt.QObject, ~reenter, self, self)
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{1}), value => put(self, "counter", value))
    number(self, "counter", 2)
    Qt.QObject.Virtual.event.handle(~Unit, ~fail_event, self, Unit{})
    Qt.QVariant.with(Unit, Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{3}), value => do Qt.Action<Unit>:
      failed: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QObject.setProperty(self, "counter", value))
      expected(Bool, failed, 73)
    )
    number(self, "counter", 3)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, simple())
    Qt.scoped(Unit, metadata())
    Qt.scoped(Unit, pointers())
    Qt.scoped(Unit, reentrant())
    objects: U32 <- Qt.Runtime.liveObjects()
    leases: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(leases, 0), "Dynamic property origins leaked")
    Qt.Action.lift(Unit, IO.print("QT612_DYNAMIC_PROPERTIES_OK native=1 false_return=1 raw_mutation=1 metadata=1 outgoing_copy=1 epoch=1 borrowed=1 self_cycle=0 reentrant=1 failure=1 removal=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
