import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected video error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An unsafe video operation succeeded")

# Mode 1 fails the format handler; mode 2 answers an invalid format.
type Video is Data:
  Video{ mode: U32, planes: Qt.QAbstractVideoBuffer.MapData, format: Qt.QVideoFrameFormat, buffer: Qt.QAbstractVideoBuffer }

def format_reply(mode: U32, format: Qt.QVideoFrameFormat) -> Qt.Action(Qt.QVideoFrameFormat):
  match mode:
    case 1: Qt.Action.fail(Qt.QVideoFrameFormat, 41, "Intentional format handler failure")
    case 2: Qt.QVideoFrameFormat.new()
    case _: Qt.QVideoFrameFormat.new__QVideoFrameFormat(format)

def frame_format(state: Video) -> Qt.Action(Qt.QVideoFrameFormat):
  match state:
    case Video{mode, planes, format, buffer}: format_reply(mode, format)

def reentrant_rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(+code, message)}: require(U32.is_eq(code, 16) || U32.is_eq(code, 1), "Wrong reentrant video rejection: " ++ message)
    case _: Qt.Action.fail(Unit, 1, "unmap ran inside an unfinished map")

def map_reply(buffer: Qt.QAbstractVideoBuffer, planes: Qt.QAbstractVideoBuffer.MapData) -> Qt.Action(Qt.QAbstractVideoBuffer.MapData):
  do Qt.Action<Qt.QAbstractVideoBuffer.MapData>:
    nested: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractVideoBuffer.unmap(buffer))
    reentrant_rejected(nested)
    Qt.QAbstractVideoBuffer.MapData.new__QAbstractVideoBuffer_MapData(planes)

def mapped_planes(state: Video, mode: Qt.QVideoFrame.MapMode) -> Qt.Action(Qt.QAbstractVideoBuffer.MapData):
  match state:
    case Video{kind, planes, format, buffer}: map_reply(buffer, planes)

def unmapped(state: Unit) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def release_views(values: List<&2, Maybe<&2, Qt.MemoryView>>) -> Qt.Action(Unit):
  match values:
    case Nil{}: Qt.Action.pure(Unit, Unit{})
    case Some{view} <> tail:
      do Qt.Action<Unit>:
        Qt.MemoryView.release(view)
        release_views(tail)
    case None{} <> tail: release_views(tail)

def readonly_write(view: Qt.MemoryView, bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.MemoryView.write(view, Qt.UInt64{0, 0}, bytes))
    rejected(Unit, result, 1)

def check_view(+buffer: Qt.QAbstractVideoBuffer, copy: Qt.QAbstractVideoBuffer.MapData, values: List<&2, Maybe<&2, Qt.MemoryView>>) -> Qt.Action(Unit):
  match values:
    case Some{+view} <> tail:
      do Qt.Action<Unit>:
        readonly: Bool <- Qt.MemoryView.isReadOnly(view)
        require(readonly, "A ReadOnly map exposed a writable plane")
        Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([7]), bytes => readonly_write(view, bytes))
        busy: Result<&1, &1, U32 & String, Qt.QVideoFrame> <- Qt.Action.attempt(Qt.QVideoFrame, Qt.QVideoFrame.fromVideoBuffer(buffer))
        rejected(Qt.QVideoFrame, busy, 16)
        Qt.QAbstractVideoBuffer.unmap(buffer)
        stale: Result<&1, &1, U32 & String, List<&2, Maybe<&2, Qt.MemoryView>>> <- Qt.Action.attempt(List<&2, Maybe<&2, Qt.MemoryView>>, Qt.QAbstractVideoBuffer.MapData.Fields.data(copy))
        rejected(List<&2, Maybe<&2, Qt.MemoryView>>, stale, 116)
        stale_view: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{1, 0}))
        rejected(Qt.QByteArray, stale_view, 116)
        Qt.MemoryView.release(view)
        release_views(tail)
    case _: Qt.Action.fail(Unit, 1, "A mapped plane disappeared")

def mapped_copy(buffer: Qt.QAbstractVideoBuffer, +copy: Qt.QAbstractVideoBuffer.MapData) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    values: List<&2, Maybe<&2, Qt.MemoryView>> <- Qt.QAbstractVideoBuffer.MapData.Fields.data(copy)
    check_view(buffer, copy, values)

def mapped(buffer: Qt.QAbstractVideoBuffer, data: Qt.QAbstractVideoBuffer.MapData) -> Qt.Action(Unit):
  Qt.QAbstractVideoBuffer.MapData.with(Unit, Qt.QAbstractVideoBuffer.MapData.new__QAbstractVideoBuffer_MapData(data), copy => mapped_copy(buffer, copy))

def rendered_frame(image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QImage.width(image)
    require(U32.is_eq(Qt.Int32.word(width), 2), "Native video conversion did not read the supplied planes")

def shared_frame(+buffer: Qt.QAbstractVideoBuffer, +frame: Qt.QVideoFrame, +copy: Qt.QVideoFrame) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVideoFrame.destroy(frame)
    valid: Bool <- Qt.QVideoFrame.isValid(copy)
    require(valid, "Destroying one frame invalidated its shared buffer")
    mapped: Bool <- Qt.QVideoFrame.map(copy, Qt.QVideoFrame.MapMode.ReadOnly())
    require(mapped, "A frame could not map its custom buffer")
    Qt.QImage.with(Unit, Qt.QVideoFrame.toImage(copy), rendered_frame)
    bypass: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractVideoBuffer.unmap(buffer))
    rejected(Unit, bypass, 1)
    Qt.QVideoFrame.destroy(copy)
    gone: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractVideoBuffer.destroy(buffer))
    rejected(Unit, gone, 116)

def frame(buffer: Qt.QAbstractVideoBuffer, +value: Qt.QVideoFrame) -> Qt.Action(Unit):
  Qt.QVideoFrame.with(Unit, Qt.QVideoFrame.new__QVideoFrame(value), copy => shared_frame(buffer, value, copy))

def buffer_checks(+buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractVideoBuffer.MapData.with(Unit, Qt.QAbstractVideoBuffer.map(buffer, Qt.QVideoFrame.MapMode.ReadOnly()), data => mapped(buffer, data))
    Qt.CallbackProbe.videoFailAllocation()
    allocation: Result<&1, &1, U32 & String, Qt.QVideoFrame> <- Qt.Action.attempt(Qt.QVideoFrame, Qt.QVideoFrame.fromVideoBuffer(buffer))
    rejected(Qt.QVideoFrame, allocation, 12)
    Qt.QVideoFrame.with(Unit, Qt.QVideoFrame.fromVideoBuffer(buffer), value => frame(buffer, value))

def destroyed_views(values: List<&2, Maybe<&2, Qt.MemoryView>>) -> Qt.Action(Unit):
  match values:
    case Some{+view} <> tail:
      do Qt.Action<Unit>:
        stale: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{1, 0}))
        rejected(Qt.QByteArray, stale, 116)
        Qt.MemoryView.release(view)
        release_views(tail)
    case _: Qt.Action.fail(Unit, 1, "Expected a bounded video view before buffer destruction")

def destroyed_mapping(+buffer: Qt.QAbstractVideoBuffer, +data: Qt.QAbstractVideoBuffer.MapData) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    values: List<&2, Maybe<&2, Qt.MemoryView>> <- Qt.QAbstractVideoBuffer.MapData.Fields.data(data)
    Qt.QAbstractVideoBuffer.destroy(buffer)
    stale: Result<&1, &1, U32 & String, List<&2, Maybe<&2, Qt.MemoryView>>> <- Qt.Action.attempt(List<&2, Maybe<&2, Qt.MemoryView>>, Qt.QAbstractVideoBuffer.MapData.Fields.data(data))
    rejected(List<&2, Maybe<&2, Qt.MemoryView>>, stale, 116)
    destroyed_views(values)

def destroy_mapped(+buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  Qt.QAbstractVideoBuffer.MapData.with(Unit, Qt.QAbstractVideoBuffer.map(buffer, Qt.QVideoFrame.MapMode.ReadWrite()), data => destroyed_mapping(buffer, data))

# Qt maps and unmaps on another thread; the handlers run on the main thread
# while its Qt event loop runs.
def thread_buffer(+buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    planes: U32 <- Qt.CallbackProbe.videoThread(buffer)
    require(U32.is_eq(planes, 1), "map from another thread did not reach the handler")

def failed_factory(+buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.QVideoFrame> <- Qt.Action.attempt(Qt.QVideoFrame, Qt.QVideoFrame.fromVideoBuffer(buffer))
    rejected(Qt.QVideoFrame, result, 41)
    consumed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractVideoBuffer.destroy(buffer))
    rejected(Unit, consumed, 116)

def invalid_frame(value: Qt.QVideoFrame) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.QVideoFrame.isValid(value)
    require(Bool.not(valid), "An invalid custom format produced a valid frame")

def invalid_factory(+buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVideoFrame.with(Unit, Qt.QVideoFrame.fromVideoBuffer(buffer), invalid_frame)
    consumed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractVideoBuffer.destroy(buffer))
    rejected(Unit, consumed, 116)

def dispatch_check(check: U32, +buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  match check:
    case 0: buffer_checks(buffer)
    case 1: destroy_mapped(buffer)
    case 2: thread_buffer(buffer)
    case 3: failed_factory(buffer)
    case _: invalid_factory(buffer)

def prepared(+mode: U32, +planes: Qt.QAbstractVideoBuffer.MapData, +format: Qt.QVideoFrameFormat, check: U32, +buffer: Qt.QAbstractVideoBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractVideoBuffer.Virtual.format.handle(~Video, ~frame_format, buffer, Video{mode, planes, format, buffer})
    Qt.QAbstractVideoBuffer.Virtual.map.handle(~Video, ~mapped_planes, buffer, Video{mode, planes, format, buffer})
    Qt.QAbstractVideoBuffer.Virtual.unmap.handle(~Unit, ~unmapped, buffer, Unit{})
    dispatch_check(check, buffer)

def buffer_run(+mode: U32, +planes: Qt.QAbstractVideoBuffer.MapData, +format: Qt.QVideoFrameFormat, check: U32) -> Qt.Action(Unit):
  Qt.QAbstractVideoBuffer.with(Unit, Qt.QAbstractVideoBuffer.newOverride(), buffer => prepared(mode, planes, format, check, buffer))

def configure(extent: U32, pitch: U32, +storage: Qt.ImageBuffer, +data: Qt.QAbstractVideoBuffer.MapData, +format: Qt.QVideoFrameFormat) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractVideoBuffer.MapData.Fields.set_data(data, [Some{storage}, None{}, None{}, None{}])
    Qt.QAbstractVideoBuffer.MapData.Fields.set_dataSize(data, [Qt.Int32{extent}, Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{0}])
    Qt.QAbstractVideoBuffer.MapData.Fields.set_bytesPerLine(data, [Qt.Int32{pitch}, Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{0}])
    Qt.QAbstractVideoBuffer.MapData.Fields.set_planeCount(data, Qt.Int32{1})
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractVideoBuffer.MapData.Fields.set_dataSize(data, [Qt.Int32{17}, Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{0}]))
    rejected(Unit, bad, 34)
    Qt.ImageBuffer.destroy(storage)
    buffer_run(0, data, format, 0)
    buffer_run(0, data, format, 1)
    buffer_run(0, data, format, 2)
    buffer_run(1, data, format, 3)
    buffer_run(2, data, format, 4)

def with_format(extent: U32, pitch: U32, format: Qt.QVideoFrameFormat) -> Qt.Action(Unit):
  Qt.ImageBuffer.with(Unit, Qt.ImageBuffer.new(Qt.UInt64{16, 0}), storage =>
    Qt.QAbstractVideoBuffer.MapData.with(Unit, Qt.QAbstractVideoBuffer.MapData.new(), data => configure(extent, pitch, storage, data, format)))

def with_size(+size: Qt.QSize) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVideoFrameFormat.with(Unit, Qt.QVideoFrameFormat.new__QSize_QVideoFrameFormat_PixelFormat(size, Qt.QVideoFrameFormat.PixelFormat.Format_RGBA8888()), format => with_format(16, 8, format))
    Qt.QVideoFrameFormat.with(Unit, Qt.QVideoFrameFormat.new__QSize_QVideoFrameFormat_PixelFormat(size, Qt.QVideoFrameFormat.PixelFormat.Format_YUV420P()), format => with_format(6, 2, format))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSize.with(Unit, Qt.QSize.new__Int32_Int32(Qt.Int32{2}, Qt.Int32{2}), size => with_size(size))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Video mapping leaked handles or leases")
    Qt.Action.lift(Unit, IO.print("QT612_VIDEO_BUFFERS_OK readonly=1 plane_bounds=1 copied_epoch=1 unique_ownership=1 shared_frames=1 thread_calls=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
