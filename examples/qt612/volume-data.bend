import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def original(value: List<&2, U32>) -> Bool:
  match value:
    case 1 <> 2 <> 3 <> 4 <> 5 <> 6 <> 7 <> 8 <> Nil{}: True{}
    case _: False{}

def changed(value: List<&2, U32>) -> Bool:
  match value:
    case 1 <> 2 <> 3 <> 4 <> 9 <> 8 <> 7 <> 6 <> Nil{}: True{}
    case _: False{}

def volume(+value: Qt.QCustom3DVolume) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCustom3DVolume.setTextureDimensions(value, Qt.Int32{1}, Qt.Int32{1}, Qt.Int32{2})
    Qt.QCustom3DVolume.setTextureData(value, 1 <> 2 <> 3 <> 4 <> 5 <> 6 <> 7 <> 8 <> Nil{})
    stored: List<&2, U32> <- Qt.QCustom3DVolume.textureData(value)
    require(original(stored), "Volume texture data did not round trip")
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(9 <> 8 <> 7 <> 6 <> Nil{}), bytes =>
      Qt.QCustom3DVolume.setSubTextureData__Qt_Axis_Int32_QByteArray(value, Qt.Qt.Axis.ZAxis(), Qt.Int32{1}, bytes))
    snapshot: List<&2, U32> <- Qt.QCustom3DVolume.textureData(value)
    require(changed(snapshot), "Volume slice did not update the native texture")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCustom3DVolume.with(Unit, Qt.QCustom3DVolume.new(), value => volume(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Volume scopes leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_VOLUME_DATA_OK owning_data=1 slice=1 cleanup=1 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
