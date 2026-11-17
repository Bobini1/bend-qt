import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def named(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, expected), "Metadata field changed class identity")
    case None{}: Qt.Action.fail(Unit, 1, "Metadata field lost its native name")

def metadata(value: Qt.QMetaObject, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QMetaObject.className(value)
    named(name, expected)

def copied(object: Qt.QObject, original: Qt.Qt3DCore.QNodeIdTypePair, copy: Qt.Qt3DCore.QNodeIdTypePair) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Qt3DCore.QNodeIdTypePair.destroy(original)
    Qt.QObject.destroy(object)
    Qt.QMetaObject.with(Unit, Qt.Qt3DCore.QNodeIdTypePair.Fields.type(copy), meta => metadata(meta, "QObject"))

def pair(+object: Qt.QObject, +original: Qt.Qt3DCore.QNodeIdTypePair) -> Qt.Action(Unit):
  Qt.Qt3DCore.QNodeIdTypePair.with(Unit, Qt.Qt3DCore.QNodeIdTypePair.new__Qt3DCore_QNodeIdTypePair(original), copy => copied(object, original, copy))

def node_id(+object: Qt.QObject, +meta: Qt.QMetaObject, id: Qt.Qt3DCore.QNodeId) -> Qt.Action(Unit):
  Qt.Qt3DCore.QNodeIdTypePair.with(Unit, Qt.Qt3DCore.QNodeIdTypePair.new__Qt3DCore_QNodeId_QMetaObject(id, meta), value => pair(object, value))

def original_metadata(+object: Qt.QObject, +meta: Qt.QMetaObject) -> Qt.Action(Unit):
  Qt.Qt3DCore.QNodeId.with(Unit, Qt.Qt3DCore.QNodeId.new(), id => node_id(object, meta, id))

def object(+value: Qt.QObject) -> Qt.Action(Unit):
  Qt.QMetaObject.with(Unit, Qt.QObject.metaObject(value), meta => original_metadata(value, meta))

def empty(value: Qt.Qt3DCore.QNodeIdTypePair) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    meta: Qt.QMetaObject <- Qt.Qt3DCore.QNodeIdTypePair.Fields.type(value)
    require(U32.is_eq(Qt.QMetaObject.word(meta), 0), "Default metadata field was not null")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Qt3DCore.QNodeIdTypePair.with(Unit, Qt.Qt3DCore.QNodeIdTypePair.new(), empty)
    Qt.QObject.with(Unit, Qt.QObject.new(), value => object(value))
    Qt.QMetaObject.with(Unit, Qt.Fixture.namespaceMetadata(), value => metadata(value, "Qt"))
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Metadata field leases leaked")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_FIELDS_OK copy=1 static_origin=1 namespace_origin=1 objects=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
