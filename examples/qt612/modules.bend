import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def query(+value: Qt.QSqlQuery) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    executed: Bool <- Qt.QSqlQuery.exec__String(value, "SELECT 'Bend SQL works' AS message")
    require(executed, "SQLite query failed")
    row: Bool <- Qt.QSqlQuery.next(value)
    require(row, "SQLite query returned no row")
    text: String <- Qt.QVariant.with(String, Qt.QSqlQuery.value__Int32(value, Qt.Int32{0}), Qt.QVariant.toString)
    require(String.eq(text, "Bend SQL works"), "SQLite result conversion failed")

def database(+value: Qt.QSqlDatabase) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSqlDatabase.setDatabaseName(value, ":memory:")
    opened: Bool <- Qt.QSqlDatabase.open(value)
    require(opened, "Qt SQLite driver did not open")
    Qt.Action.finally(Unit, Qt.QSqlQuery.with(Unit, Qt.QSqlQuery.new__QSqlDatabase(value), item => query(item)), Qt.QSqlDatabase.close(value))

def audio(+value: Qt.QAudioFormat) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAudioFormat.setSampleRate(value, Qt.Int32{48000})
    Qt.QAudioFormat.setChannelCount(value, Qt.Int32{2})
    Qt.QAudioFormat.setSampleFormat(value, Qt.QAudioFormat.SampleFormat.Int16())
    valid: Bool <- Qt.QAudioFormat.isValid(value)
    require(valid, "Audio format was rejected")
    size: Qt.Int32 <- Qt.QAudioFormat.bytesPerFrame(value)
    require(U32.is_eq(Qt.Int32.word(size), 4), "Audio frame size is wrong")

def bars(+value: Qt.QBarSet) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    one: Qt.F64 <- Qt.F64.fromString("1")
    two: Qt.F64 <- Qt.F64.fromString("2")
    Qt.QBarSet.append__List_F64(value, [one, two])
    count: Qt.Int64 <- Qt.QBarSet.count(value)
    require(U32.is_eq(Qt.Int64.lo(count), 2), "Qt Graphs did not append both values")

def svg_bytes(bytes: Qt.QByteArray, +renderer: Qt.QSvgRenderer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    loaded: Bool <- Qt.QSvgRenderer.load__QByteArray(renderer, bytes)
    require(loaded, "SVG bytes failed to load")
    valid: Bool <- Qt.QSvgRenderer.isValid(renderer)
    require(valid, "Loaded SVG is invalid")

def svg(renderer: Qt.QSvgRenderer) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("<svg xmlns='http://www.w3.org/2000/svg' width='20' height='10'><rect width='20' height='10' fill='red'/></svg>"), bytes => svg_bytes(bytes, renderer))

def coordinate(+value: Qt.QGeoCoordinate) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.QGeoCoordinate.isValid(value)
    require(valid, "Positioning coordinate is invalid")
    latitude: Qt.F64 <- Qt.QGeoCoordinate.latitude(value)
    text: String <- Qt.F64.toString(latitude)
    require(String.eq(text, "51"), "Positioning coordinate round trip failed")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Action.finally(Unit, Qt.QSqlDatabase.with(Unit, Qt.QSqlDatabase.addDatabase__String_String("QSQLITE", "bend-modules"), value => database(value)), Qt.QSqlDatabase.removeDatabase("bend-modules"))
    Qt.QAudioFormat.with(Unit, Qt.QAudioFormat.new(), value => audio(value))
    Qt.QBarSet.with(Unit, Qt.QBarSet.new(), value => bars(value))
    Qt.QSvgRenderer.with(Unit, Qt.QSvgRenderer.new(), svg)
    empty: Bool <- Qt.QDomDocument.with(Bool, Qt.QDomDocument.new(), Qt.QDomDocument.isNull)
    require(empty, "Empty XML document is not null")
    latitude: Qt.F64 <- Qt.F64.fromString("51")
    longitude: Qt.F64 <- Qt.F64.fromString("22")
    Qt.QGeoCoordinate.with(Unit, Qt.QGeoCoordinate.new__F64_F64(latitude, longitude), value => coordinate(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Broad module scopes leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_MODULES_OK sqlite=1 multimedia=1 graphs=1 svg=1 xml=1 positioning=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
