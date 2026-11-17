import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def source() -> List<&2, String>:
  "2 1 2 1" <> ". c #ff0000" <> "  c None" <> ". " <> Nil{}

def red(+color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    channel: Qt.Int32 <- Qt.QColor.red(color)
    alpha: Qt.Int32 <- Qt.QColor.alpha(color)
    require(U32.is_eq(Qt.Int32.word(channel), 255) && U32.is_eq(Qt.Int32.word(alpha), 255), "XPM color table changed")

def transparent(color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    alpha: Qt.Int32 <- Qt.QColor.alpha(color)
    require(U32.is_eq(Qt.Int32.word(alpha), 0), "XPM transparent pixel changed")

def image(+value: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QImage.width(value)
    height: Qt.Int32 <- Qt.QImage.height(value)
    require(U32.is_eq(Qt.Int32.word(width), 2) && U32.is_eq(Qt.Int32.word(height), 1), "XPM dimensions changed")
    Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(value, Qt.Int32{0}, Qt.Int32{0}), color => red(color))
    Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(value, Qt.Int32{1}, Qt.Int32{0}), transparent)

def pixmap(+value: Qt.QPixmap) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QPixmap.width(value)
    alpha: Bool <- Qt.QPixmap.hasAlphaChannel(value)
    require(U32.is_eq(Qt.Int32.word(width), 2) && alpha, "XPM pixmap constructor lost image data")

def rejected(expected: U32, result: Result<&1, &1, U32 & String, Qt.QImage>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong XPM extent error")
    case Done{value}: Qt.Action.finally(Unit, Qt.Action.fail(Unit, 1, "Malformed XPM array reached the native reader"), Qt.QImage.release(value))

def reject(lines: List<&2, String>, code: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.QImage> <- Qt.Action.attempt(Qt.QImage, Qt.QImage.new__List_String(lines))
    rejected(code, result)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QImage.with(Unit, Qt.QImage.new__List_String(source()), value => image(value))
    Qt.QPixmap.with(Unit, Qt.QPixmap.new__List_String(source()), value => pixmap(value))
    reject(Nil{}, 22)
    reject("2 1 2 1" <> ". c #ff0000" <> Nil{}, 22)
    reject("2 1 1 1" <> ". c #ff0000" <> "." <> Nil{}, 22)
    reject("999999999999999999999999999 1 1 1" <> Nil{}, 22)
    reject("32768 1 1 1" <> Nil{}, 34)
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "XPM conversion leaked native image handles")
    Qt.Action.lift(Unit, IO.print("QT612_XPM_ARRAYS_OK image=1 pixmap=1 transparency=1 missing_rows=1 short_pixels=1 checked_header=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
