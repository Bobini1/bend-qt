# Maintainer fixture supplies an over-aligned registered gadget in its payload.
import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def read(property: Qt.QMetaProperty, value: Qt.MetaStorage) -> Qt.Action(String):
  Qt.QVariant.with(String, Qt.QMetaProperty.readOnGadget(property, value), Qt.QVariant.toString)

def write(property: Qt.QMetaProperty, value: Qt.MetaStorage, text: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ok: Bool <- Qt.QMetaProperty.writeOnGadget(property, value, text)
    require(ok, "Gadget property write failed")

def property(+descriptor: Qt.QMetaProperty, +value: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    initial: String <- read(descriptor, value)
    require(String.eq(initial, "initial"), "Gadget default construction failed")
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("Bend gadget 🎵"), text => write(descriptor, value, text))
    changed: String <- read(descriptor, value)
    require(String.eq(changed, "Bend gadget 🎵"), "Gadget Unicode value changed")
    reset: Bool <- Qt.QMetaProperty.resetOnGadget(descriptor, value)
    require(reset, "Gadget property reset failed")
    restored: String <- read(descriptor, value)
    require(String.eq(restored, "reset"), "Gadget reset did not run native code")

def failed(-A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(code, actual), "Wrong typed argument error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid typed generic argument succeeded")

def invoke(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, input: Qt.QGenericArgument, output: Qt.QGenericReturnArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    called: Bool <- Qt.QMetaMethod.invokeOnGadget__MetaStorage_QGenericReturnArgument_QGenericArgument(method, gadget, output, input)
    require(called, "Typed gadget invocation failed")

def output_argument(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, +input: Qt.QGenericArgument, +output: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGenericReturnArgument.with(Unit, Qt.QGenericReturnArgument.fromStorage(output), result => invoke(method, gadget, input, result))
    text: String <- Qt.QVariant.with(String, Qt.MetaStorage.toVariant(output), Qt.QVariant.toString)
    require(String.eq(text, "reset 🎵"), "Meta-call returned the wrong typed value")

def output_variant(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, +input: Qt.QGenericArgument, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(value), output => output_argument(method, gadget, input, output))

def invoke_input(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, +input: Qt.QGenericArgument) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString(""), value => output_variant(method, gadget, input, value))

def input_storage(+storage: Qt.MetaStorage) -> Qt.Action(Qt.QGenericArgument):
  do Qt.Action<Qt.QGenericArgument>:
    wrong: Result<&1, &1, U32 & String, Qt.QGenericArgument> <- Qt.Action.attempt(Qt.QGenericArgument, Qt.QGenericArgument.new__String_MetaStorage("int", storage))
    failed(Qt.QGenericArgument, 22, wrong)
    Qt.QGenericArgument.fromStorage(storage)

def input_variant(value: Qt.QVariant) -> Qt.Action(Qt.QGenericArgument):
  Qt.MetaStorage.with(Qt.QGenericArgument, Qt.MetaStorage.fromVariant(value), storage => input_storage(storage))

def copied_input(value: Qt.QGenericArgument) -> Qt.Action(Qt.QGenericArgument):
  Qt.QGenericArgument.new__QGenericArgument(value)

def make_input() -> Qt.Action(Qt.QGenericArgument):
  Qt.QGenericArgument.with(Qt.QGenericArgument,
    Qt.QVariant.with(Qt.QGenericArgument, Qt.QVariant.fromString(" 🎵"), input_variant), copied_input)

def invoke_method(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QGenericArgument.with(Unit, make_input(), input => invoke_input(method, gadget, input))

def mutable_call(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, argument: Qt.QGenericArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    called: Bool <- Qt.QMetaMethod.invokeOnGadget__MetaStorage_QGenericArgument(method, gadget, argument)
    require(called, "Mutable reference gadget invocation failed")

def mutable_storage(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, +storage: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGenericArgument.with(Unit, Qt.QGenericArgument.new__String_MetaStorage("QString&", storage), argument => mutable_call(method, gadget, argument))
    text: String <- Qt.QVariant.with(String, Qt.MetaStorage.toVariant(storage), Qt.QVariant.toString)
    require(String.eq(text, "original changed"), "Meta-call lost its mutable reference write")

def mutable_variant(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(value), storage => mutable_storage(method, gadget, storage))

def mutable_method(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("original"), value => mutable_variant(method, gadget, value))

def throwing_call(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, argument: Qt.QGenericArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    caught: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMetaMethod.invokeOnGadget__MetaStorage_QGenericArgument(method, gadget, argument))
    failed(Bool, 14, caught)

def throwing_storage(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, +storage: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGenericArgument.with(Unit, Qt.QGenericArgument.new__String_MetaStorage("QString&", storage), argument => throwing_call(method, gadget, argument))
    stale: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.MetaStorage.toVariant(storage))
    failed(Qt.QVariant, 116, stale)

def throwing_variant(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(value), storage => throwing_storage(method, gadget, storage))

def throwing_method(+method: Qt.QMetaMethod, +gadget: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("original"), value => throwing_variant(method, gadget, value))

def properties(+metadata: Qt.QMetaObject, +value: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(metadata, "text")
    Qt.QMetaProperty.with(Unit, Qt.QMetaObject.property(metadata, index), descriptor => property(descriptor, value))
    method_index: Qt.Int32 <- Qt.QMetaObject.indexOfMethod(metadata, "echo(QString)")
    Qt.QMetaMethod.with(Unit, Qt.QMetaObject.method(metadata, method_index), method => invoke_method(method, value))
    mutable_index: Qt.Int32 <- Qt.QMetaObject.indexOfMethod(metadata, "mutate(QString&)")
    Qt.QMetaMethod.with(Unit, Qt.QMetaObject.method(metadata, mutable_index), method => mutable_method(method, value))
    throwing_index: Qt.Int32 <- Qt.QMetaObject.indexOfMethod(metadata, "throwing(QString&)")
    Qt.QMetaMethod.with(Unit, Qt.QMetaObject.method(metadata, throwing_index), method => throwing_method(method, value))

def named_metadata(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, "BendQtTestGadget"), "Member metadata origin changed")
    case None{}: Qt.Action.fail(Unit, 1, "Member metadata name is missing")

def member_metadata(metadata: Qt.QMetaObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QMetaObject.className(metadata)
    named_metadata(name)

def storage(+meta: Qt.QMetaType, value: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    id: Qt.Int32 <- Qt.QMetaType.rawId(meta)
    Qt.QMetaObject.with(Unit, Qt.QMetaType.metaObjectForType(id), metadata => properties(metadata, value))
    Qt.QMetaObject.with(Unit, Qt.QMetaType.metaObject(meta), member_metadata)

def gadget(+meta: Qt.QMetaType) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +alignment: Qt.Int64 <- Qt.QMetaType.alignOf(meta)
    require(U32.is_eq(Qt.Int64.lo(alignment), 64) && U32.is_eq(Qt.Int64.hi(alignment), 0), "Fixture lost its over-alignment")
    Qt.MetaStorage.with(Unit, Qt.QMetaType.create(meta), value => storage(meta, value))

def lookup(name: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QMetaType.with(Unit, Qt.QMetaType.fromName(name), meta => gadget(meta))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("BendQtTestGadget"), lookup)
    live: U32 <- Qt.Fixture.liveGadgets()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0) && U32.is_eq(objects, 0), "Gadget cleanup leaked constructed values")
    Qt.Action.lift(Unit, IO.print("QT612_METATYPE_GADGET_OK alignment64=1 default_construct=1 read=1 write=1 reset=1 invoke=1 typed_storage=1 retained_copy=1 destructor=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
