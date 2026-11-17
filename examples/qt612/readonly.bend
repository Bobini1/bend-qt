import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def permission(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 1), "Wrong const-view error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Const native view permitted mutation")

def check(+device: Qt.QInputDevice) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(Bool.not(U32.is_eq(Qt.QInputDevice.word(device), 0)), "Qt has no primary keyboard")
    first: String <- Qt.QInputDevice.objectName(device)
    mutation: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QInputDevice.setObjectName(device, "forbidden const mutation"))
    permission(mutation)
    alias_mutation: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.setObjectName(Qt.QInputDevice.as_QObject(device), "forbidden base mutation"))
    permission(alias_mutation)
    deletion: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QInputDevice.destroy(device))
    permission(deletion)
    second: String <- Qt.QInputDevice.objectName(device)
    require(String.eq(first, second), "Const-view rejection changed native state")
    +again: Qt.QInputDevice <- Qt.QInputDevice.primaryKeyboard__String("")
    require(U32.is_eq(Qt.QInputDevice.word(device), Qt.QInputDevice.word(again)), "Const getter changed native identity")
    name: String <- Qt.QInputDevice.name(again)
    return Unit{}

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    device: Qt.QInputDevice <- Qt.QInputDevice.primaryKeyboard__String("")
    before: U32 <- Qt.Runtime.liveObjects()
    check(device)
    after: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(before, after), "Const getter registered duplicate identity")
    Qt.Action.lift(Unit, IO.print("QT612_READONLY_OK const_reads=1 identity=1 mutation_rejected=1 base_alias_rejected=1 borrowed_delete_rejected=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
