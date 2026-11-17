import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected protected field lifetime rejection")

def member_view() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +decoder: Qt.QStringDecoder <- Qt.QStringDecoder.new__String("UTF-8")
    +state: Qt.QStringConverterBase.State <- Qt.QStringDecoder.Fields.state(decoder)
    +again: Qt.QStringConverterBase.State <- Qt.QStringDecoder.Fields.state(decoder)
    require(U32.is_eq(Qt.QStringConverterBase.State.word(state), Qt.QStringConverterBase.State.word(again)), "A native member view lost its identity")
    Qt.QStringConverterBase.State.Fields.set_invalidChars(state, Qt.Int64{2, 0})
    changed: Bool <- Qt.QStringDecoder.hasError(decoder)
    require(changed, "Mutating the State view did not change its decoder")
    Qt.QStringConverterBase.State.Fields.set_invalidChars(state, Qt.Int64{0, 0})
    Qt.QStringDecoder.destroy(decoder)
    stale: Result<&1, &1, U32 & String, Qt.Int64> <- Qt.Action.attempt(Qt.Int64, Qt.QStringConverterBase.State.Fields.invalidChars(state))
    expected(Qt.Int64, stale, 116)

def painting() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +image: Qt.QImage <- Qt.QImage.new__Int32_Int32_QImage_Format(Qt.Int32{8}, Qt.Int32{8}, Qt.QImage.Format.Format_ARGB32())
    +engine: Qt.QPaintEngine <- Qt.QImage.paintEngine(image)
    empty: Qt.QPaintEngineState <- Qt.QPaintEngine.Fields.state(engine)
    require(U32.is_eq(Qt.QPaintEngineState.word(empty), 0), "An idle raster engine had a painter state")
    +device: Qt.QPaintDevice <- Qt.QImage.as_QPaintDevice(image)
    +painter: Qt.QPainter <- Qt.QPainter.new__QPaintDevice(device)
    +state: Qt.QPaintEngineState <- Qt.QPaintEngine.Fields.state(engine)
    same: Qt.QPaintEngineState <- Qt.QPaintEngine.Fields.state(engine)
    require(U32.is_eq(Qt.QPaintEngineState.word(state), Qt.QPaintEngineState.word(same)), "Repeated state access created different identities")
    active: U32 <- Qt.QPaintEngine.Fields.active(engine)
    require(U32.is_eq(active, 1), "A raster engine's bitfield did not reflect native painting")
    painters: U32 <- Qt.QImage.Fields.painters(image)
    require(U32.is_eq(painters, 1), "A foreign paint device's protected count was incorrect")
    original: Qt.Flags_QPaintEngine__DirtyFlag <- Qt.QPaintEngineState.Fields.dirtyFlags(state)
    Qt.QPaintEngineState.Fields.set_dirtyFlags(state, Qt.Flags_QPaintEngine__DirtyFlag{1})
    current: Qt.Flags_QPaintEngine__DirtyFlag <- Qt.QPaintEngineState.state(state)
    require(U32.is_eq(Qt.Flags_QPaintEngine__DirtyFlag.word(current), 1), "An ordinary protected field missed the actual native state")
    Qt.QPaintEngineState.Fields.set_dirtyFlags(state, original)
    ended: Bool <- Qt.QPainter.end(painter)
    require(ended, "Could not end the native painter")
    stale: Result<&1, &1, U32 & String, Qt.Flags_QPaintEngine__DirtyFlag> <- Qt.Action.attempt(Qt.Flags_QPaintEngine__DirtyFlag, Qt.QPaintEngineState.state(state))
    expected(Qt.Flags_QPaintEngine__DirtyFlag, stale, 116)
    begun: Bool <- Qt.QPainter.begin(painter, device)
    require(begun, "Could not restart the native painter")
    fresh: Qt.QPaintEngineState <- Qt.QPaintEngine.Fields.state(engine)
    require(Bool.not(U32.is_eq(Qt.QPaintEngineState.word(fresh), Qt.QPaintEngineState.word(state))), "A new painting epoch revived an old view")
    finished: Bool <- Qt.QPainter.end(painter)
    require(finished, "Could not finish the second painting epoch")

def foreign_bitfields() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +owner: Qt.QObject <- Qt.CallbackProbe.foreignFields()
    +material: Qt.QSGOpaqueTextureMaterial <- Qt.CallbackProbe.foreignMaterial(owner)
    Qt.QSGOpaqueTextureMaterial.Fields.set_m_filtering(material, 2)
    native: U32 <- Qt.CallbackProbe.materialFiltering(material)
    require(U32.is_eq(native, 2), "A foreign material's actual native filtering did not change")
    Qt.QSGOpaqueTextureMaterial.Fields.set_m_reserved(material, 7)
    reserved: U32 <- Qt.QSGOpaqueTextureMaterial.Fields.m_reserved(material)
    require(U32.is_eq(reserved, 7), "A foreign reserved bitfield lost its value")
    filtering: U32 <- Qt.QSGOpaqueTextureMaterial.Fields.m_filtering(material)
    require(U32.is_eq(filtering, 2), "A bitfield write changed a neighboring field")
    Qt.QObject.destroy(owner)
    stale: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.QSGOpaqueTextureMaterial.Fields.m_filtering(material))
    expected(U32, stale, 116)

def pointer_field() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QWidget <- Qt.QWidget.new()
    +second: Qt.QWidget <- Qt.QWidget.new()
    +item: Qt.QWidgetItem <- Qt.QWidgetItem.new(first)
    Qt.QWidgetItem.Fields.set_wid(item, second)
    selected: Qt.QWidget <- Qt.QWidgetItem.Fields.wid(item)
    require(U32.is_eq(Qt.QWidget.word(selected), Qt.QWidget.word(second)), "A protected QObject pointer field lost its identity")
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(second))
    expected(Unit, held, 16)
    Qt.QWidgetItem.destroy(item)
    Qt.QWidget.destroy(second)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, member_view())
    Qt.scoped(Unit, painting())
    Qt.scoped(Unit, foreign_bitfields())
    Qt.scoped(Unit, pointer_field())
    Qt.Action.lift(Unit, IO.print("QT612_PROTECTED_FIELDS_OK foreign=1 bitfields=1 native_state_view=1 painting_epochs=1 pointer_retention=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
