type QTest.QTouchEventSequence is Data:
  QTest.QTouchEventSequence{word: U32}

def QTest.QTouchEventSequence.word(self: QTest.QTouchEventSequence) -> U32:
  match self:
    case QTest.QTouchEventSequence{word}: word

def QTest.QTouchEventSequence.wrap(result: Result<&1, &1, U32 & String, U32>) -> Result<&1, &1, U32 & String, QTest.QTouchEventSequence>:
  match result:
    case Fail{error}: Fail{error}
    case Done{word}: Done{QTest.QTouchEventSequence{word}}

def QTest.createTouchDeviceWith(deviceType: QInputDevice.DeviceType, capabilities: Flags_QInputDevice__Capability) -> Action(QPointingDevice):
  Internal.TouchSequence.createDevice(QInputDevice.DeviceType.word(deviceType), Flags_QInputDevice__Capability.word(capabilities))

def QTest.createTouchDevice() -> Action(QPointingDevice):
  QTest.createTouchDeviceWith(QInputDevice.DeviceType.TouchScreen(), Flags_QInputDevice__Capability{QInputDevice.Capability.word(QInputDevice.Capability.Position())})

def QTest.touchEventWithAutoCommit(window: QWindow, device: QPointingDevice, autoCommit: Bool) -> Action(QTest.QTouchEventSequence):
  do Action<QTest.QTouchEventSequence>:
    word: U32 <- Internal.TouchSequence.newWindow(window, device, autoCommit)
    return QTest.QTouchEventSequence{word}

def QTest.touchEvent(window: QWindow, device: QPointingDevice) -> Action(QTest.QTouchEventSequence):
  QTest.touchEventWithAutoCommit(window, device, True{})

def QTest.touchWidgetWithAutoCommit(widget: QWidget, device: QPointingDevice, autoCommit: Bool) -> Action(QTest.QTouchEventSequence):
  do Action<QTest.QTouchEventSequence>:
    word: U32 <- Internal.TouchSequence.newWidget(widget, device, autoCommit)
    return QTest.QTouchEventSequence{word}

def QTest.touchWidget(widget: QWidget, device: QPointingDevice) -> Action(QTest.QTouchEventSequence):
  QTest.touchWidgetWithAutoCommit(widget, device, True{})

def QTest.QTouchEventSequence.destroy(self: QTest.QTouchEventSequence) -> Action(Unit):
  Internal.TouchSequence.destroy(QTest.QTouchEventSequence.word(self))

def QTest.QTouchEventSequence.releaseHandle(self: QTest.QTouchEventSequence) -> Action(Unit):
  Internal.TouchSequence.releaseHandle(QTest.QTouchEventSequence.word(self))

def QTest.QTouchEventSequence.commitWith(self: QTest.QTouchEventSequence, processEvents: Bool) -> Action(Bool):
  Internal.TouchSequence.commit(QTest.QTouchEventSequence.word(self), processEvents)

def QTest.QTouchEventSequence.commit(self: QTest.QTouchEventSequence) -> Action(Bool):
  QTest.QTouchEventSequence.commitWith(self, True{})

def QTest.QTouchEventSequence.press(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint) -> Action(Unit):
  Internal.TouchSequence.press(QTest.QTouchEventSequence.word(self), touchId, point)

def QTest.QTouchEventSequence.move(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint) -> Action(Unit):
  Internal.TouchSequence.move(QTest.QTouchEventSequence.word(self), touchId, point)

def QTest.QTouchEventSequence.release(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint) -> Action(Unit):
  Internal.TouchSequence.release(QTest.QTouchEventSequence.word(self), touchId, point)

def QTest.QTouchEventSequence.stationary(self: QTest.QTouchEventSequence, touchId: Int32) -> Action(Unit):
  Internal.TouchSequence.stationary(QTest.QTouchEventSequence.word(self), touchId)

def QTest.QTouchEventSequence.pressInWindow(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint, window: QWindow) -> Action(Unit):
  Internal.TouchSequence.pressWindow(QTest.QTouchEventSequence.word(self), touchId, point, window)

def QTest.QTouchEventSequence.moveInWindow(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint, window: QWindow) -> Action(Unit):
  Internal.TouchSequence.moveWindow(QTest.QTouchEventSequence.word(self), touchId, point, window)

def QTest.QTouchEventSequence.releaseInWindow(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint, window: QWindow) -> Action(Unit):
  Internal.TouchSequence.releaseWindow(QTest.QTouchEventSequence.word(self), touchId, point, window)

def QTest.QTouchEventSequence.pressInWidget(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint, widget: QWidget) -> Action(Unit):
  Internal.TouchSequence.pressWidget(QTest.QTouchEventSequence.word(self), touchId, point, widget)

def QTest.QTouchEventSequence.moveInWidget(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint, widget: QWidget) -> Action(Unit):
  Internal.TouchSequence.moveWidget(QTest.QTouchEventSequence.word(self), touchId, point, widget)

def QTest.QTouchEventSequence.releaseInWidget(self: QTest.QTouchEventSequence, touchId: Int32, point: QPoint, widget: QWidget) -> Action(Unit):
  Internal.TouchSequence.releaseWidget(QTest.QTouchEventSequence.word(self), touchId, point, widget)

def QTest.QTouchEventSequence.moveToParentScope(self: QTest.QTouchEventSequence) -> Action(QTest.QTouchEventSequence):
  do Action.Raw<Result<&1, &1, U32 & String, QTest.QTouchEventSequence>>:
    result: Result<&1, &1, U32 & String, U32> <- Scope.transfer_raw(0, QTest.QTouchEventSequence.word(self), 0)
    return QTest.QTouchEventSequence.wrap(result)

def QTest.QTouchEventSequence.detachFromScope(self: QTest.QTouchEventSequence) -> Action(QTest.QTouchEventSequence):
  do Action.Raw<Result<&1, &1, U32 & String, QTest.QTouchEventSequence>>:
    result: Result<&1, &1, U32 & String, U32> <- Scope.transfer_raw(0, QTest.QTouchEventSequence.word(self), 1)
    return QTest.QTouchEventSequence.wrap(result)

def QTest.QTouchEventSequence.with(-A: Type, acquire: Action(QTest.QTouchEventSequence), body: QTest.QTouchEventSequence -> Action(A)) -> Action(A):
  Action.using(QTest.QTouchEventSequence, A, acquire, value => Action.cleanup(QTest.QTouchEventSequence.releaseHandle(value)), body)
