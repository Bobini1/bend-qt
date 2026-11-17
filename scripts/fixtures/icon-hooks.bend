import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def null_hook(state: Unit, initial: Bool) -> Qt.Action(Bool):
  do Qt.Action<Bool>:
    require(initial, "The hook did not keep its initial bool")
    return False{}

def old_pixmap(+pixmap: Qt.QPixmap) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QPixmap.width(pixmap)
    height: Qt.Int32 <- Qt.QPixmap.height(pixmap)
    require(U32.is_eq(Qt.Int32.word(width), 3), "The initial pixmap width was lost")
    require(U32.is_eq(Qt.Int32.word(height), 5), "The initial pixmap height was lost")

def scaled_reply(+data: Qt.QIconEngine.ScaledPixmapArgument) -> Qt.Action(Qt.QIconEngine.ScaledPixmapArgument):
  do Qt.Action<Qt.QIconEngine.ScaledPixmapArgument>:
    Qt.QPixmap.with(Unit, Qt.QIconEngine.ScaledPixmapArgument.Fields.pixmap(data), pixmap => old_pixmap(pixmap))
    Qt.QPixmap.with(Unit, Qt.QPixmap.new__Int32_Int32(Qt.Int32{11}, Qt.Int32{13}), pixmap => Qt.QIconEngine.ScaledPixmapArgument.Fields.set_pixmap(data, pixmap))
    return data

def scaled_hook(state: Unit, data: Qt.QIconEngine.ScaledPixmapArgument) -> Qt.Action(Qt.QIconEngine.ScaledPixmapArgument):
  scaled_reply(data)

def prepare_data(+data: Qt.QIconEngine.ScaledPixmapArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QIconEngine.ScaledPixmapArgument.Fields.set_mode(data, Qt.QIcon.Mode.Active())
    Qt.QIconEngine.ScaledPixmapArgument.Fields.set_state(data, Qt.QIcon.State.On())
    scale: Qt.F64 <- Qt.F64.fromString("2")
    Qt.QIconEngine.ScaledPixmapArgument.Fields.set_scale(data, scale)
    Qt.QSize.with(Unit, Qt.QSize.new__Int32_Int32(Qt.Int32{7}, Qt.Int32{9}), size => Qt.QIconEngine.ScaledPixmapArgument.Fields.set_size(data, size))
    Qt.QPixmap.with(Unit, Qt.QPixmap.new__Int32_Int32(Qt.Int32{3}, Qt.Int32{5}), pixmap => Qt.QIconEngine.ScaledPixmapArgument.Fields.set_pixmap(data, pixmap))

def new_pixmap(+pixmap: Qt.QPixmap) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QPixmap.width(pixmap)
    height: Qt.Int32 <- Qt.QPixmap.height(pixmap)
    require(U32.is_eq(Qt.Int32.word(width), 11), "The forward hook returned the wrong width")
    require(U32.is_eq(Qt.Int32.word(height), 13), "The forward hook returned the wrong height")

def forward_scaled(engine: Qt.QIconEngine, +data: Qt.QIconEngine.ScaledPixmapArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    prepare_data(data)
    Qt.QIconEngine.ScaledPixmapArgument.with(Unit, Qt.QIconEngine.virtual_hookScaledPixmap(engine, data), result =>
      Qt.QPixmap.with(Unit, Qt.QIconEngine.ScaledPixmapArgument.Fields.pixmap(result), pixmap => new_pixmap(pixmap)))
    Qt.QPixmap.with(Unit, Qt.QIconEngine.ScaledPixmapArgument.Fields.pixmap(data), pixmap => old_pixmap(pixmap))

# A hook without a handler (id 1024 in the probe) runs the C++ base.
def engine_checks(+engine: Qt.QIconEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QIconEngine.Virtual.virtual_hookIsNull.handle(~Unit, ~null_hook, engine, Unit{})
    Qt.QIconEngine.Virtual.virtual_hookScaledPixmap.handle(~Unit, ~scaled_hook, engine, Unit{})
    valid: U32 <- Qt.CallbackProbe.iconHooks(engine)
    require(U32.is_eq(valid, 1), "Native hooks did not round-trip")
    result: Bool <- Qt.QIconEngine.virtual_hookIsNull(engine, True{})
    require(Bool.not(result), "The typed forward hook did not use the native virtual")
    Qt.QIconEngine.ScaledPixmapArgument.with(Unit, Qt.QIconEngine.ScaledPixmapArgument.new(), data => forward_scaled(engine, data))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QIconEngine.with(Unit, Qt.QIconEngine.newOverride(), engine => engine_checks(engine))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Icon hooks leaked native copies")
    Qt.Action.lift(Unit, IO.print("QT612_ICON_HOOKS_OK native_dispatch=1 input_output=1 unknown_fallback=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
