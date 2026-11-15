import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(+code, text)}: require(U32.is_eq(code, 22), "Wrong cross-family cast error: " ++ text)
    case Done{value}: Qt.Action.fail(Unit, 1, "A different native module's type was accepted")

def graph_changed(probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "graphs")

def chart_changed(probe: Qt.QObject, count: Qt.Int32) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "charts")

def graph_series_changed() -> Qt.Signal:
  Qt.Signal.define("seriesChanged", [Qt.QScatter3DSeries.arg()])

def legacy_series_changed() -> Qt.Signal:
  Qt.Signal.define("seriesChanged", [Qt.DataVisualization.QScatter3DSeries.arg()])

def receive_legacy() -> Qt.Method:
  Qt.Method.define("receiveLegacy", [Qt.DataVisualization.QScatter3DSeries.arg()], Qt.unit())

def Relay() -> Qt.QtObject:
  Qt.QtObject.withMethods(Qt.QtObject.withSignals(Qt.QObject.define("MixedNativeRelay", []), [graph_series_changed(), legacy_series_changed()]), [receive_legacy()])

def on_graph_series(probe: Qt.QObject, series: Qt.QScatter3DSeries) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(Qt.QScatter3DSeries.as_QObject(series))
    Qt.QObject.setObjectName(probe, name)

def on_legacy_series(probe: Qt.QObject, series: Qt.DataVisualization.QScatter3DSeries) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(Qt.DataVisualization.QScatter3DSeries.as_QObject(series))
    Qt.QObject.setObjectName(probe, name)

def native_families() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +graph: Qt.QScatter3DSeries <- Qt.QScatter3DSeries.new()
    +legacy: Qt.DataVisualization.QScatter3DSeries <- Qt.DataVisualization.QScatter3DSeries.new()
    Qt.QObject.setObjectName(Qt.QScatter3DSeries.as_QObject(graph), "native-graph")
    Qt.QObject.setObjectName(Qt.DataVisualization.QScatter3DSeries.as_QObject(legacy), "native-legacy")
    +graph_proxy: Qt.QScatterDataProxy <- Qt.QScatterDataProxy.new()
    +legacy_proxy: Qt.DataVisualization.QScatterDataProxy <- Qt.DataVisualization.QScatterDataProxy.new()
    +graph_direct: Qt.QObject <- Qt.QObject.new()
    +legacy_direct: Qt.QObject <- Qt.QObject.new()
    +graph_queued: Qt.QObject <- Qt.QObject.new()
    +legacy_queued: Qt.QObject <- Qt.QObject.new()
    +graph_forwarded: Qt.QObject <- Qt.QObject.new()
    +legacy_forwarded: Qt.QObject <- Qt.QObject.new()
    +legacy_method: Qt.QObject <- Qt.QObject.new()
    +relay: Qt.QtObject.Instance(Relay()) <- Qt.QtObject.new(~Relay())
    Qt.Method.handle(~receive_legacy(), ~Qt.QObject, ~on_legacy_series, Qt.QtObject.as_QObject(~Relay(), relay), legacy_method)
    graph_observer: Qt.Connection <- Qt.Signal.connect(~graph_series_changed(), ~Qt.QObject, ~on_graph_series, Qt.QtObject.as_QObject(~Relay(), relay), graph_forwarded)
    legacy_observer: Qt.Connection <- Qt.Signal.connect(~legacy_series_changed(), ~Qt.QObject, ~on_legacy_series, Qt.QtObject.as_QObject(~Relay(), relay), legacy_forwarded)
    graph_forward: Qt.Connection <- Qt.Signal.connectSignalWith(~graph_series_changed(), ~graph_series_changed(), Qt.QScatterDataProxy.as_QObject(graph_proxy), Qt.QtObject.as_QObject(~Relay(), relay), Qt.Qt.ConnectionType.QueuedConnection())
    legacy_forward: Qt.Connection <- Qt.Signal.connectSignal(~legacy_series_changed(), ~legacy_series_changed(), Qt.DataVisualization.QScatterDataProxy.as_QObject(legacy_proxy), Qt.QtObject.as_QObject(~Relay(), relay))
    method_forward: Qt.Connection <- Qt.Signal.connectMethodWith(~legacy_series_changed(), ~receive_legacy(), Qt.DataVisualization.QScatterDataProxy.as_QObject(legacy_proxy), Qt.QtObject.as_QObject(~Relay(), relay), Qt.Qt.ConnectionType.QueuedConnection())
    wrong_forward: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection, Qt.Signal.connectSignal(~graph_series_changed(), ~legacy_series_changed(), Qt.QScatterDataProxy.as_QObject(graph_proxy), Qt.QtObject.as_QObject(~Relay(), relay)))
    rejected(Qt.Connection, wrong_forward)
    graph_connection: Qt.Connection <- Qt.Signal.connect(~graph_series_changed(), ~Qt.QObject, ~on_graph_series, Qt.QScatterDataProxy.as_QObject(graph_proxy), graph_direct)
    legacy_connection: Qt.Connection <- Qt.Signal.connect(~legacy_series_changed(), ~Qt.QObject, ~on_legacy_series, Qt.DataVisualization.QScatterDataProxy.as_QObject(legacy_proxy), legacy_direct)
    graph_queue: Qt.Connection <- Qt.Signal.connectWith(~graph_series_changed(), ~Qt.QObject, ~on_graph_series, Qt.QScatterDataProxy.as_QObject(graph_proxy), Qt.Qt.ConnectionType.QueuedConnection(), graph_queued)
    legacy_queue: Qt.Connection <- Qt.Signal.connectWith(~legacy_series_changed(), ~Qt.QObject, ~on_legacy_series, Qt.DataVisualization.QScatterDataProxy.as_QObject(legacy_proxy), Qt.Qt.ConnectionType.QueuedConnection(), legacy_queued)
    wrong_connection: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection, Qt.Signal.connect(~legacy_series_changed(), ~Qt.QObject, ~on_legacy_series, Qt.QScatterDataProxy.as_QObject(graph_proxy), legacy_direct))
    rejected(Qt.Connection, wrong_connection)
    Qt.QScatter3DSeries.setDataProxy(graph, graph_proxy)
    Qt.DataVisualization.QScatter3DSeries.setDataProxy(legacy, legacy_proxy)
    Qt.QCoreApplication.processEvents()
    graph_name: String <- Qt.QObject.objectName(graph_direct)
    legacy_name: String <- Qt.QObject.objectName(legacy_direct)
    queued_graph_name: String <- Qt.QObject.objectName(graph_queued)
    queued_legacy_name: String <- Qt.QObject.objectName(legacy_queued)
    require(String.eq(graph_name, "native-graph") && String.eq(legacy_name, "native-legacy") && String.eq(queued_graph_name, "native-graph") && String.eq(queued_legacy_name, "native-legacy"), "Native module signal aliases lost their concrete QObject argument")
    forwarded_graph_name: String <- Qt.QObject.objectName(graph_forwarded)
    forwarded_legacy_name: String <- Qt.QObject.objectName(legacy_forwarded)
    method_name: String <- Qt.QObject.objectName(legacy_method)
    require(String.eq(forwarded_graph_name, "native-graph") && String.eq(forwarded_legacy_name, "native-legacy") && String.eq(method_name, "native-legacy"), "Qt signal or method destination lost its module argument identity")
    +value: Qt.QVariant <- Qt.QObject.property(Qt.QScatterDataProxy.as_QObject(graph_proxy), "series")
    copy: Qt.QScatter3DSeries <- Qt.QVariant.toValue(~Qt.QScatter3DSeries.arg(), value)
    copied_name: String <- Qt.QObject.objectName(Qt.QScatter3DSeries.as_QObject(copy))
    require(String.eq(copied_name, "native-graph"), "Native property QVariant lost its originating QObject family")
    wrong_value: Result<&1, &1, U32 & String, Qt.DataVisualization.QScatter3DSeries> <- Qt.Action.attempt(Qt.DataVisualization.QScatter3DSeries, Qt.QVariant.toValue(~Qt.DataVisualization.QScatter3DSeries.arg(), value))
    rejected(Qt.DataVisualization.QScatter3DSeries, wrong_value)

def peer() -> Qt.Property:
  Qt.Property.define("peer", Qt.Charts.QLineSeries.arg())

def graph_items() -> Qt.Property:
  Qt.Property.define("graphItems", Qt.list(Qt.QScatterDataItem.arg()))

def legacy_items() -> Qt.Property:
  Qt.Property.define("legacyItems", Qt.list(Qt.DataVisualization.QScatterDataItem.arg()))

def Holder() -> Qt.QtObject:
  Qt.QObject.define("MixedModuleHolder", [peer(), graph_items(), legacy_items()])

def GraphSeries() -> Qt.QtObject:
  Qt.QLineSeries.define("BendGraphSeries", [])

def ChartSeries() -> Qt.QtObject:
  Qt.Charts.QLineSeries.define("BendChartSeries", [])

def qml_source() -> String:
  "import QtQml\nQtObject { property string result: holder.peer.objectName + ':' + holder.graphItems.length + ':' + holder.legacyItems.length; Component.onCompleted: holder.peer.objectName = 'qml-chart' }"

def qml_imports_source() -> String:
  "import QtQml\nimport QtGraphs as Graphs\nimport QtCharts as Charts\nimport QtDataVisualization as Legacy\nQtObject { property Graphs.Scatter3DSeries graph: Graphs.Scatter3DSeries { name: 'graph-series' }; property Legacy.Scatter3DSeries legacy: Legacy.Scatter3DSeries { name: 'legacy-series' }; property Charts.LineSeries chart: Charts.LineSeries { name: 'chart-series' }; property string result: holder.peer.objectName + ':' + holder.graphItems.length + ':' + holder.legacyItems.length + (graph.name === 'graph-series' && legacy.name === 'legacy-series' && chart.name === 'chart-series' ? '' : ':wrong-native-series'); Component.onCompleted: holder.peer.objectName = 'qml-chart' }"

def qml_families() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    graph: Qt.QtObject.Instance(GraphSeries()) <- Qt.QtObject.new(~GraphSeries())
    +chart: Qt.QtObject.Instance(ChartSeries()) <- Qt.QtObject.new(~ChartSeries())
    Qt.QObject.setObjectName(Qt.QtObject.as_QObject(~ChartSeries(), chart), "chart")
    +holder: Qt.QtObject.Instance(Holder()) <- Qt.QtObject.new(~Holder())
    Qt.Property.set(~peer(), Qt.QtObject.as_QObject(~Holder(), holder), Qt.QtObject.asNativeBase(~ChartSeries(), chart))
    point: Qt.QScatterDataItem <- Qt.QScatterDataItem.new()
    legacy: Qt.DataVisualization.QScatterDataItem <- Qt.DataVisualization.QScatterDataItem.new()
    Qt.Property.set(~graph_items(), Qt.QtObject.as_QObject(~Holder(), holder), [point])
    Qt.Property.set(~legacy_items(), Qt.QtObject.as_QObject(~Holder(), holder), [legacy])
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "holder", Qt.QtObject.as_QObject(~Holder(), holder))
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8(qml_source())
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Mixed-module QML did not compile")
    +object: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QObject.property(object, "result")
    +text: String <- Qt.QVariant.toString(result)
    require(String.eq(text, "qml-chart:1:1"), "QML lost a qualified QObject or native value sequence: " ++ text)

def families() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +modern: Qt.QLineSeries <- Qt.QLineSeries.new()
    +legacy: Qt.Charts.QLineSeries <- Qt.Charts.QLineSeries.new()
    +graph_probe: Qt.QObject <- Qt.QObject.new()
    +chart_probe: Qt.QObject <- Qt.QObject.new()
    graph_connection: Qt.Connection <- Qt.QLineSeries.connect_countChanged(~Qt.QObject, ~graph_changed, modern, graph_probe)
    chart_connection: Qt.Connection <- Qt.Charts.QLineSeries.connect_pointAdded(~Qt.QObject, ~chart_changed, legacy, chart_probe)
    Qt.QXYSeries.append__F64_F64(Qt.QLineSeries.as_QXYSeries(modern), Qt.F64{0, 0}, Qt.F64{0, 1072693248})
    Qt.Charts.QXYSeries.append__F64_F64(Qt.Charts.QLineSeries.as_QXYSeries(legacy), Qt.F64{0, 0}, Qt.F64{0, 1073741824})
    graph_count: Qt.Int64 <- Qt.QXYSeries.count(Qt.QLineSeries.as_QXYSeries(modern))
    chart_count: Qt.Int32 <- Qt.Charts.QXYSeries.count(Qt.Charts.QLineSeries.as_QXYSeries(legacy))
    require(U32.is_eq(Qt.Int64.lo(graph_count), 1) && U32.is_eq(Qt.Int32.word(chart_count), 1), "Native series families shared the wrong implementation")
    graph_name: String <- Qt.QObject.objectName(graph_probe)
    chart_name: String <- Qt.QObject.objectName(chart_probe)
    require(String.eq(graph_name, "graphs") && String.eq(chart_name, "charts"), "Partition callbacks did not share the Bend host")
    wrong_graph: Result<&1, &1, U32 & String, Qt.QLineSeries> <- Qt.Action.attempt(Qt.QLineSeries, Qt.QLineSeries.cast(Qt.Charts.QLineSeries.as_QObject(legacy)))
    rejected(Qt.QLineSeries, wrong_graph)
    wrong_chart: Result<&1, &1, U32 & String, Qt.Charts.QLineSeries> <- Qt.Action.attempt(Qt.Charts.QLineSeries, Qt.Charts.QLineSeries.cast(Qt.QLineSeries.as_QObject(modern)))
    rejected(Qt.Charts.QLineSeries, wrong_chart)
    +graph_item: Qt.QScatterDataItem <- Qt.QScatterDataItem.new()
    +legacy_item: Qt.DataVisualization.QScatterDataItem <- Qt.DataVisualization.QScatterDataItem.new()
    Qt.QScatterDataItem.setX(graph_item, Qt.F64{0, 1072693248})
    Qt.DataVisualization.QScatterDataItem.setX(legacy_item, Qt.F64{0, 1073741824})
    graph_x: Qt.F64 <- Qt.QScatterDataItem.x(graph_item)
    legacy_x: Qt.F64 <- Qt.DataVisualization.QScatterDataItem.x(legacy_item)
    require(U32.is_eq(Qt.F64.hi(graph_x), 1072693248) && U32.is_eq(Qt.F64.hi(legacy_x), 1073741824), "Same-named native values crossed module implementations")
    +graph_variant: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QScatterDataItem.arg(), graph_item)
    +legacy_variant: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.DataVisualization.QScatterDataItem.arg(), legacy_item)
    graph_copy: Qt.QScatterDataItem <- Qt.QVariant.toValue(~Qt.QScatterDataItem.arg(), graph_variant)
    legacy_copy: Qt.DataVisualization.QScatterDataItem <- Qt.QVariant.toValue(~Qt.DataVisualization.QScatterDataItem.arg(), legacy_variant)
    copied_graph_x: Qt.F64 <- Qt.QScatterDataItem.x(graph_copy)
    copied_legacy_x: Qt.F64 <- Qt.DataVisualization.QScatterDataItem.x(legacy_copy)
    require(U32.is_eq(Qt.F64.hi(copied_graph_x), 1072693248) && U32.is_eq(Qt.F64.hi(copied_legacy_x), 1073741824), "QVariant lost the native value family")
    wrong_value: Result<&1, &1, U32 & String, Qt.QScatterDataItem> <- Qt.Action.attempt(Qt.QScatterDataItem, Qt.QVariant.toValue(~Qt.QScatterDataItem.arg(), legacy_variant))
    rejected(Qt.QScatterDataItem, wrong_value)
    +graph_list: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.list(Qt.QScatterDataItem.arg()), [graph_item])
    +legacy_list: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.list(Qt.DataVisualization.QScatterDataItem.arg()), [legacy_item])
    graph_items: List<&2, Qt.QScatterDataItem> <- Qt.QVariant.toValue(~Qt.list(Qt.QScatterDataItem.arg()), graph_list)
    legacy_items: List<&2, Qt.DataVisualization.QScatterDataItem> <- Qt.QVariant.toValue(~Qt.list(Qt.DataVisualization.QScatterDataItem.arg()), legacy_list)
    require(U32.is_eq(U32.from_nat(List.length(&2, Qt.QScatterDataItem, graph_items)), 1) && U32.is_eq(U32.from_nat(List.length(&2, Qt.DataVisualization.QScatterDataItem, legacy_items)), 1), "QVariant lost a native value container")
    wrong_list: Result<&1, &1, U32 & String, List<&2, Qt.QScatterDataItem>> <- Qt.Action.attempt(List<&2, Qt.QScatterDataItem>, Qt.QVariant.toValue(~Qt.list(Qt.QScatterDataItem.arg()), legacy_list))
    rejected(List<&2, Qt.QScatterDataItem>, wrong_list)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, families())
    Qt.scoped(Unit, native_families())
    Qt.scoped(Unit, qml_families())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Partition runtime leaked native handles")
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(data, 0), "Partition runtime leaked Bend data")
    Qt.Action.lift(Unit, IO.print("QT_MODULE_PARTITIONS_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
