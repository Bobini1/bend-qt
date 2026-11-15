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

def tag(value: Maybe<&2, Qt.QFont.Tag>) -> Qt.Action(Unit):
  match value:
    case Some{+value}:
      do Qt.Action<Unit>:
        +font: Qt.QFont <- Qt.QFont.new()
        Qt.QFont.setFeature(font, value, 1)
        +feature: U32 <- Qt.QFont.featureValue(font, value)
        require(U32.is_eq(feature, 1), "Checked font tag did not reach Qt")
    case None{}: Qt.Action.fail(Unit, 1, "Valid OpenType tag was rejected")

def entries(values: List<&2, Qt.QFileInfo>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}:
      do Qt.Action<Unit>:
        +name: String <- Qt.QFileInfo.fileName(value)
        require(String.eq(name, "entry"), "Directory entry snapshot changed")
    case _: Qt.Action.fail(Unit, 1, "Directory listing lost an entry")

def invalid_tag(value: Maybe<&2, Qt.QFont.Tag>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{tag}: Qt.Action.fail(Unit, 1, "Invalid OpenType tag was accepted")

def values() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +value: Maybe<&2, Qt.QFont.Tag> <- Qt.QFont.Tag.fromString("liga")
    tag(value)
    +value: Maybe<&2, Qt.QFont.Tag> <- Qt.QFont.Tag.fromValue(1818847073)
    tag(value)
    +invalid: Maybe<&2, Qt.QFont.Tag> <- Qt.QFont.Tag.fromString("longer")
    invalid_tag(invalid)
    +temporary: Qt.QTemporaryDir <- Qt.QTemporaryDir.new()
    +path: String <- Qt.QTemporaryDir.path(temporary)
    +directory: Qt.QDir <- Qt.QDir.new__String(path)
    +created: Bool <- Qt.QDir.mkdir__String(directory, "entry")
    require(created, "Temporary directory creation failed")
    +listing: Qt.QDirListing <- Qt.QDirListing.new__String(path)
    +snapshots: List<&2, Qt.QFileInfo> <- Qt.QDirListing.entries(listing)
    Qt.QDirListing.destroy(listing)
    entries(snapshots)
    +locale: Qt.QLocale <- Qt.QLocale.system()
    name: String <- Qt.QLocale.name(locale)
    require(Bool.not(String.eq(name, "")), "System locale disappeared")
    +action: Qt.QAction <- Qt.QAction.new__QObject(Qt.QObject{0})
    +menu: Qt.QMenu <- Qt.QMenu.new__QWidget(Qt.QWidget{0})
    Qt.QAction.setMenu(action, Qt.QMenu.as_QObject(menu))
    actual: Qt.QMenu <- Qt.QAction.menu(action)
    require(U32.is_eq(Qt.QMenu.word(actual), Qt.QMenu.word(menu)), "Action menu template getter changed identity")

def script() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QJSEngine <- Qt.QJSEngine.new()
    +number: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{42})
    +map: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.variantMap(), [Qt.PairValue{"answer", number}])
    +value: Qt.QJSValue <- Qt.QJSEngine.toScriptValue(engine, map)
    Qt.QVariant.destroy(map)
    +answer: Qt.QJSValue <- Qt.QJSValue.property__String(value, "answer")
    +actual: Qt.Int32 <- Qt.QJSValue.toInt(answer)
    require(U32.is_eq(Qt.Int32.word(actual), 42), "QVariant-to-JavaScript conversion changed its map")

def wizard() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +wizard: Qt.QWizard <- Qt.QWizard.new__QWidget(Qt.QWidget{0})
    +page: Qt.QWizardPage <- Qt.QWizardPage.new__QWidget(Qt.QWidget{0})
    Qt.QWizard.setPage(wizard, Qt.Int32{0}, page)
    +edit: Qt.QLineEdit <- Qt.QLineEdit.new__QWidget(Qt.QWizardPage.as_QWidget(page))
    Qt.QWizardPage.registerField__String_QWidget_String_String(page, "name*", Qt.QLineEdit.as_QWidget(edit), "text", "textChanged(QString)")
    complete: Bool <- Qt.QWizardPage.isComplete(page)
    require(Bool.not(complete), "Mandatory wizard field did not start incomplete")
    Qt.QLineEdit.setText(edit, "Bend")
    complete: Bool <- Qt.QWizardPage.isComplete(page)
    require(complete, "Wizard field did not read its exported widget property")
    value: Qt.QVariant <- Qt.QWizard.field(wizard, "name")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "Bend"), "Wizard field lookup lost its registered value")

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def Card() -> Qt.QtObject:
  Qt.QObject.define("ConvenienceSingletonCard", [title()])

def translation() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +translator: Qt.QTranslator <- Qt.CallbackProbe.contextTranslator()
    installed: Bool <- Qt.QCoreApplication.installTranslator(translator)
    require(installed, "Translation test could not install its translator")
    text: String <- Qt.QPushButton.tr__String("source")
    require(String.eq(text, "QPushButton:source"), "Native tr used an inherited QObject context")
    text: String <- Qt.QtObject.tr(~Card(), "source")
    require(String.eq(text, "ConvenienceSingletonCard:source"), "Schema tr lost the declared class context")
    removed: Bool <- Qt.QCoreApplication.removeTranslator(translator)
    require(removed, "Translation test could not remove its translator")

def singleton() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.QObject <- Qt.Qml.registerSingleton(~Card(), "Bend.ConvenienceSingleton", 1, 0, "Card")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +card: Qt.QtObject.Instance(Card()) <- Qt.QQmlEngine.singletonInstance(~Qt.QtObject.arg(~Card()), engine, "Bend.ConvenienceSingleton", "Card")
    Qt.Property.set(~title(), Qt.QtObject.as_QObject(~Card(), card), "typed")
    +again: Qt.QtObject.Instance(Card()) <- Qt.QQmlEngine.singletonInstance(~Qt.QtObject.arg(~Card()), engine, "Bend.ConvenienceSingleton", "Card")
    +text: String <- Qt.Property.get(~title(), Qt.QtObject.as_QObject(~Card(), again))
    require(String.eq(text, "typed"), "Singleton lookup lost its concrete QObject schema")
    +script: Qt.QJSValue <- Qt.QQmlEngine.singletonInstance(~Qt.QJSValue.arg(), engine, "Bend.ConvenienceSingleton", "Card")
    +field: Qt.QJSValue <- Qt.QJSValue.property__String(script, "title")
    +text: String <- Qt.QJSValue.toString(field)
    require(String.eq(text, "typed"), "QJSValue singleton lookup lost its object")
    wrong: Result<&1, &1, U32 & String, Qt.QPushButton> <- Qt.Action.attempt(Qt.QPushButton, Qt.QQmlEngine.singletonInstance(~Qt.QPushButton.arg(), engine, "Bend.ConvenienceSingleton", "Card"))
    expected(Qt.QPushButton, wrong, 22)

def bounds(values: List<&2, Qt.PairValue<Maybe<&2, Qt.Int64>, Maybe<&2, Qt.Int64>>>) -> Qt.Action(Unit):
  match values:
    case Qt.PairValue{Some{first}, Some{last}} <> Qt.PairValue{Some{start}, None{}} <> Qt.PairValue{None{}, Some{length}} <> Nil{}:
      require(U32.is_eq(Qt.Int64.lo(first), 0) && U32.is_eq(Qt.Int64.lo(last), 5) && U32.is_eq(Qt.Int64.lo(start), 10) && U32.is_eq(Qt.Int64.lo(length), 2), "HTTP optional range bounds changed")
    case _: Qt.Action.fail(Unit, 1, "HTTP range snapshot changed shape")

def range_set(value: Maybe<&2, Qt.QHttpHeaderRangeSet>) -> Qt.Action(Unit):
  match value:
    case Some{value}:
      do Qt.Action<Unit>:
        +ranges: List<&2, Qt.PairValue<Maybe<&2, Qt.Int64>, Maybe<&2, Qt.Int64>>> <- Qt.QHttpHeaderRangeSet.ranges(value)
        bounds(ranges)
    case None{}: Qt.Action.fail(Unit, 1, "HTTP Range header was not parsed")

def http() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +ranges: Qt.QHttpHeaderRangeSet <- Qt.QHttpHeaderRangeSet.fromRanges([Qt.HttpRange.closed(Qt.Int64{0, 0}, Qt.Int64{5, 0}), Qt.HttpRange.from(Qt.Int64{10, 0}), Qt.HttpRange.suffix(Qt.Int64{2, 0})])
    +values: List<&2, Qt.PairValue<Maybe<&2, Qt.Int64>, Maybe<&2, Qt.Int64>>> <- Qt.QHttpHeaderRangeSet.ranges(ranges)
    bounds(values)
    +headers: Qt.QHttpHeaders <- Qt.QHttpHeaders.new()
    Qt.QHttpHeaders.setRangeValues(headers, ranges)
    +value: Maybe<&2, Qt.QHttpHeaderRangeSet> <- Qt.QHttpHeaders.rangeValues(headers)
    range_set(value)
    Qt.QHttpHeaderRangeSet.setRanges(ranges, [Qt.HttpRange.from(Qt.Int64{20, 0})])
    invalid: Result<&1, &1, U32 & String, Qt.QHttpHeaderRangeSet> <- Qt.Action.attempt(Qt.QHttpHeaderRangeSet, Qt.QHttpHeaderRangeSet.fromRanges([Qt.HttpRange.closed(Qt.Int64{9, 0}, Qt.Int64{2, 0})]))
    expected(Qt.QHttpHeaderRangeSet, invalid, 22)

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

def ExtendedRange() -> Qt.QtObject:
  Qt.QRangeModel.define("ConvenienceExtendedRange", [title()])

def schema_models() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +one: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{1})
    +instance: Qt.QtObject.Instance(ExtendedRange()) <- Qt.QRangeModel.newAs__List_QVariant_QObject(~ExtendedRange(), [one], Qt.QObject{0})
    +model: Qt.QRangeModel = Qt.QtObject.asNativeBase(~ExtendedRange(), instance)
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

def image_models() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes([255, 0, 0, 255])
    +buffer: Qt.ImageBuffer <- Qt.ImageBuffer.fromBytes(bytes)
    +image: Qt.QImage <- Qt.QImage.fromBuffer(buffer, Qt.Int32{1}, Qt.Int32{1}, Qt.QImage.Format.Format_RGBA8888())
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QImage.arg(), image)
    +model: Qt.QRangeModel <- Qt.QRangeModel.fromValues([boxed])
    Qt.QVariant.destroy(boxed)
    Qt.QImage.destroy(image)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.ImageBuffer.destroy(buffer))
    expected(Unit, held, 16)
    +index: Qt.QModelIndex <- Qt.QRangeModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0})
    +value: Qt.QVariant <- Qt.QRangeModel.data__QModelIndex(model, index)
    +restored: Qt.QImage <- Qt.QVariant.toValue(~Qt.QImage.arg(), value)
    +color: Qt.QColor <- Qt.QImage.pixelColor__Int32_Int32(restored, Qt.Int32{0}, Qt.Int32{0})
    +red: Qt.Int32 <- Qt.QColor.red(color)
    require(U32.is_eq(Qt.Int32.word(red), 255), "Model's external image backing expired")
    Qt.QColor.destroy(color)
    Qt.QImage.destroy(restored)
    Qt.QVariant.destroy(value)
    Qt.QModelIndex.destroy(index)
    Qt.QRangeModel.destroy(model)
    Qt.ImageBuffer.destroy(buffer)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, values())
    Qt.scoped(Unit, script())
    Qt.scoped(Unit, wizard())
    Qt.scoped(Unit, singleton())
    Qt.scoped(Unit, translation())
    Qt.scoped(Unit, http())
    Qt.scoped(Unit, basic_models())
    Qt.scoped(Unit, schema_models())
    Qt.scoped(Unit, replacements())
    Qt.scoped(Unit, metadata_models())
    Qt.scoped(Unit, image_models())
    +objects: U32 <- Qt.Runtime.liveObjects()
    +retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Convenience value origins leaked")
    Qt.Action.lift(Unit, IO.print("QT612_CONVENIENCE_APIS_OK directory=1 fontTags=1 singleton=1 script=1 http=1 flat=1 table=1 nativeEditing=1 qmlEditing=1 cellReplacement=1 staleIsolation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
