import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def range_error(result: Result<&1, &1, U32 & String, Qt.Outputs_Bool_Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An NMEA parser accepted a byte count beyond its owned input")

def parsed(value: Qt.Outputs_Bool_Bool) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Bool_Bool{parsed, fixed}:
      require(parsed && fixed, "Native NMEA position outputs were lost")

def identifiers(values: List<&2, Qt.Int32>) -> Qt.Action(Unit):
  match values:
    case a <> b <> c <> d <> e <> f <> g <> h <> Nil{}:
      require(U32.is_eq(Qt.Int32.word(a), 4) && U32.is_eq(Qt.Int32.word(h), 31), "NMEA satellite-in-use values changed")
    case _: Qt.Action.fail(Unit, 1, "NMEA satellite-in-use output list was lost")

def satellites(values: List<&2, Qt.QGeoSatelliteInfo>) -> Qt.Action(Unit):
  match values:
    case first <> second <> third <> fourth <> Nil{}:
      do Qt.Action<Unit>:
        id: Qt.Int32 <- Qt.QGeoSatelliteInfo.satelliteIdentifier(first)
        require(U32.is_eq(Qt.Int32.word(id), 1), "NMEA satellite output changed its native identifier")
    case _: Qt.Action.fail(Unit, 1, "NMEA satellite output list was lost")

def satellite_result(value: Qt.Outputs_QNmeaSatelliteInfoSource_SatelliteInfoParseStatus_List_QGeoSatelliteInfo_QGeoSatelliteInfo_SatelliteSystem) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QNmeaSatelliteInfoSource_SatelliteInfoParseStatus_List_QGeoSatelliteInfo_QGeoSatelliteInfo_SatelliteSystem{status, values, system}:
      do Qt.Action<Unit>:
        require(U32.is_eq(Qt.QNmeaSatelliteInfoSource.SatelliteInfoParseStatus.word(status), 2), "Native NMEA parse status changed")
        require(U32.is_eq(Qt.QGeoSatelliteInfo.SatelliteSystem.word(system), 1), "Native NMEA satellite system output was lost")
        satellites(values)

def in_use_result(value: Qt.Outputs_QGeoSatelliteInfo_SatelliteSystem_List_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QGeoSatelliteInfo_SatelliteSystem_List_Int32{system, values}:
      do Qt.Action<Unit>:
        require(U32.is_eq(Qt.QGeoSatelliteInfo.SatelliteSystem.word(system), 1), "Native NMEA satellite system changed")
        identifiers(values)

def style_options() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +view: Qt.QListView <- Qt.QListView.new()
    +option: Qt.QStyleOptionViewItem <- Qt.QStyleOptionViewItem.new()
    Qt.QListView.initViewItemOption(view, option)
    +widget: Qt.QWidget <- Qt.QStyleOptionViewItem.Fields.widget(option)
    require(U32.is_eq(Qt.QWidget.word(widget), Qt.QListView.word(view)), "Style initialization lost its widget field")
    Qt.QListView.release(view)
    Qt.QWidget.setObjectName(widget, "retained view")
    name: String <- Qt.QWidget.objectName(widget)
    require(String.eq(name, "retained view"), "A native output pointer lost its aggregate dependency")
    +model: Qt.QStringListModel <- Qt.QStringListModel.new__List_String(["native text"])
    +index: Qt.QModelIndex <- Qt.QStringListModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0})
    +delegate: Qt.QStyledItemDelegate <- Qt.QStyledItemDelegate.new()
    Qt.QStyledItemDelegate.initStyleOption(delegate, option, index)
    text: String <- Qt.QStyleOptionViewItem.Fields.text(option)
    require(String.eq(text, "native text"), "Delegate initialization did not update the supplied option")

def graphics_outputs() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +offset: Qt.QPoint <- Qt.QPoint.new__Int32_Int32(Qt.Int32{5}, Qt.Int32{6})
    +effect: Qt.QGraphicsDropShadowEffect <- Qt.QGraphicsDropShadowEffect.new()
    +pixmap: Qt.QPixmap <- Qt.QGraphicsDropShadowEffect.sourcePixmap__Qt_CoordinateSystem_QPoint_QGraphicsEffect_PixmapPadMode(
      effect, Qt.Qt.CoordinateSystem.LogicalCoordinates(), offset, Qt.QGraphicsEffect.PixmapPadMode.NoPad())
    empty: Bool <- Qt.QPixmap.isNull(pixmap)
    require(empty, "An unattached graphics effect unexpectedly had a source")
    +image: Qt.QImage <- Qt.QImage.new()
    redirected: Qt.QPaintDevice <- Qt.QImage.redirected(image, offset)
    require(U32.is_eq(Qt.QPaintDevice.word(redirected), 0), "QImage unexpectedly redirected its paint device")
    x: Qt.Int32 <- Qt.QPoint.x(offset)
    y: Qt.Int32 <- Qt.QPoint.y(offset)
    require(U32.is_eq(Qt.Int32.word(x), 5) && U32.is_eq(Qt.Int32.word(y), 6), "Optional native output storage was damaged")

def modbus() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +client: Qt.QModbusTcpClient <- Qt.QModbusTcpClient.new()
    +bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes([2, 0, 42])
    +response: Qt.QModbusResponse <- Qt.QModbusResponse.new__QModbusPdu_FunctionCode_QByteArray(Qt.QModbusPdu.FunctionCode.ReadHoldingRegisters(), bytes)
    +data: Qt.QModbusDataUnit <- Qt.QModbusDataUnit.new__QModbusDataUnit_RegisterType_Int32_U32(Qt.QModbusDataUnit.RegisterType.HoldingRegisters(), Qt.Int32{0}, 1)
    ok: Bool <- Qt.QModbusTcpClient.processResponse(client, response, data)
    require(ok, "The native Modbus client rejected a valid holding-register response")
    value: U32 <- Qt.QModbusDataUnit.value(data, Qt.Int64{0, 0})
    require(U32.is_eq(value, 42), "Modbus response decoding lost its value output")
    private: Bool <- Qt.QModbusTcpClient.processPrivateResponse(client, response, data)
    require(Bool.not(private), "The default private-response handler changed")
    +server: Qt.QModbusTcpServer <- Qt.QModbusTcpServer.new()
    +map: Qt.QModbusDataUnit <- Qt.QModbusDataUnit.new__QModbusDataUnit_RegisterType_Int32_List_U32(Qt.QModbusDataUnit.RegisterType.HoldingRegisters(), Qt.Int32{0}, [42, 43])
    ok: Bool <- Qt.QModbusTcpServer.setMap(server, [Qt.PairValue{Qt.QModbusDataUnit.RegisterType.HoldingRegisters(), map}])
    require(ok, "The native Modbus server rejected its register map")
    +read: Qt.QModbusDataUnit <- Qt.QModbusDataUnit.new__QModbusDataUnit_RegisterType_Int32_U32(Qt.QModbusDataUnit.RegisterType.HoldingRegisters(), Qt.Int32{0}, 2)
    ok: Bool <- Qt.QModbusTcpServer.readData(server, read)
    require(ok, "The native Modbus server could not read its register range")
    value: U32 <- Qt.QModbusDataUnit.value(read, Qt.Int64{1, 0})
    require(U32.is_eq(value, 43), "Modbus readData lost its mutated value")
    ok: Bool <- Qt.QModbusTcpServer.readData(server, Qt.QModbusDataUnit{0})
    require(Bool.not(ok), "A null Modbus output changed Qt's false result")

def nmea() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +position: Qt.QNmeaPositionInfoSource <- Qt.QNmeaPositionInfoSource.new__QNmeaPositionInfoSource_UpdateMode_QObject(Qt.QNmeaPositionInfoSource.UpdateMode.RealTimeMode(), Qt.QObject{0})
    +bytes: Qt.QByteArray <- Qt.QByteArray.fromUtf8("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n")
    +info: Qt.QGeoPositionInfo <- Qt.QGeoPositionInfo.new()
    value: Qt.Outputs_Bool_Bool <- Qt.QNmeaPositionInfoSource.parsePosInfoFromNmeaData__QByteArray_QGeoPositionInfo(position, bytes, info)
    parsed(value)
    +coordinate: Qt.QGeoCoordinate <- Qt.QGeoPositionInfo.coordinate(info)
    valid: Bool <- Qt.QGeoCoordinate.isValid(coordinate)
    require(valid, "NMEA parsing did not mutate the supplied position")
    value: Qt.Outputs_Bool_Bool <- Qt.QNmeaPositionInfoSource.parsePosInfoFromNmeaData__QByteArray_Int32_QGeoPositionInfo(position, bytes, Qt.Int32{67}, info)
    parsed(value)
    invalid: Result<&1, &1, U32 & String, Qt.Outputs_Bool_Bool> <- Qt.Action.attempt(Qt.Outputs_Bool_Bool,
      Qt.QNmeaPositionInfoSource.parsePosInfoFromNmeaData__QByteArray_Int32_QGeoPositionInfo(position, bytes, Qt.Int32{68}, info))
    range_error(invalid)
    +source: Qt.QNmeaSatelliteInfoSource <- Qt.QNmeaSatelliteInfoSource.new__QNmeaSatelliteInfoSource_UpdateMode_QObject(Qt.QNmeaSatelliteInfoSource.UpdateMode.RealTimeMode(), Qt.QObject{0})
    +satellite_bytes: Qt.QByteArray <- Qt.QByteArray.fromUtf8("$GPGSV,1,1,04,01,40,083,41,02,17,308,42,03,08,122,43,04,12,230,44*74\r\n")
    value: Qt.Outputs_QNmeaSatelliteInfoSource_SatelliteInfoParseStatus_List_QGeoSatelliteInfo_QGeoSatelliteInfo_SatelliteSystem <- Qt.QNmeaSatelliteInfoSource.parseSatelliteInfoFromNmea__QByteArray_List_QGeoSatelliteInfo_QGeoSatelliteInfo_SatelliteSystem(source, satellite_bytes, [], Qt.QGeoSatelliteInfo.SatelliteSystem.Undefined())
    satellite_result(value)
    +use_bytes: Qt.QByteArray <- Qt.QByteArray.fromUtf8("$GPGSA,A,3,04,05,09,12,24,25,29,31,,,,,1.8,1.0,1.5*3D\r\n")
    value: Qt.Outputs_QGeoSatelliteInfo_SatelliteSystem_List_Int32 <- Qt.QNmeaSatelliteInfoSource.parseSatellitesInUseFromNmea__QByteArray_List_Int32(source, use_bytes, [])
    in_use_result(value)

def signing() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +oauth: Qt.QOAuth1 <- Qt.QOAuth1.new()
    +url: Qt.QUrl <- Qt.QUrl.new__String("https://bend.example/resource")
    +request: Qt.QNetworkRequest <- Qt.QNetworkRequest.new__QUrl(url)
    Qt.QOAuth1.setup__QNetworkRequest_List_PairValue_String_QVariant_QNetworkAccessManager_Operation(oauth, request, [], Qt.QNetworkAccessManager.Operation.GetOperation())
    present: Bool <- Qt.QNetworkRequest.hasRawHeader(request, "Authorization")
    require(present, "OAuth setup did not update the supplied network request")
    +verb: Qt.QByteArray <- Qt.QByteArray.fromUtf8("GET")
    Qt.QOAuth1.setup__QNetworkRequest_List_PairValue_String_QVariant_QByteArray(oauth, request, [], verb)
    present: Bool <- Qt.QNetworkRequest.hasRawHeader(request, "Authorization")
    require(present, "OAuth setup with an explicit verb lost its request mutation")

def voices() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +speech: Qt.QTextToSpeech <- Qt.QTextToSpeech.new()
    +locale: Qt.QLocale <- Qt.QLocale.new__String("en_US")
    values: List<&2, Qt.QVoice> <- Qt.QTextToSpeech.allVoices(speech, locale)
    values: List<&2, Qt.QVoice> <- Qt.QTextToSpeech.allVoices(speech, Qt.QLocale{0})
    return Unit{}

# The real HTTP request and scene graph data originate in Qt callbacks.
# Keep their complete forward wrappers in this fixture's native syntax check.
def match_request(rule: Qt.QHttpServerRouterRule, request: Qt.QHttpServerRequest, result: Qt.QRegularExpressionMatch) -> Qt.Action(Bool):
  Qt.QHttpServerRouterRule.matches(rule, request, result)

def update_node(item: Qt.QQuickItem, node: Qt.QSGNode, data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Qt.QSGNode):
  Qt.QQuickItem.updatePaintNode(item, node, data)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, style_options())
    Qt.scoped(Unit, graphics_outputs())
    Qt.scoped(Unit, modbus())
    Qt.scoped(Unit, nmea())
    Qt.scoped(Unit, signing())
    Qt.scoped(Unit, voices())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Native value-pointer calls leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_VALUE_POINTER_CALLS_OK styles=1 graphics=1 modbus=1 nmea=1 bounded=1 oauth=1 locale=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
