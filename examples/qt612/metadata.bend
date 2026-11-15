import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def named(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, expected), "Native metadata name differs")
    case None{}: Qt.Action.fail(Unit, 1, "Native metadata text disappeared")

def absent(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{text}: Qt.Action.fail(Unit, 1, "Null metadata text became a String")

def valid(value: Qt.QMetaType) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QMetaType.name(value)
    named(name, "int")

def invalid(value: Qt.QMetaType) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QMetaType.name(value)
    absent(name)

def version(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(Bool.not(String.eq(text, "")), "Qt version text is empty")
    case None{}: Qt.Action.fail(Unit, 1, "Qt version text is null")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QMetaType.with(Unit, Qt.QMetaType.new(), invalid)
    Qt.QMetaType.with(Unit, Qt.QMetaType.new__Int32(Qt.Int32{Qt.QMetaType.Type.word(Qt.QMetaType.Type.Int())}), valid)
    text: Maybe<&2, String> <- Qt.Global.qVersion()
    version(text)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Metadata scopes leaked")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_OK nullable_text=1 copied_names=1 version=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
