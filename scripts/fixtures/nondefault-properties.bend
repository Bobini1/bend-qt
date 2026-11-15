import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def option() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("option", Qt.QFontInfo.arg()), True{})

def accessor() -> Qt.Property:
  Qt.Property.readOnly("accessor", Qt.QFontInfo.arg())

def optionResult() -> Qt.Method:
  Qt.Method.define("optionResult", [], Qt.QFontInfo.arg())

def evaluations() -> Qt.Property:
  Qt.Property.define("evaluations", Qt.int32())

def Model() -> Qt.QtObject:
  Qt.QtObject.withMethods(Qt.QObject.define("NondefaultPropertyModel", [option(), accessor(), evaluations()]), [optionResult()])

type ComputedState is Data:
  ComputedState{source: Qt.QObject, target: Qt.QObject}

def computed_value(source: Qt.QObject, +target: Qt.QObject) -> Qt.Action(Qt.QFontInfo):
  do Qt.Action<Qt.QFontInfo>:
    previous: Qt.Int32 <- Qt.Property.get(~evaluations(), target)
    Qt.Property.set(~evaluations(), target, Qt.Int32{U32.add(Qt.Int32.word(previous), 1)})
    Qt.Property.get(~option(), source)

def computed(state: ComputedState) -> Qt.Action(Qt.QFontInfo):
  match state:
    case ComputedState{source, +target}: computed_value(source, target)

def read_option(value: Qt.QFontInfo) -> Qt.Action(Qt.QFontInfo):
  Qt.Action.pure(Qt.QFontInfo, value)

def expected_empty(result: Result<&1, &1, U32 & String, Qt.QFontInfo>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 61), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An uninitialized nondefault property unexpectedly had a value")

def expect_option(+value: Qt.QFontInfo, expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    size: Qt.Int32 <- Qt.QFontInfo.pixelSize(value)
    require(U32.is_eq(Qt.Int32.word(size), expected), "A nondefault font-info value changed its native data")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +second: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +source: Qt.QObject = Qt.QtObject.as_QObject(~Model(), first)
    +target: Qt.QObject = Qt.QtObject.as_QObject(~Model(), second)
    empty: Result<&1, &1, U32 & String, Qt.QFontInfo> <- Qt.Action.attempt(Qt.QFontInfo, Qt.Property.get(~option(), source))
    expected_empty(empty)
    +font: Qt.QFont <- Qt.QFont.new()
    Qt.QFont.setPixelSize(font, Qt.Int32{11})
    +initial: Qt.QFontInfo <- Qt.QFontInfo.new__QFont(font)
    Qt.QFont.setPixelSize(font, Qt.Int32{22})
    +updated: Qt.QFontInfo <- Qt.QFontInfo.new__QFont(font)
    Qt.Property.store(~option(), source, initial)
    value: Qt.QFontInfo <- Qt.Property.get(~option(), source)
    expect_option(value, 11)
    Qt.Property.handleGetter(~accessor(), ~Qt.QFontInfo, ~read_option, source, updated)
    value: Qt.QFontInfo <- Qt.Property.get(~accessor(), source)
    expect_option(value, 22)
    Qt.Method.handle(~optionResult(), ~Qt.QFontInfo, ~read_option, source, updated)
    value: Qt.QFontInfo <- Qt.Method.call(~optionResult(), source)
    expect_option(value, 22)
    Qt.Property.bind(~option(), ~option(), target, source)
    Qt.Property.set(~option(), source, updated)
    value: Qt.QFontInfo <- Qt.Property.get(~option(), target)
    expect_option(value, 22)
    +third: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +calculated: Qt.QObject = Qt.QtObject.as_QObject(~Model(), third)
    Qt.Property.handleBinding(~option(), ~ComputedState, ~computed, calculated, ComputedState{source, calculated})
    value: Qt.QFontInfo <- Qt.Property.get(~option(), calculated)
    expect_option(value, 22)
    count: Qt.Int32 <- Qt.Property.get(~evaluations(), calculated)
    require(U32.is_eq(Qt.Int32.word(count), 1), "A nondefault binding was not initialized in exactly one evaluation")
    Qt.Property.set(~option(), source, initial)
    value: Qt.QFontInfo <- Qt.Property.get(~option(), calculated)
    expect_option(value, 11)
    Qt.Property.set(~option(), source, updated)
    value: Qt.QFontInfo <- Qt.Property.get(~option(), calculated)
    expect_option(value, 22)
    count: Qt.Int32 <- Qt.Property.get(~evaluations(), calculated)
    require(U32.is_eq(Qt.Int32.word(count), 3), "A nondefault computed binding lost dependency tracking or evaluated twice")
    native: Bool <- Qt.CallbackProbe.nondefaultRead(source)
    require(native, "Native property reflection or invocation lost a nondefault value")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Nondefault property values or handlers leaked")
    Qt.Action.lift(Unit, IO.print("QT612_NONDEFAULT_PROPERTIES_OK stored=1 getter=1 method=1 native=1 binding=1 uninitialized=61 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
