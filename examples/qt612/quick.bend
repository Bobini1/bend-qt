import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def qml() -> String:
  "import QtQuick\nWindow { id: root; width: 480; height: 280; visible: false; color: '#101827'; title: 'Bend + Qt Quick'; property real precise: 1.0000000000000002; Rectangle { anchors.centerIn: parent; width: 400; height: 190; radius: 24; color: '#203b54'; Text { anchors.centerIn: parent; text: 'Bend + Qt Quick\\nZażółć 🎵'; color: '#8ee3cf'; font.pixelSize: 28; horizontalAlignment: Text.AlignHCenter } } Timer { interval: 120; running: root.visible; onTriggered: root.title = 'QML → Bend: Zażółć 🎵' } }"

def same_bits(+left: Qt.F64, +right: Qt.F64) -> Bool:
  U32.is_eq(Qt.F64.lo(left), Qt.F64.lo(right)) && U32.is_eq(Qt.F64.hi(left), Qt.F64.hi(right))

def write_real(+root: Qt.QObject, +expected: Qt.F64, variant: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    written: Bool <- Qt.QQmlProperty.write__QObject_String_QVariant(root, "precise", variant)
    require(written, "QML property write failed")
    actual: Qt.F64 <- Qt.QVariant.with(Qt.F64, Qt.QQmlProperty.read__QObject_String(root, "precise"), Qt.QVariant.toF64)
    require(same_bits(expected, actual), "qreal lost precision through QVariant/QML")

def inspect_pixel(+color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    red: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    blue: Qt.Int32 <- Qt.QColor.blue(color)
    require(U32.is_eq(Qt.Int32.word(red), 16) && U32.is_eq(Qt.Int32.word(green), 24) && U32.is_eq(Qt.Int32.word(blue), 39), "Quick did not render the expected background")

def inspect_image(+image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QImage.width(image)
    height: Qt.Int32 <- Qt.QImage.height(image)
    require(U32.is_eq(Qt.Int32.word(width), 480) && U32.is_eq(Qt.Int32.word(height), 280), "Quick grab has wrong dimensions")
    Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0}), color => inspect_pixel(color))

# The QML timer changes the title inside the event loop. The handler records
# the title and ends the loop.
def title_changed(probe: Qt.QObject, title: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setObjectName(probe, title)
    Qt.QCoreApplication.exit__Int32(Qt.Int32{9})

def show_window(+window: Qt.QQuickWindow, +probe: Qt.QObject, titles: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.show(window)
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(code), 9), "The title handler did not end the event loop")
    title: String <- Qt.QObject.objectName(probe)
    require(String.eq(title, "QML → Bend: Zażółć 🎵"), "QML signal payload did not reach Bend")
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), image => inspect_image(image))
    Qt.QQuickWindow.hide(window)

def watch_title(+window: Qt.QQuickWindow, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QQuickWindow.connect_windowTitleChanged(~Qt.QObject, ~title_changed, window, probe),
    titles => show_window(window, probe, titles))

def root_demo(+root: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    initial: Qt.F64 <- Qt.QVariant.with(Qt.F64, Qt.QQmlProperty.read__QObject_String(root, "precise"), Qt.QVariant.toF64)
    require(same_bits(initial, Qt.F64{1, 1072693248}), "QML real was narrowed to F32")
    +value: Qt.F64 <- Qt.F64.fromString("1.2345678901234567")
    Qt.QVariant.with(Unit, Qt.QVariant.fromF64(value), variant => write_real(root, value, variant))
    +window: Qt.QQuickWindow <- Qt.QQuickWindow.cast(root)
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => watch_title(window, probe))

def load_data(+component: Qt.QQmlComponent, data: Qt.QByteArray, url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML component failed to load")
    Qt.QObject.with(Unit, Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0}), root => root_demo(root))

def component_demo(+component: Qt.QQmlComponent) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8(qml()), data => Qt.QUrl.with(Unit, Qt.QUrl.new(), url => load_data(component, data, url)))

def engine_demo(engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQmlComponent.with(Unit, Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0}), component => component_demo(component))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), engine_demo)
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "QML scoped cleanup leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_QUICK_OK qml=1 rendered_pixels=1 unicode_signal=1 qreal64=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
