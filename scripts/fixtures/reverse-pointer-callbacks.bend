import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected reverse pointer callback failure")

def text(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{value}: require(String.eq(value, expected), "A native C-string callback input changed")
    case None{}: Qt.Action.fail(Unit, 1, "A native C-string callback input became null")

def absent(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{value}: Qt.Action.fail(Unit, 1, "A null native C-string became an empty string")

def translated(state: Unit, context: Maybe<&2, String>, source: Maybe<&2, String>, disambiguation: Maybe<&2, String>, n: Qt.Int32) -> Qt.Action(String):
  do Qt.Action<String>:
    text(context, "BendContext")
    text(source, "native λ")
    absent(disambiguation)
    require(U32.is_eq(Qt.Int32.word(n), 4294967295), "A translator callback lost its plural default")
    return "translated λ"

def refused_translation(state: Unit, context: Maybe<&2, String>, source: Maybe<&2, String>, disambiguation: Maybe<&2, String>, n: Qt.Int32) -> Qt.Action(String):
  Qt.Action.fail(String, 79, "Expected translator callback failure")

def optional_real(input: Maybe<&2, Qt.F64>, value: Qt.F64) -> Maybe<&2, Qt.F64>:
  match input:
    case Some{old}: Some{value}
    case None{}: None{}

def margins(state: Unit, left: Maybe<&2, Qt.F64>, top: Maybe<&2, Qt.F64>, right: Maybe<&2, Qt.F64>, bottom: Maybe<&2, Qt.F64>) -> Qt.Action(Qt.CallbackReply_Optional_F64_Optional_F64_Optional_F64_Optional_F64):
  Qt.Action.pure(Qt.CallbackReply_Optional_F64_Optional_F64_Optional_F64_Optional_F64,
    Qt.CallbackReply_Optional_F64_Optional_F64_Optional_F64_Optional_F64{
      optional_real(left, Qt.F64{0, 1072693248}), optional_real(top, Qt.F64{0, 1073741824}),
      optional_real(right, Qt.F64{0, 1074266112}), optional_real(bottom, Qt.F64{0, 1074790400})})

def line_values(values: List<&2, Qt.QLine>) -> Qt.Action(Unit):
  match values:
    case first <> second <> Nil{}:
      do Qt.Action<Unit>:
        x: Qt.Int32 <- Qt.QLine.x1(first)
        y: Qt.Int32 <- Qt.QLine.y2(second)
        require(U32.is_eq(Qt.Int32.word(x), 1) && U32.is_eq(Qt.Int32.word(y), 8), "A native array callback changed its copied elements")
    case _: Qt.Action.fail(Unit, 1, "A native array callback lost its extent")

def lines(state: Qt.QObject, values: List<&2, Qt.QLine>, count: Qt.Int32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.Int32.word(count), 2), "An audited native array count was not restored")
    line_values(values)
    Qt.QObject.setObjectName(state, "lines")

def optional_error(input: Maybe<&2, Qt.QGeoServiceProvider.Error>) -> Maybe<&2, Qt.QGeoServiceProvider.Error>:
  match input:
    case Some{old}: Some{Qt.QGeoServiceProvider.Error.NotSupportedError()}
    case None{}: None{}

def optional_text(input: Maybe<&2, String>) -> Maybe<&2, String>:
  match input:
    case Some{old}: Some{"Bend provider error"}
    case None{}: None{}

def geocoding(state: Unit, parameters: List<&2, Qt.PairValue<String, Qt.QVariant>>, error: Maybe<&2, Qt.QGeoServiceProvider.Error>, message: Maybe<&2, String>) -> Qt.Action(Qt.CallbackReply_Owned_QGeoCodingManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String):
  Qt.Action.pure(Qt.CallbackReply_Owned_QGeoCodingManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String,
    Qt.CallbackReply_Owned_QGeoCodingManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String{Qt.QGeoCodingManagerEngine{0}, optional_error(error), optional_text(message)})

def places(state: Unit, parameters: List<&2, Qt.PairValue<String, Qt.QVariant>>, error: Maybe<&2, Qt.QGeoServiceProvider.Error>, message: Maybe<&2, String>) -> Qt.Action(Qt.CallbackReply_Owned_QPlaceManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String):
  Qt.Action.pure(Qt.CallbackReply_Owned_QPlaceManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String,
    Qt.CallbackReply_Owned_QPlaceManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String{Qt.QPlaceManagerEngine{0}, optional_error(error), optional_text(message)})

def routing(state: Unit, parameters: List<&2, Qt.PairValue<String, Qt.QVariant>>, error: Maybe<&2, Qt.QGeoServiceProvider.Error>, message: Maybe<&2, String>) -> Qt.Action(Qt.CallbackReply_Owned_QGeoRoutingManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String):
  Qt.Action.pure(Qt.CallbackReply_Owned_QGeoRoutingManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String,
    Qt.CallbackReply_Owned_QGeoRoutingManagerEngine_Optional_QGeoServiceProvider_Error_Optional_String{Qt.QGeoRoutingManagerEngine{0}, optional_error(error), optional_text(message)})

def prompt(state: Unit, origin: Qt.QUrl, message: String, default: String, result: Maybe<&2, String>) -> Qt.Action(Qt.CallbackReply_Bool_Optional_String):
  Qt.Action.pure(Qt.CallbackReply_Bool_Optional_String, Qt.CallbackReply_Bool_Optional_String{True{}, Some{"Bend answer"}})

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +translator: Qt.QTranslator <- Qt.QTranslator.newOverride()
    Qt.QTranslator.Virtual.translate.handle(~Unit, ~translated, translator, Unit{})
    value: String <- Qt.QTranslator.translate__String_String(translator, "BendContext", "native λ")
    require(String.eq(value, "translated λ"), "The native translator did not return Bend's answer")
    Qt.QTranslator.Virtual.translate.handle(~Unit, ~refused_translation, translator, Unit{})
    failed: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTranslator.translate__String_String(translator, "BendContext", "native λ"))
    expected(String, failed, 79)
    +widget: Qt.QGraphicsWidget <- Qt.QGraphicsWidget.newOverride()
    Qt.QGraphicsLayoutItem.Virtual.getContentsMargins.handle(~Unit, ~margins, Qt.QGraphicsWidget.as_QGraphicsLayoutItem(widget), Unit{})
    ok: Bool <- Qt.CallbackProbe.layoutMargins(Qt.QGraphicsWidget.as_QGraphicsLayoutItem(widget))
    require(ok, "Native optional margin outputs were not committed")
    +engine: Qt.QPaintEngine <- Qt.QPaintEngine.newOverride()
    +probe: Qt.QObject <- Qt.QObject.new()
    Qt.QPaintEngine.Virtual.drawLines__List_QLine_Int32.handle(~Qt.QObject, ~lines, engine, probe)
    Qt.CallbackProbe.paintLines(engine, False{})
    Qt.CallbackProbe.paintLines(engine, True{})
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "lines"), "Native drawing array callbacks did not run")
    +factory: Qt.QGeoServiceProviderFactory <- Qt.QGeoServiceProviderFactory.newOverride()
    Qt.QGeoServiceProviderFactory.Virtual.createGeocodingManagerEngine.handle(~Unit, ~geocoding, factory, Unit{})
    Qt.QGeoServiceProviderFactory.Virtual.createPlaceManagerEngine.handle(~Unit, ~places, factory, Unit{})
    Qt.QGeoServiceProviderFactory.Virtual.createRoutingManagerEngine.handle(~Unit, ~routing, factory, Unit{})
    ok: Bool <- Qt.CallbackProbe.geoFactoryOutputs(factory)
    require(ok, "Native Geo service factory outputs were lost")
    +page: Qt.QWebEnginePage <- Qt.QWebEnginePage.newOverride()
    Qt.QWebEnginePage.Virtual.javaScriptPrompt.handle(~Unit, ~prompt, page, Unit{})
    ok: Bool <- Qt.CallbackProbe.javascriptPrompt(page)
    require(ok, "Native JavaScript prompt lost its string output")

def run() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, checks())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Reverse pointer callback resources leaked")
    Qt.Action.lift(Unit, IO.print("QT612_REVERSE_POINTER_CALLBACKS_OK cstrings=1 margins=1 arrays=1 worker=1 enum_outputs=1 prompt=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, run()))
