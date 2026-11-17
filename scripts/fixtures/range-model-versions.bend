import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Convenience error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid convenience operation succeeded")

def number(+model: Qt.QRangeModel, row: U32, column: U32, expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +index: Qt.QModelIndex <- Qt.QRangeModel.index__Int32_Int32(model, Qt.Int32{row}, Qt.Int32{column})
    +value: Qt.QVariant <- Qt.QRangeModel.data__QModelIndex(model, index)
    +actual: Qt.Int32 <- Qt.QVariant.toValue(~Qt.int32(), value)
    require(U32.is_eq(Qt.Int32.word(actual), expected), "Range cell changed")
    Qt.QVariant.destroy(value)
    Qt.QModelIndex.destroy(index)

def qml(+model: Qt.QRangeModel, expression: String) -> Qt.Action(String):
  do Qt.Action<String>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "ranges", Qt.QRangeModel.as_QObject(model))
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    +data: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nQtObject { property string answer: String(" ++ expression ++ ") }")
    +url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    +ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Range QML did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    +value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "answer")
    Qt.QVariant.toString(value)

def basic_models() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +one: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{1})
    +two: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{2})
    +model: Qt.QRangeModel <- Qt.QRangeModel.fromValues([one, two])
    number(model, 1, 0, 2)
    +good: Bool <- Qt.CallbackProbe.rangeNativeEditing(model)
    require(good, "Native range insert/edit/remove or self-object value failed")
    +text: String <- Qt.scoped(String, qml(model, "ranges.insertRows(2, 1) && ranges.setData(ranges.index(2, 0), 19, 2) && ranges.data(ranges.index(2, 0), 0) === 19"))
    require(String.eq(text, "true"), "QML direct range editing failed")
    +table: Qt.QRangeModel <- Qt.QRangeModel.fromRows([[one, two], [two, one]])
    Qt.QVariant.destroy(one)
    Qt.QVariant.destroy(two)
    number(table, 1, 1, 1)
    +columns: Qt.Int32 <- Qt.QRangeModel.columnCount(table)
    require(U32.is_eq(Qt.Int32.word(columns), 2), "Tabular range lost a column")
    good: Bool <- Qt.CallbackProbe.rangeNativeEditing(table)
    require(good, "Native table row or column editing lost its cell state")
    good: Bool <- Qt.CallbackProbe.rangeNativeSelf(table)
    require(good, "Range model could not store its own QObject pointer")
    Qt.QRangeModel.destroy(table)

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def ExtendedRange() -> Qt.ObjectType:
  Qt.QRangeModel.define("ConvenienceExtendedRange", [title()])

def schema_models() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +one: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{1})
    +instance: Qt.ObjectType.Instance(ExtendedRange()) <- Qt.QRangeModel.newAs__List_QVariant_QObject(~ExtendedRange(), [one], Qt.QObject{0})
    +model: Qt.QRangeModel = Qt.ObjectType.asNativeBase(~ExtendedRange(), instance)
    Qt.Property.set(~title(), Qt.QRangeModel.as_QObject(model), "extended")
    text: String <- Qt.Property.get(~title(), Qt.QRangeModel.as_QObject(model))
    require(String.eq(text, "extended"), "Range schema constructor lost its properties")
    number(model, 0, 0, 1)

def replacements() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +target: Qt.QObject <- Qt.QObject.new()
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.qobject(), target)
    +model: Qt.QRangeModel <- Qt.QRangeModel.fromValues([boxed])
    Qt.QVariant.destroy(boxed)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(target))
    expected(Unit, held, 16)
    +index: Qt.QModelIndex <- Qt.QRangeModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0})
    +replacement: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{7})
    +accepted: Bool <- Qt.QRangeModel.setData__QModelIndex_QVariant(model, index, replacement)
    require(accepted, "Range replacement failed")
    Qt.QObject.destroy(target)
    number(model, 0, 0, 7)
    +header_target: Qt.QObject <- Qt.QObject.new()
    +header: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.qobject(), header_target)
    +accepted: Bool <- Qt.QRangeModel.setHeaderData__Int32_Qt_Orientation_QVariant(model, Qt.Int32{0}, Qt.Qt.Orientation.Horizontal(), header)
    require(Bool.not(accepted), "Native value-range header setter changed its contract")
    Qt.QVariant.destroy(header)
    Qt.QObject.destroy(header_target)
    Qt.QModelIndex.destroy(index)
    Qt.QRangeModel.destroy(model)

def metadata_models() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    +seven: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{7})
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "seed", seven)
    +meta: Qt.QMetaObject <- Qt.QQmlPropertyMap.metaObject(map)
    +index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "seed")
    +property: Qt.QMetaProperty <- Qt.QMetaObject.property(meta, index)
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QMetaProperty.arg(), property)
    +model: Qt.QRangeModel <- Qt.QRangeModel.fromValues([boxed, seven])
    Qt.QVariant.destroy(boxed)
    Qt.QMetaProperty.destroy(property)
    Qt.QMetaObject.release(meta)
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "changed", seven)
    number(model, 1, 0, 7)
    +text: String <- Qt.scoped(String, qml(model, "ranges.data(ranges.index(1, 0), 0)"))
    require(String.eq(text, "7"), "Stale metadata poisoned another QML row")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.scoped(String, qml(model, "ranges.data(ranges.index(0, 0), 0)")))
    expected(String, stale, 116)
    +cell: Qt.QModelIndex <- Qt.QRangeModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0})
    stale: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QRangeModel.data__QModelIndex(model, cell))
    expected(Qt.QVariant, stale, 116)
    +accepted: Bool <- Qt.QRangeModel.setData__QModelIndex_QVariant(model, cell, seven)
    require(accepted, "Stale range cell could not be replaced")
    Qt.QQmlPropertyMap.destroy(map)
    number(model, 0, 0, 7)
    Qt.QModelIndex.destroy(cell)
    Qt.QRangeModel.destroy(model)
    Qt.QVariant.destroy(seven)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Action.lift(Unit, IO.print("RANGE_CHECK basic_models"))
    Qt.scoped(Unit, basic_models())
    Qt.Action.lift(Unit, IO.print("RANGE_CHECK schema_models"))
    Qt.scoped(Unit, schema_models())
    Qt.Action.lift(Unit, IO.print("RANGE_CHECK replacements"))
    Qt.scoped(Unit, replacements())
    Qt.Action.lift(Unit, IO.print("RANGE_CHECK metadata_models"))
    Qt.scoped(Unit, metadata_models())
    +objects: U32 <- Qt.Runtime.liveObjects()
    +retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Range model origins leaked")
    Qt.Action.lift(Unit, IO.print("QT_RANGE_MODEL_BEND_OK nativeEditing=1 qmlEditing=1 table=1 subclass=1 qobjectRetention=1 staleIsolation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
