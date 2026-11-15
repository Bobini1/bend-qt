import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A distinct native representation was not checked")

def option() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("option", Qt.QCommandLineOption.valueArg()), True{})

def key() -> Qt.Property:
  Qt.Property.define("key", Qt.QCollatorSortKey.valueArg())

def pointer() -> Qt.Property:
  Qt.Property.define("pointer", Qt.QCommandLineOption.arg())

def ready() -> Qt.Signal:
  Qt.Signal.define("ready", [Qt.QCommandLineOption.valueArg(), Qt.QCollatorSortKey.valueArg()])

def Model() -> Qt.QtObject:
  Qt.QtObject.withSignals(Qt.QObject.define("NativeValueForms", [option(), key(), pointer()]), [ready()])

def description(value: Qt.QCommandLineOption, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QCommandLineOption.description(value)
    require(String.eq(text, expected), "A native owning value changed with its original wrapper")

def equal_keys(first: Qt.QCollatorSortKey, second: Qt.QCollatorSortKey) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    order: Qt.Int32 <- Qt.QCollatorSortKey.compare(first, second)
    require(U32.is_eq(Qt.Int32.word(order), 0), "Native sort key copy changed")

type Observer is Data:
  Observer{probe: Qt.QObject, expected: Qt.QCollatorSortKey}

def received(state: Observer, option: Qt.QCommandLineOption, key: Qt.QCollatorSortKey) -> Qt.Action(Unit):
  match state:
    case Observer{probe, expected}:
      do Qt.Action<Unit>:
        description(option, "first")
        equal_keys(key, expected)
        Qt.QObject.setObjectName(probe, "values")

def boxed(+option: Qt.QCommandLineOption, +key: Qt.QCollatorSortKey, +expected_key: Qt.QCollatorSortKey) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +box: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QCommandLineOption.valueArg(), option)
    +copy: Qt.QCommandLineOption <- Qt.QVariant.toValue(~Qt.QCommandLineOption.valueArg(), box)
    description(copy, "first")
    wrong: Result<&1, &1, U32 & String, Qt.QCommandLineOption> <- Qt.Action.attempt(Qt.QCommandLineOption,
      Qt.QVariant.toValue(~Qt.QCommandLineOption.arg(), box))
    expected(Qt.QCommandLineOption, wrong, 22)
    +key_box: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QCollatorSortKey.valueArg(), key)
    copy_key: Qt.QCollatorSortKey <- Qt.QVariant.toValue(~Qt.QCollatorSortKey.valueArg(), key_box)
    equal_keys(copy_key, expected_key)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +second: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +self: Qt.QObject = Qt.QtObject.as_QObject(~Model(), first)
    +target: Qt.QObject = Qt.QtObject.as_QObject(~Model(), second)
    +probe: Qt.QObject <- Qt.QObject.new()
    +collator: Qt.QCollator <- Qt.QCollator.new()
    +expected_key: Qt.QCollatorSortKey <- Qt.QCollator.sortKey(collator, "Bend")
    +source_key: Qt.QCollatorSortKey <- Qt.QCollator.sortKey(collator, "Bend")
    +source: Qt.QCommandLineOption <- Qt.QCommandLineOption.new__String("mode")
    Qt.QCommandLineOption.setDescription(source, "first")
    Qt.Property.store(~option(), self, source)
    Qt.Property.store(~option(), target, source)
    Qt.Property.store(~key(), self, source_key)
    Qt.Property.store(~pointer(), self, source)
    actual_pointer: Qt.QCommandLineOption <- Qt.Property.get(~pointer(), self)
    require(U32.is_eq(Qt.QCommandLineOption.word(actual_pointer), Qt.QCommandLineOption.word(source)), "Default arg stopped representing the native pointer")
    connection: Qt.Connection <- Qt.Signal.connectWith(~ready(), ~Observer, ~received, self,
      Qt.Qt.ConnectionType.QueuedConnection(), Observer{probe, expected_key})
    Qt.Signal.emit(~ready(), self, source, source_key)
    Qt.QCommandLineOption.setDescription(source, "changed")
    Qt.QCommandLineOption.destroy(source)
    Qt.QCollatorSortKey.destroy(source_key)
    Qt.QCoreApplication.processEvents()
    text: String <- Qt.QObject.objectName(probe)
    require(String.eq(text, "values"), "Owning native signal arguments did not survive source deletion")
    +value: Qt.QCommandLineOption <- Qt.Property.get(~option(), self)
    description(value, "first")
    +value_key: Qt.QCollatorSortKey <- Qt.Property.get(~key(), self)
    equal_keys(value_key, expected_key)
    Qt.scoped(Unit, boxed(value, value_key, expected_key))
    stale: Result<&1, &1, U32 & String, Qt.QCommandLineOption> <- Qt.Action.attempt(Qt.QCommandLineOption, Qt.Property.get(~pointer(), self))
    expected(Qt.QCommandLineOption, stale, 116)
    Qt.Property.bind(~option(), ~option(), target, self)
    +next: Qt.QCommandLineOption <- Qt.QCommandLineOption.new__String("mode")
    Qt.QCommandLineOption.setDescription(next, "next")
    Qt.Property.set(~option(), self, next)
    bound: Qt.QCommandLineOption <- Qt.Property.get(~option(), target)
    description(bound, "next")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Native value-form descriptors leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_VALUE_FORMS_OK default_pointer=1 owning_value=1 property=1 signal=1 variant=1 binding=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
