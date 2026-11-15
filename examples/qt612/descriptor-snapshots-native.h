#pragma once
#ifdef BQT_RHI_ATTRIBUTE_AT
static void rhi_snapshot_checks() {
    using namespace bendqt;
    BqtRequest r{};
    auto *layout = new QRhiVertexInputLayout;
    layout->setBindings({QRhiVertexInputBinding(24)});
    layout->setAttributes({QRhiVertexInputAttribute(0, 7, QRhiVertexInputAttribute::Float3, 0)});
    uint32_t owner = own(&r, layout, BQT_RHI_LAYOUT_TYPE);
    assert(owner && !r.error);
    r = {}; r.self = owner; r.arguments[0] = wide_value(0);
    BQT_RHI_ATTRIBUTE_AT(&r);
    assert(!r.error && r.result.word);
    BqtValue snapshot = r.result;
    auto *attribute = static_cast<QRhiVertexInputAttribute *>(entry(snapshot.word)->value);
    assert(attribute->location() == 7);
    r = {}; r.self = owner; r.arguments[0] = wide_value(1);
    BQT_RHI_ATTRIBUTE_AT(&r);
    assert(r.error == ERANGE);
    r = {}; r.self = owner; r.arguments[0] = wide_value(uint64_t(-1));
    BQT_RHI_ATTRIBUTE_AT(&r);
    assert(r.error == ERANGE);
    layout->setAttributes({QRhiVertexInputAttribute(0, 9, QRhiVertexInputAttribute::Float3, 0)});
    r = {}; r.self = owner; destroy_object(&r);
    assert(!r.error && attribute->location() == 7);
    discard_value(snapshot);
    std::puts("QT612_NATIVE_RHI_SNAPSHOTS_OK copied_descriptor=1 exact_bounds=1 negative_index=1 source_mutation=1 source_destruction=1");
}
#endif

#ifdef BQT_SCXML_DATA_NAMES
class BqtNativeScxmlTable : public QScxmlTableData {
public:
    mutable qint32 names[3] = {4, -1, 9};
    int count = 3;
    QString string(qint32) const override { return {}; }
    qint32 *instructions() const override { return nullptr; }
    QScxmlExecutableContent::EvaluatorInfo evaluatorInfo(qint32) const override { return {}; }
    QScxmlExecutableContent::AssignmentInfo assignmentInfo(qint32) const override { return {}; }
    QScxmlExecutableContent::ForeachInfo foreachInfo(qint32) const override { return {}; }
    qint32 *dataNames(int *size) const override { *size = count; return names; }
    qint32 initialSetup() const override { return -1; }
    QString name() const override { return {}; }
    const qint32 *stateMachineTable() const override { return nullptr; }
    QScxmlInvokableServiceFactory *serviceFactory(int) const override { return nullptr; }
};

static void scxml_name_checks() {
    using namespace bendqt;
    BqtRequest r{};
    auto *table = new BqtNativeScxmlTable;
    uint32_t owner = own(&r, static_cast<QScxmlTableData *>(table), BQT_SCXML_TABLE_TYPE);
    assert(owner && !r.error);
    r = {}; r.self = owner; BQT_SCXML_DATA_NAMES(&r);
    assert(!r.error && r.result.tag == 2 && r.result.count == 3);
    BqtValue snapshot = r.result;
    assert(snapshot.items[0].word == 4 && int32_t(snapshot.items[1].word) == -1 && snapshot.items[2].word == 9);
    table->names[0] = 99;
    assert(snapshot.items[0].word == 4);
    table->count = -1;
    r = {}; r.self = owner; BQT_SCXML_DATA_NAMES(&r);
    assert(r.error == EFAULT);
    r = {}; r.self = owner; destroy_object(&r);
    assert(!r.error && snapshot.items[0].word == 4);
    discard_value(snapshot);
    std::puts("QT612_NATIVE_SCXML_NAMES_OK explicit_extent=1 owning_copy=1 negative_count=1 source_destruction=1");
}
#endif
