import Base
import ../../packages/qt612/qt.bend as Qt

# The maintainer test resolves these operations from the actual package.
# Ordinary examples use only public typed functions.
def raw_bytes(value: Qt.Wire) -> Qt.Action(U32):
  Qt.@BYTE_RAW@(@BYTE_OPERATION@, 0, value)

def raw_pairs(query: Qt.QUrlQuery, value: Qt.Wire) -> Qt.Action(Unit):
  Qt.@PAIR_RAW@(@PAIR_OPERATION@, Qt.QUrlQuery.word(query), value)

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong raw codec error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Malformed wire payload was accepted")

def byte_result(values: List<&2, U32>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}: require(U32.is_eq(value, 65), "Resolved raw byte operation returned wrong data")
    case _: Qt.Action.fail(Unit, 1, "Resolved raw byte operation returned wrong length")

def bytes(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    byte_result(result)

def byte_controls() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: U32 <- raw_bytes(Qt.WireSequence{Qt.WireScalar{65, 0} <> Nil{}})
    Qt.QByteArray.with(Unit, Qt.Action.pure(Qt.QByteArray, Qt.QByteArray{accepted}), bytes)
    malformed: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, raw_bytes(Qt.WireText{"wrong shape"}))
    expect_error(U32, malformed)
    malformed_item: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, raw_bytes(Qt.WireSequence{Qt.WireScalar{0, 0} <> Qt.WireText{"wrong element"} <> Nil{}}))
    expect_error(U32, malformed_item)

def pairs_result(items: List<&2, Qt.PairValue<String, String>>) -> Qt.Action(Unit):
  match items:
    case Qt.PairValue{key, value} <> Nil{}:
      require(String.eq(key, "key") && String.eq(value, "saved"), "Malformed pair mutated native query items")
    case _: Qt.Action.fail(Unit, 1, "Resolved raw query operation returned wrong pair count")

def pairs(+query: Qt.QUrlQuery) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    raw_pairs(query, Qt.WireSequence{Qt.WireSequence{Qt.WireText{"key"} <> Qt.WireText{"saved"} <> Nil{}} <> Nil{}})
    malformed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, raw_pairs(query, Qt.WireSequence{Qt.WireSequence{Qt.WireText{"a"} <> Qt.WireText{"b"} <> Qt.WireText{"c"} <> Nil{}} <> Nil{}}))
    expect_error(Unit, malformed)
    result: List<&2, Qt.PairValue<String, String>> <- Qt.QUrlQuery.queryItems__QUrl_ComponentFormattingOption(query, Qt.QUrl.ComponentFormattingOption.PrettyDecoded())
    pairs_result(result)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    byte_controls()
    Qt.QUrlQuery.with(Unit, Qt.QUrlQuery.new(), query => pairs(query))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Raw codec controls leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_RAW_CODECS_OK bytes_shape=1 bytes_element=1 pair_shape=1 valid_raw=1 unchanged=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
