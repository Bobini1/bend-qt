import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def retain_model(mapper: Qt.QDataWidgetMapper, +model: Qt.QStringListModel) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    Qt.QStringListModel.setStringList(model, "Retained until application shutdown" <> Nil{})
    Qt.QDataWidgetMapper.setModel(mapper, Qt.QStringListModel.as_QAbstractItemModel(model))
    return model

def mapper_case(mapper: Qt.QDataWidgetMapper) -> Qt.Action(Qt.QStringListModel):
  Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), model => retain_model(mapper, model))

def retain_menu(tray: Qt.QSystemTrayIcon, +menu: Qt.QMenu) -> Qt.Action(Qt.QMenu):
  do Qt.Action<Qt.QMenu>:
    Qt.QMenu.setTitle(menu, "Retained QWidget shutdown")
    Qt.QSystemTrayIcon.setContextMenu(tray, menu)
    return menu

def tray_case(tray: Qt.QSystemTrayIcon) -> Qt.Action(Qt.QMenu):
  Qt.QMenu.with(Qt.QMenu, Qt.QMenu.new(), menu => retain_menu(tray, menu))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +application: Qt.QCoreApplication <- Qt.QCoreApplication.instance()
    # These scopes deliberately leave Qt-owned retainers alive. Their referenced
    # model/menu scopes have ended and their deletion is pending until shutdown.
    model: Qt.QStringListModel <- Qt.QDataWidgetMapper.with(Qt.QStringListModel, Qt.QDataWidgetMapper.new__QObject(Qt.QCoreApplication.as_QObject(application)), mapper_case)
    menu: Qt.QMenu <- Qt.QSystemTrayIcon.with(Qt.QMenu, Qt.QSystemTrayIcon.new__QObject(Qt.QCoreApplication.as_QObject(application)), tray_case)
    strings: List<&2, String> <- Qt.QStringListModel.stringList(model)
    title: String <- Qt.QMenu.title(menu)
    require(String.eq(title, "Retained QWidget shutdown"), "Pending menu was destroyed prematurely")
    edges: U32 <- Qt.Runtime.liveRetentions()
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(edges, 2) && U32.is_eq(objects, 5) && U32.is_eq(connections, 0), "Unexpected shutdown fixture registry state")
    # The harness enables BEND_QT_CHECK_SHUTDOWN and requires its native
    # QT612_SHUTDOWN_OK marker, emitted only after QApplication destruction.
    Qt.Action.lift(Unit, IO.print("QT612_SHUTDOWN_RETENTION_READY pending_targets=2 qt_owned_retainers=2"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
