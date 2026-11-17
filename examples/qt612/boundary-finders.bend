import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def text(+finder: Qt.QTextBoundaryFinder, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: String <- Qt.QTextBoundaryFinder.string(finder)
    require(String.eq(actual, expected), "Boundary finder lost its retained string")
    Qt.QTextBoundaryFinder.toStart(finder)
    next: Qt.Int64 <- Qt.QTextBoundaryFinder.toNextBoundary(finder)
    require(U32.is_eq(Qt.Int64.lo(next), 5), "Boundary finder working attributes changed")

def copied(+original: Qt.QTextBoundaryFinder, +copy: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextBoundaryFinder.destroy(original)
    text(copy, "hello world")

def original(+finder: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.new__QTextBoundaryFinder(finder), copy => copied(finder, copy))

def assignment_result(+source: Qt.QTextBoundaryFinder, +destination: Qt.QTextBoundaryFinder, result: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextBoundaryFinder.destroy(source)
    text(destination, "hello source")
    text(result, "hello source")

def destination(+source: Qt.QTextBoundaryFinder, +target: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.op_assign(target, source), result => assignment_result(source, target, result))

def assignment(+source: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.new(), target => destination(source, target))

def swapped(+first: Qt.QTextBoundaryFinder, +second: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextBoundaryFinder.swap(first, second)
    text(first, "other string")
    Qt.QTextBoundaryFinder.destroy(first)
    text(second, "hello world")

def swap_first(+first: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.withWorkingBuffer__QTextBoundaryFinder_BoundaryType_String_UInt64(Qt.QTextBoundaryFinder.BoundaryType.Word(), "other string", Qt.UInt64{64, 0}), second => swapped(first, second))

def raw_prefix(+finder: Qt.QTextBoundaryFinder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    next: Qt.Int64 <- Qt.QTextBoundaryFinder.toNextBoundary(finder)
    require(U32.is_eq(Qt.Int64.lo(next), 1), "First raw-text boundary changed")
    last: Qt.Int64 <- Qt.QTextBoundaryFinder.toNextBoundary(finder)
    require(U32.is_eq(Qt.Int64.lo(last), 3), "Raw-text length must count UTF-16 units")
    end: Qt.Int64 <- Qt.QTextBoundaryFinder.toNextBoundary(finder)
    require(U32.is_eq(Qt.Int64.lo(end), 4294967295), "Raw-text finder exceeded its prefix")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.withWorkingBuffer__QTextBoundaryFinder_BoundaryType_String_UInt64(Qt.QTextBoundaryFinder.BoundaryType.Word(), "hello world", Qt.UInt64{64, 0}), finder => original(finder))
    Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.withWorkingBuffer__QTextBoundaryFinder_BoundaryType_String_UInt64(Qt.QTextBoundaryFinder.BoundaryType.Word(), "hello source", Qt.UInt64{64, 0}), finder => assignment(finder))
    Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.withWorkingBuffer__QTextBoundaryFinder_BoundaryType_String(Qt.QTextBoundaryFinder.BoundaryType.Word(), "hello world"), finder => swap_first(finder))
    Qt.QTextBoundaryFinder.with(Unit, Qt.QTextBoundaryFinder.withWorkingBuffer__QTextBoundaryFinder_BoundaryType_String_Int64_UInt64(Qt.QTextBoundaryFinder.BoundaryType.Grapheme(), "a😀z", Qt.Int64{3, 0}, Qt.UInt64{16, 0}), finder => raw_prefix(finder))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Boundary finder backing leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_BOUNDARY_FINDERS_OK working_buffer=1 text=1 copy=1 assignment=1 swap=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
