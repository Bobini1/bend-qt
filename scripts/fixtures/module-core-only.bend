import Base
import ../../packages/qt612/qt.bend as Qt

def core() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.new()
    Qt.QObject.setObjectName(object, "Core-only consumer")
    name: String <- Qt.QObject.objectName(object)
    Qt.Action.lift(Unit, IO.print(name))

def main() -> IO(Unit):
  do IO<Unit>:
    IO.try(Unit, Qt.run(Unit, core()))
    maps: String <- Qt.Runtime.loadedLibraries()
    IO.print(maps)
    IO.print("QT_MODULE_CORE_ONLY_OK")
