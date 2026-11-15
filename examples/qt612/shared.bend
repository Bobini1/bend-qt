import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong shared-pointer error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected shared-pointer lifetime failure")

def image(+value: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QImage.width(value)
    height: Qt.Int32 <- Qt.QImage.height(value)
    require(U32.is_eq(Qt.Int32.word(width), 32) && U32.is_eq(Qt.Int32.word(height), 24), "Shared grab result lost its image")

def finished(code: U32) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

def ready_state(empty: Bool, result: Qt.QQuickItemGrabResult) -> Qt.Action(Unit):
  match empty:
    case False{}: Qt.QImage.with(Unit, Qt.QQuickItemGrabResult.image(result), value => image(value))
    case True{}:
      do Qt.Action<Unit>:
        # The grab completes while the event loop renders the window.
        code: Qt.Int32 <- Qt.QCoreApplication.exec()
        require(U32.is_eq(Qt.Int32.word(code), 5), "The ready handler did not end the event loop")
        Qt.QImage.with(Unit, Qt.QQuickItemGrabResult.image(result), value => image(value))

def ready(+result: Qt.QQuickItemGrabResult, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # Qt emits ready only from its event loop, which has not run since the
    # grab started, so connecting first cannot miss it.
    empty: Bool <- Qt.QImage.with(Bool, Qt.QQuickItemGrabResult.image(result), Qt.QImage.isNull)
    ready_state(empty, result)

def clone_lifetime(+source: Qt.Shared_QQuickItemGrabResult, +clone: Qt.Shared_QQuickItemGrabResult) -> Qt.Action(Qt.QQuickItemGrabResult):
  do Qt.Action<Qt.QQuickItemGrabResult>:
    first: Qt.QQuickItemGrabResult <- Qt.Shared_QQuickItemGrabResult.data(source)
    +second: Qt.QQuickItemGrabResult <- Qt.Shared_QQuickItemGrabResult.data(clone)
    require(U32.is_eq(Qt.QQuickItemGrabResult.word(first), Qt.QQuickItemGrabResult.word(second)), "Shared holder copies changed pointee identity")
    Qt.Shared_QQuickItemGrabResult.destroy(source)
    forbidden: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQuickItemGrabResult.destroy(second))
    expect_error(Unit, forbidden, 1)
    adoption: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQuickItemGrabResult.setParent(second, Qt.QObject{0}))
    expect_error(Unit, adoption, 1)
    Qt.Connection.with(Unit, Qt.QQuickItemGrabResult.connect_ready(~U32, ~finished, second, 5), connection => ready(second, connection))
    return second

def holder(+value: Qt.Shared_QQuickItemGrabResult) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    empty: Bool <- Qt.Shared_QQuickItemGrabResult.isNull(value)
    require(Bool.not(empty), "Qt did not create a shared grab result")
    stale: Qt.QQuickItemGrabResult <- Qt.Shared_QQuickItemGrabResult.with(Qt.QQuickItemGrabResult, Qt.Shared_QQuickItemGrabResult.clone(value), clone => clone_lifetime(value, clone))
    gone: Result<&1, &1, U32 & String, Qt.QImage> <- Qt.Action.attempt(Qt.QImage, Qt.QQuickItemGrabResult.image(stale))
    expect_error(Qt.QImage, gone, 116)

def size(item: Qt.QQuickItem, value: Qt.QSize) -> Qt.Action(Unit):
  Qt.Shared_QQuickItemGrabResult.with(Unit, Qt.QQuickItem.grabToImage__QSize(item, value), shared => holder(shared))

def window(+value: Qt.QQuickWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.resize__Int32_Int32(value, Qt.Int32{32}, Qt.Int32{24})
    Qt.QQuickWindow.show(value)
    Qt.QCoreApplication.processEvents()
    item: Qt.QQuickItem <- Qt.QQuickWindow.contentItem(value)
    Qt.QSize.with(Unit, Qt.QSize.new__Int32_Int32(Qt.Int32{32}, Qt.Int32{24}), dimensions => size(item, dimensions))
    Qt.QQuickWindow.hide(value)

def empty_holder(value: Qt.Shared_QQuickItemGrabResult) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    empty: Bool <- Qt.Shared_QQuickItemGrabResult.isNull(value)
    require(empty, "Default shared holder should be empty")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Shared_QQuickItemGrabResult.with(Unit, Qt.Shared_QQuickItemGrabResult.new(), empty_holder)
    Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), value => window(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Shared-pointer scopes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_SHARED_OK control_block=1 clone=1 identity=1 last_holder=1 transfer_rejected=1 quick_image=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
