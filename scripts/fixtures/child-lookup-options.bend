import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def count(items: List<&2, Qt.QTimer>) -> U32:
  U32.from_nat(List.length(&2, Qt.QTimer, items))

def same(value: Maybe<&2, Qt.QTimer>, expected: Qt.QTimer) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.fail(Unit, 1, "Child lookup found no timer")
    case Some{timer}: require(U32.is_eq(Qt.QTimer.word(timer), Qt.QTimer.word(expected)), "Child lookup did not return the nearest matching timer")

def tree() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +root: Qt.QObject <- Qt.QObject.new()
    +branch: Qt.QObject <- Qt.QObject.new__QObject(root)
    +nested: Qt.QTimer <- Qt.QTimer.new__QObject(branch)
    +direct: Qt.QTimer <- Qt.QTimer.new__QObject(root)
    Qt.QTimer.setObjectName(nested, "match")
    Qt.QTimer.setObjectName(direct, "match")
    first: Maybe<&2, Qt.QTimer> <- Qt.QTimer.findIn(root, "match")
    same(first, direct)
    recursive: List<&2, Qt.QTimer> <- Qt.QTimer.findAllIn(root, "")
    shallow: List<&2, Qt.QTimer> <- Qt.QTimer.findAllInWith(root, "", Qt.Flags_Qt__FindChildOption{0})
    require(U32.is_eq(count(recursive), 2) && U32.is_eq(count(shallow), 1), "Child lookup ignored the recursion option")
    +pattern: Qt.QRegularExpression <- Qt.QRegularExpression.new__String("^match$")
    matching: List<&2, Qt.QTimer> <- Qt.QTimer.findAllMatchingInWith(root, pattern, Qt.Flags_Qt__FindChildOption{0})
    require(U32.is_eq(count(matching), 1), "Pattern lookup ignored direct children only")
    named: Maybe<&2, Qt.QTimer> <- Qt.QTimer.findInWith(root, "match", Qt.Flags_Qt__FindChildOption{0})
    same(named, direct)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, tree())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Child lookup kept the tree alive")
    Qt.Action.lift(Unit, IO.print("QT612_CHILD_LOOKUP_OPTIONS_OK recursive=1 direct=1 nearest=1 regex=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
