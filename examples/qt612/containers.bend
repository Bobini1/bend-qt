import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected conversion failure")

def strings_result(items: List<&2, String>) -> Qt.Action(Unit):
  match items:
    case a <> b <> c <> Nil{}:
      require(String.eq(a, "Zażółć 🎵") && String.eq(b, "") && String.eq(c, "Zażółć 🎵"), "String list lost order or Unicode")
    case _: Qt.Action.fail(Unit, 1, "Wrong string list length")

def strings(+model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +items: List<&2, String> = "Zażółć 🎵" <> "" <> "Zażółć 🎵" <> Nil{}
    Qt.QStringListModel.setStringList(model, items)
    strings_result(items)
    result: List<&2, String> <- Qt.QStringListModel.stringList(model)
    strings_result(result)
    Qt.QStringListModel.setStringList(model, Nil{})
    empty: List<&2, String> <- Qt.QStringListModel.stringList(model)
    require(List.is_empty(&2, String, empty), "Empty list did not round trip")

def pairs_result(items: List<&2, Qt.PairValue<String, String>>) -> Qt.Action(Unit):
  match items:
    case Qt.PairValue{a, b} <> Qt.PairValue{c, d} <> Nil{}:
      require(String.eq(a, "key") && String.eq(b, "🎵") && String.eq(c, "key") && String.eq(d, "second"), "Nested pairs lost order or duplicates")
    case _: Qt.Action.fail(Unit, 1, "Wrong query pair shape")

def pairs(+query: Qt.QUrlQuery) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QUrlQuery.setQueryItems(query, Qt.PairValue{"key", "🎵"} <> Qt.PairValue{"key", "second"} <> Nil{})
    result: List<&2, Qt.PairValue<String, String>> <- Qt.QUrlQuery.queryItems__Flags_QUrl__ComponentFormattingOption(query, Qt.Flags_QUrl__ComponentFormattingOption{0})
    pairs_result(result)

def roles_result(items: List<&2, Qt.PairValue<Qt.Int32, Qt.QByteArray>>) -> Qt.Action(Unit):
  match items:
    case Qt.PairValue{key, value} <> Nil{}:
      do Qt.Action<Unit>:
        text: String <- Qt.QByteArray.utf8(value)
        require(U32.is_eq(Qt.Int32.word(key), 256) && String.eq(text, "音符"), "Hash conversion failed")
    case _: Qt.Action.fail(Unit, 1, "Wrong role hash size")

def roles_value(+model: Qt.QStandardItemModel, value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStandardItemModel.setItemRoleNames(model, Qt.PairValue{Qt.Int32{256}, value} <> Nil{})
    Qt.List_Pair_Int32_QByteArray.with(Unit, Qt.QStandardItemModel.roleNames(model), roles_result)

def roles(model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("音符"), value => roles_value(model, value))

def map_result(items: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(Unit):
  match items:
    case Qt.PairValue{a, first} <> Qt.PairValue{z, second} <> Nil{}:
      do Qt.Action<Unit>:
        x: String <- Qt.QVariant.toString(first)
        y: String <- Qt.QVariant.toString(second)
        require(String.eq(a, "a") && String.eq(z, "z") && String.eq(x, "last") && String.eq(y, "first"), "Map ordering or duplicate replacement failed")
    case _: Qt.Action.fail(Unit, 1, "Wrong unique map shape")

def map_case(map: Qt.QCborMap) -> Qt.Action(Unit):
  Qt.List_Pair_String_QVariant.with(Unit, Qt.QCborMap.toVariantMap(map), map_result)

def map_values(+first: Qt.QVariant, second: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QCborMap.with(Unit, Qt.QCborMap.fromVariantMap(Qt.PairValue{"z", first} <> Qt.PairValue{"a", first} <> Qt.PairValue{"a", second} <> Nil{}), map_case)

def map_first(first: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("last"), second => map_values(first, second))

def multi_result(items: List<&2, Qt.PairValue<Qt.QByteArray, Qt.QByteArray>>) -> Qt.Action(Unit):
  match items:
    case Qt.PairValue{key1, value1} <> Qt.PairValue{key2, value2} <> Nil{}:
      do Qt.Action<Unit>:
        k1: String <- Qt.QByteArray.utf8(key1)
        k2: String <- Qt.QByteArray.utf8(key2)
        +a: String <- Qt.QByteArray.utf8(value1)
        +b: String <- Qt.QByteArray.utf8(value2)
        require(String.eq(k1, "x-score") && String.eq(k2, "x-score"), "Multimap keys changed")
        require((String.eq(a, "first") && String.eq(b, "last")) || (String.eq(a, "last") && String.eq(b, "first")), "Multimap dropped duplicate entries")
    case _: Qt.Action.fail(Unit, 1, "Wrong multimap size")

def multi_headers(+headers: Qt.QHttpHeaders) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.List_Pair_QByteArray_QByteArray.with(Unit, Qt.QHttpHeaders.toMultiMap(headers), multi_result)
    Qt.List_Pair_QByteArray_QByteArray.with(Unit, Qt.QHttpHeaders.toMultiHash(headers), multi_result)

def multi_values(+key: Qt.QByteArray, first: Qt.QByteArray, second: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +items: List<&2, Qt.PairValue<Qt.QByteArray, Qt.QByteArray>> = Qt.PairValue{key, first} <> Qt.PairValue{key, second} <> Nil{}
    Qt.QHttpHeaders.with(Unit, Qt.QHttpHeaders.fromMultiMap(items), headers => multi_headers(headers))
    Qt.QHttpHeaders.with(Unit, Qt.QHttpHeaders.fromMultiHash(items), headers => multi_headers(headers))

def multi_first(+key: Qt.QByteArray, first: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("last"), second => multi_values(key, first, second))

def multi_key(+key: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("first"), first => multi_first(key, first))

def stops_result(items: List<&2, Qt.PairValue<Qt.F64, Qt.QColor>>) -> Qt.Action(Unit):
  match items:
    case Qt.PairValue{position, color} <> Nil{}:
      do Qt.Action<Unit>:
        same: Bool <- Qt.F64.equal(position, Qt.F64{1, 1071644672})
        red: Qt.Int32 <- Qt.QColor.red(color)
        require(same && U32.is_eq(Qt.Int32.word(red), 255), "Nested real/value pair lost precision")
    case _: Qt.Action.fail(Unit, 1, "Wrong gradient stop shape")

def stops_color(+gradient: Qt.QLinearGradient, color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QLinearGradient.setStops(gradient, Qt.PairValue{Qt.F64{1, 1071644672}, color} <> Nil{})
    Qt.List_Pair_F64_QColor.with(Unit, Qt.QLinearGradient.stops(gradient), stops_result)

def stops(gradient: Qt.QLinearGradient) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QColor.new__Int32_Int32_Int32_Int32(Qt.Int32{255}, Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{255}), color => stops_color(gradient, color))

def many(count: Nat, +url: Qt.QUrl) -> List<&2, Qt.QUrl>:
  match count:
    case Zero{}: Nil{}
    case Succ{rest}: url <> many(rest, url)

def urls_result(items: List<&2, Qt.QUrl>) -> Qt.Action(Unit):
  match items:
    case first <> second <> Nil{}:
      do Qt.Action<Unit>:
        a: String <- Qt.QUrl.toString__Flags_QUrl__ComponentFormattingOption(first, Qt.Flags_QUrl__ComponentFormattingOption{0})
        b: String <- Qt.QUrl.toString__Flags_QUrl__ComponentFormattingOption(second, Qt.Flags_QUrl__ComponentFormattingOption{0})
        require(String.eq(a, "https://example.org/score") && String.eq(b, "https://example.org/score"), "Copied URL list failed")
    case _: Qt.Action.fail(Unit, 1, "Wrong URL list size")

def fail_urls(items: List<&2, Qt.QUrl>) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 17, "Container body failed")

def url_count(items: List<&2, Qt.QUrl>) -> U32:
  match items:
    case Nil{}: 0
    case head <> tail: U32.add(1, url_count(tail))

def grown_urls(items: List<&2, Qt.QUrl>) -> Qt.Action(Unit):
  require(U32.is_eq(url_count(items), 4100), "Growing URL conversion returned the wrong size")

def urls_value(+mime: Qt.QMimeData, +url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QMimeData.setUrls(mime, url <> url <> Nil{})
    Qt.List_QUrl.with(Unit, Qt.QMimeData.urls(mime), urls_result)
    baseline: U32 <- Qt.Runtime.liveObjects()
    failed_body: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.List_QUrl.with(Unit, Qt.QMimeData.urls(mime), fail_urls))
    expect_error(Unit, failed_body, 17)
    cleaned: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(baseline, cleaned), "Failed container body bypassed cleanup")
    # Conversion must validate every element before invoking Qt.
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMimeData.setUrls(mime, url <> Qt.QUrl{0} <> Nil{}))
    expect_error(Unit, bad, 116)
    Qt.List_QUrl.with(Unit, Qt.QMimeData.urls(mime), urls_result)
    before: U32 <- Qt.Runtime.liveObjects()
    Qt.QMimeData.setUrls(mime, many(4100n, url))
    Qt.List_QUrl.with(Unit, Qt.QMimeData.urls(mime), grown_urls)
    after: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(before, after), "Growing output conversion leaked value handles")

def urls(mime: Qt.QMimeData) -> Qt.Action(Unit):
  Qt.QUrl.with(Unit, Qt.QUrl.new__String_QUrl_ParsingMode("https://example.org/score", Qt.QUrl.ParsingMode.TolerantMode()), url => urls_value(mime, url))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringListModel.with(Unit, Qt.QStringListModel.new(), model => strings(model))
    Qt.QUrlQuery.with(Unit, Qt.QUrlQuery.new(), query => pairs(query))
    Qt.QStandardItemModel.with(Unit, Qt.QStandardItemModel.new(), roles)
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("first"), map_first)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("x-score"), key => multi_key(key))
    Qt.QLinearGradient.with(Unit, Qt.QLinearGradient.new(), stops)
    Qt.QMimeData.with(Unit, Qt.QMimeData.new(), urls)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Container scopes leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_CONTAINERS_OK strings=1 pairs=1 hash=1 map=1 multimap=1 multihash=1 nested_real=1 values=1 shared_input=1 invalid_element=1 rollback=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
