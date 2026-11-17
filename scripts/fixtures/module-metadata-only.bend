import Base
import ../../packages/qt612/qt.bend as Qt

def points() -> Qt.Property:
  Qt.Property.define("points", Qt.list(Qt.DataVisualization.QScatterDataItem.arg()))

def changed() -> Qt.Signal:
  Qt.Signal.define("changed", [Qt.DataVisualization.QScatterDataItem.arg()])

def Holder() -> Qt.ObjectType:
  Qt.ObjectType.withSignals(Qt.QObject.define("MetadataOnlyHolder", [points()]), [changed()])

def create() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    holder: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    return Unit{}

def main() -> IO(Unit):
  do IO<Unit>:
    IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => create())))
    maps: String <- Qt.Runtime.loadedLibraries()
    IO.print(maps)
    IO.print("QT_MODULE_METADATA_ONLY_OK")
