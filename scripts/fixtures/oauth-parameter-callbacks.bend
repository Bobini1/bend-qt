import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 93), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected OAuth modifier failure")

def modify(state: Unit, stage: Qt.QAbstractOAuth.Stage, values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(List<&2, Qt.PairValue<String, Qt.QVariant>>):
  do Qt.Action<List<&2, Qt.PairValue<String, Qt.QVariant>>>:
    value: Qt.QVariant <- Qt.QVariant.fromString("new")
    return Qt.PairValue{"added", value} <> values

def refused(state: Unit, stage: Qt.QAbstractOAuth.Stage, values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(List<&2, Qt.PairValue<String, Qt.QVariant>>):
  Qt.Action.fail(List<&2, Qt.PairValue<String, Qt.QVariant>>, 93, "Expected OAuth modifier failure")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +flow: Qt.QOAuth2AuthorizationCodeFlow <- Qt.QOAuth2AuthorizationCodeFlow.new()
    +oauth: Qt.QAbstractOAuth = Qt.QOAuth2AuthorizationCodeFlow.as_QAbstractOAuth(flow)
    Qt.QAbstractOAuth.setModifyParametersFunctionWithHandler(~Unit, ~modify, oauth, Unit{})
    ok: Bool <- Qt.CallbackProbe.modifyParameters(oauth)
    require(ok, "The OAuth modifier did not update the native parameter map")
    Qt.QAbstractOAuth.setModifyParametersFunctionWithHandler(~Unit, ~refused, oauth, Unit{})
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.CallbackProbe.modifyParameters(oauth))
    expected(result)
    Qt.QAbstractOAuth.clearModifyParametersFunction(oauth)
    present: Bool <- Qt.CallbackProbe.hasModifyParameters(oauth)
    require(Bool.not(present), "Clearing an OAuth modifier kept its native callable")
    Qt.Action.lift(Unit, IO.print("QT612_OAUTH_PARAMETER_CALLBACKS_OK native_map=1 transactional_failure=93 clear=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => Qt.scoped(Unit, checks()))))
