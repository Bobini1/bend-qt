import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def count_changed(probe: Qt.QObject, count: Qt.Int32) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, U32.show(Qt.Int32.word(count)))

def series_count(series: Qt.QLineSeries, values: List<&2, Qt.QAbstractSeries>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}: require(U32.is_eq(Qt.QAbstractSeries.word(value), Qt.QLineSeries.word(series)), "Chart changed series identity")
    case _: Qt.Action.fail(Unit, 1, "Chart has the wrong series count")

def scatter_snapshot(values: List<&2, Qt.QScatterDataItem>) -> Qt.Action(Unit):
  match values:
    case value <> rest: do Qt.Action<Unit>:
      position: Qt.QVector3D <- Qt.QScatterDataItem.position(value)
      return Unit{}
    case _: Qt.Action.fail(Unit, 1, "Scatter snapshot was empty")

def surface_snapshot(values: List<&2, List<&2, Qt.QSurfaceDataItem>>) -> Qt.Action(Unit):
  match values:
    case (item <> Nil{}) <> rest: do Qt.Action<Unit>:
      position: Qt.QVector3D <- Qt.QSurfaceDataItem.position(item)
      return Unit{}
    case _: Qt.Action.fail(Unit, 1, "Surface array snapshot had the wrong shape")

def charts() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +chart: Qt.QChart <- Qt.QChart.new()
    +series: Qt.QLineSeries <- Qt.QLineSeries.new()
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.QLineSeries.connect_pointAdded(~Qt.QObject, ~count_changed, series, probe)
    Qt.QXYSeries.append__F64_F64(Qt.QLineSeries.as_QXYSeries(series), Qt.F64{0, 0}, Qt.F64{0, 1072693248})
    Qt.QXYSeries.append__F64_F64(Qt.QLineSeries.as_QXYSeries(series), Qt.F64{0, 1072693248}, Qt.F64{0, 1073741824})
    count: Qt.Int32 <- Qt.QXYSeries.count(Qt.QLineSeries.as_QXYSeries(series))
    require(U32.is_eq(Qt.Int32.word(count), 2), "Chart points were not appended")
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, "1"), "Chart signal did not reach Bend synchronously")
    Qt.QChart.addSeries(chart, Qt.QLineSeries.as_QAbstractSeries(series))
    Qt.QChart.createDefaultAxes(chart)
    values: List<&2, Qt.QAbstractSeries> <- Qt.QChart.series(chart)
    series_count(series, values)

def scatter() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.QScatterDataProxy <- Qt.QScatterDataProxy.new()
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.QScatterDataProxy.connect_itemCountChanged(~Qt.QObject, ~count_changed, proxy, probe)
    +position: Qt.QVector3D <- Qt.QVector3D.new()
    +item: Qt.QScatterDataItem <- Qt.QScatterDataItem.new__QVector3D(position)
    index: Qt.Int32 <- Qt.QScatterDataProxy.addItem(proxy, item)
    require(U32.is_eq(Qt.Int32.word(index), 0), "Scatter insertion index changed")
    Qt.QScatterDataProxy.resetArray(proxy, [item, item])
    Qt.QScatterDataItem.release(item)
    count: Qt.Int32 <- Qt.QScatterDataProxy.itemCount(proxy)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Scatter array was not copied")
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, "2"), "DataVisualization signal did not reach Bend")
    snapshot: List<&2, Qt.QScatterDataItem> <- Qt.QScatterDataProxy.array(proxy)
    Qt.QScatterDataProxy.resetArray(proxy, [])
    scatter_snapshot(snapshot)

def bars() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.QBarDataProxy <- Qt.QBarDataProxy.new()
    +item: Qt.QBarDataItem <- Qt.QBarDataItem.new__F64(Qt.F64{0, 1078263808})
    index: Qt.Int32 <- Qt.QBarDataProxy.addRow__List_QBarDataItem(proxy, [item])
    Qt.QBarDataProxy.resetArray__List_List_QBarDataItem(proxy, [[item], [item]])
    Qt.QBarDataItem.release(item)
    count: Qt.Int32 <- Qt.QBarDataProxy.rowCount(proxy)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Bar rows were not copied")
    +snapshot: Qt.QBarDataItem <- Qt.QBarDataProxy.itemAt__Int32_Int32(proxy, Qt.Int32{1}, Qt.Int32{0})
    Qt.QBarDataProxy.resetArray(proxy)
    value: Qt.F64 <- Qt.QBarDataItem.value(snapshot)
    require(U32.is_eq(Qt.F64.hi(value), 1078263808), "Bar snapshot expired after replacing its array")

def surface() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.QSurfaceDataProxy <- Qt.QSurfaceDataProxy.new()
    position: Qt.QVector3D <- Qt.QVector3D.new()
    +item: Qt.QSurfaceDataItem <- Qt.QSurfaceDataItem.new__QVector3D(position)
    index: Qt.Int32 <- Qt.QSurfaceDataProxy.addRow(proxy, [item])
    Qt.QSurfaceDataProxy.resetArray(proxy, [[item], [item]])
    Qt.QSurfaceDataItem.release(item)
    count: Qt.Int32 <- Qt.QSurfaceDataProxy.rowCount(proxy)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Surface rows were not copied")
    snapshot: List<&2, List<&2, Qt.QSurfaceDataItem>> <- Qt.QSurfaceDataProxy.array(proxy)
    Qt.QSurfaceDataProxy.resetArray(proxy, [])
    surface_snapshot(snapshot)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, charts())
    Qt.scoped(Unit, scatter())
    Qt.scoped(Unit, bars())
    Qt.scoped(Unit, surface())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Charts or DataVisualization objects leaked")
    Qt.Action.lift(Unit, IO.print("QT612_LEGACY_CHARTS_OK chart=1 signals=1 ownership=1 scatter=1 bars=1 surface=1 snapshots=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
