import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Qt takes the new device; the error text is an output argument.
def create_device(state: Unit, name: String, error: Maybe<&2, String>) -> Qt.Action(Qt.CallbackReply_Owned_QCanBusDevice_Optional_String):
  do Qt.Action<Qt.CallbackReply_Owned_QCanBusDevice_Optional_String>:
    device: Qt.QCanBusDevice <- Qt.QCanBusDevice.newOverride()
    return Qt.CallbackReply_Owned_QCanBusDevice_Optional_String{device, Some{"created"}}

def available_devices(state: Unit, error: Maybe<&2, String>) -> Qt.Action(Qt.CallbackReply_List_QCanBusDeviceInfo_Optional_String):
  Qt.Action.pure(Qt.CallbackReply_List_QCanBusDeviceInfo_Optional_String, Qt.CallbackReply_List_QCanBusDeviceInfo_Optional_String{Nil{}, Some{"queried"}})

def evaluate_bool(state: Unit, id: Qt.Int32, ok: Maybe<&2, Bool>) -> Qt.Action(Qt.CallbackReply_Bool_Optional_Bool):
  Qt.Action.pure(Qt.CallbackReply_Bool_Optional_Bool, Qt.CallbackReply_Bool_Optional_Bool{True{}, Some{True{}}})

def evaluate_string(state: Unit, id: Qt.Int32, ok: Maybe<&2, Bool>) -> Qt.Action(Qt.CallbackReply_String_Optional_Bool):
  Qt.Action.pure(Qt.CallbackReply_String_Optional_Bool, Qt.CallbackReply_String_Optional_Bool{"answer", Some{True{}}})

def load(state: Unit, name: String, base: String, errors: Maybe<&2, List<&2, String>>) -> Qt.Action(Qt.CallbackReply_QByteArray_Optional_List_String):
  do Qt.Action<Qt.CallbackReply_QByteArray_Optional_List_String>:
    bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes(111 <> 107 <> Nil{})
    return Qt.CallbackReply_QByteArray_Optional_List_String{bytes, Some{"diagnostic" <> Nil{}}}

def simplify(state: Unit, widgets: Maybe<&2, List<&2, Qt.QWidget>>) -> Qt.Action(Qt.CallbackReply_CallbackResult_Optional_List_QWidget):
  match widgets:
    case Some{first <> second <> Nil{}}:
      Qt.Action.pure(Qt.CallbackReply_CallbackResult_Optional_List_QWidget, Qt.CallbackReply_CallbackResult_Optional_List_QWidget{Some{second <> Nil{}}})
    case _: Qt.Action.fail(Qt.CallbackReply_CallbackResult_Optional_List_QWidget, 22, "Wrong mutable Designer widget list")

def factory_demo(+factory: Qt.QCanBusFactory) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCanBusFactory.Virtual.createDevice.handle(~Unit, ~create_device, factory, Unit{})
    Qt.QCanBusFactory.Virtual.availableDevices.handle(~Unit, ~available_devices, factory, Unit{})
    valid: U32 <- Qt.CallbackProbe.canFactory(factory)
    require(U32.is_eq(valid, 1), "CAN factory ownership or error outputs failed")

def model_demo(+model: Qt.QScxmlDataModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QScxmlDataModel.Virtual.evaluateToBool.handle(~Unit, ~evaluate_bool, model, Unit{})
    Qt.QScxmlDataModel.Virtual.evaluateToString.handle(~Unit, ~evaluate_string, model, Unit{})
    valid: U32 <- Qt.CallbackProbe.scxmlModel(model)
    require(U32.is_eq(valid, 1), "SCXML success outputs failed")

def loader_demo(+loader: Qt.QScxmlCompiler.Loader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QScxmlCompiler.Loader.Virtual.load.handle(~Unit, ~load, loader, Unit{})
    valid: U32 <- Qt.CallbackProbe.scxmlLoader(loader)
    require(U32.is_eq(valid, 1), "The SCXML loader container output failed")

# The probe makes the form and deletes it after the call.
def designer_demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +form: Qt.QDesignerFormWindowInterface <- Qt.CallbackProbe.newDesignerForm()
    Qt.QDesignerFormWindowInterface.Virtual.simplifySelection.handle(~Unit, ~simplify, form, Unit{})
    valid: U32 <- Qt.CallbackProbe.designerSelection(form)
    require(U32.is_eq(valid, 1), "The Designer mutable widget list output failed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCanBusFactory.with(Unit, Qt.QCanBusFactory.newOverride(), factory => factory_demo(factory))
    Qt.QScxmlDataModel.with(Unit, Qt.QScxmlDataModel.newOverride(), model => model_demo(model))
    Qt.QScxmlCompiler.Loader.with(Unit, Qt.QScxmlCompiler.Loader.newOverride(), loader => loader_demo(loader))
    designer_demo()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Module handlers leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_MODULE_CALLBACKS_OK can_factory=1 native_ownership=1 string_outputs=1 bool_outputs=1 container_outputs=1 pointer_list_outputs=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
