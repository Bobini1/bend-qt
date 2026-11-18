import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def count_changed(probe: Qt.QObject, count: Qt.Int32) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, U32.show(Qt.Int32.word(count)))

def series_count(series: Qt.Charts.QLineSeries, values: List<&2, Qt.Charts.QAbstractSeries>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}: require(U32.is_eq(Qt.Charts.QAbstractSeries.word(value), Qt.Charts.QLineSeries.word(series)), "Chart changed series identity")
    case _: Qt.Action.fail(Unit, 1, "Chart has the wrong series count")

def scatter_snapshot(values: List<&2, Qt.DataVisualization.QScatterDataItem>) -> Qt.Action(Unit):
  match values:
    case value <> rest: do Qt.Action<Unit>:
      position: Qt.QVector3D <- Qt.DataVisualization.QScatterDataItem.position(value)
      return Unit{}
    case _: Qt.Action.fail(Unit, 1, "Scatter snapshot was empty")

def surface_snapshot(values: List<&2, List<&2, Qt.DataVisualization.QSurfaceDataItem>>) -> Qt.Action(Unit):
  match values:
    case (item <> Nil{}) <> rest: do Qt.Action<Unit>:
      position: Qt.QVector3D <- Qt.DataVisualization.QSurfaceDataItem.position(item)
      return Unit{}
    case _: Qt.Action.fail(Unit, 1, "Surface array snapshot had the wrong shape")

def charts() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +chart: Qt.Charts.QChart <- Qt.Charts.QChart.new()
    +series: Qt.Charts.QLineSeries <- Qt.Charts.QLineSeries.new()
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Charts.QLineSeries.connect_pointAdded(~Qt.QObject, ~count_changed, series, probe)
    Qt.Charts.QXYSeries.append__F64_F64(Qt.Charts.QLineSeries.as_QXYSeries(series), Qt.F64{0, 0}, Qt.F64{0, 1072693248})
    Qt.Charts.QXYSeries.append__F64_F64(Qt.Charts.QLineSeries.as_QXYSeries(series), Qt.F64{0, 1072693248}, Qt.F64{0, 1073741824})
    count: Qt.Int32 <- Qt.Charts.QXYSeries.count(Qt.Charts.QLineSeries.as_QXYSeries(series))
    require(U32.is_eq(Qt.Int32.word(count), 2), "Chart points were not appended")
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, "1"), "Chart signal did not reach Bend synchronously")
    Qt.Charts.QChart.addSeries(chart, Qt.Charts.QLineSeries.as_QAbstractSeries(series))
    Qt.Charts.QChart.createDefaultAxes(chart)
    values: List<&2, Qt.Charts.QAbstractSeries> <- Qt.Charts.QChart.series(chart)
    series_count(series, values)

def scatter() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.DataVisualization.QScatterDataProxy <- Qt.DataVisualization.QScatterDataProxy.new()
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.DataVisualization.QScatterDataProxy.connect_itemCountChanged(~Qt.QObject, ~count_changed, proxy, probe)
    +position: Qt.QVector3D <- Qt.QVector3D.new()
    +item: Qt.DataVisualization.QScatterDataItem <- Qt.DataVisualization.QScatterDataItem.new__QVector3D(position)
    index: Qt.Int32 <- Qt.DataVisualization.QScatterDataProxy.addItem(proxy, item)
    require(U32.is_eq(Qt.Int32.word(index), 0), "Scatter insertion index changed")
    Qt.DataVisualization.QScatterDataProxy.resetArray(proxy, [item, item])
    Qt.DataVisualization.QScatterDataItem.release(item)
    count: Qt.Int32 <- Qt.DataVisualization.QScatterDataProxy.itemCount(proxy)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Scatter array was not copied")
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, "2"), "DataVisualization signal did not reach Bend")
    snapshot: List<&2, Qt.DataVisualization.QScatterDataItem> <- Qt.DataVisualization.QScatterDataProxy.array(proxy)
    Qt.DataVisualization.QScatterDataProxy.resetArray(proxy, [])
    scatter_snapshot(snapshot)

def bars() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.DataVisualization.QBarDataProxy <- Qt.DataVisualization.QBarDataProxy.new()
    +item: Qt.DataVisualization.QBarDataItem <- Qt.DataVisualization.QBarDataItem.new__F64(Qt.F64{0, 1078263808})
    index: Qt.Int32 <- Qt.DataVisualization.QBarDataProxy.addRow__List_DataVisualization_QBarDataItem(proxy, [item])
    Qt.DataVisualization.QBarDataProxy.resetArray__List_List_DataVisualization_QBarDataItem(proxy, [[item], [item]])
    Qt.DataVisualization.QBarDataItem.release(item)
    count: Qt.Int32 <- Qt.DataVisualization.QBarDataProxy.rowCount(proxy)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Bar rows were not copied")
    +snapshot: Qt.DataVisualization.QBarDataItem <- Qt.DataVisualization.QBarDataProxy.itemAt__Int32_Int32(proxy, Qt.Int32{1}, Qt.Int32{0})
    Qt.DataVisualization.QBarDataProxy.resetArray(proxy)
    value: Qt.F64 <- Qt.DataVisualization.QBarDataItem.value(snapshot)
    require(U32.is_eq(Qt.F64.hi(value), 1078263808), "Bar snapshot expired after replacing its array")

def surface() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.DataVisualization.QSurfaceDataProxy <- Qt.DataVisualization.QSurfaceDataProxy.new()
    position: Qt.QVector3D <- Qt.QVector3D.new()
    +item: Qt.DataVisualization.QSurfaceDataItem <- Qt.DataVisualization.QSurfaceDataItem.new__QVector3D(position)
    index: Qt.Int32 <- Qt.DataVisualization.QSurfaceDataProxy.addRow(proxy, [item])
    Qt.DataVisualization.QSurfaceDataProxy.resetArray(proxy, [[item], [item]])
    Qt.DataVisualization.QSurfaceDataItem.release(item)
    count: Qt.Int32 <- Qt.DataVisualization.QSurfaceDataProxy.rowCount(proxy)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Surface rows were not copied")
    snapshot: List<&2, List<&2, Qt.DataVisualization.QSurfaceDataItem>> <- Qt.DataVisualization.QSurfaceDataProxy.array(proxy)
    Qt.DataVisualization.QSurfaceDataProxy.resetArray(proxy, [])
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
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
