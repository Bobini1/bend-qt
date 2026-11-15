#pragma once
#ifdef BQT_QTEST_FORMAT
static BqtRequest qt_test_column(const QString &name, int type) {
    BqtRequest r{};
    r.arguments[0].word = type;
    r.arguments[1] = bendqt::string_value(name);
    bendqt::BQT_QTEST_ADD_COLUMN(&r);
    bendqt::discard_value(r.arguments[1]);
    return r;
}

static BqtRequest qt_test_data(const QString &name, int type, bool global = false) {
    BqtRequest r{};
    r.arguments[0] = bendqt::string_value(name);
    r.arguments[1].word = type;
    if (global) bendqt::BQT_QTEST_GLOBAL_DATA(&r);
    else bendqt::BQT_QTEST_ELEMENT_DATA(&r);
    bendqt::discard_value(r.arguments[0]);
    return r;
}

class BqtNativeQtTestFixture : public QObject {
    Q_OBJECT
private slots:
    void initTestCase_data() {
        auto r = qt_test_column(QStringLiteral("global_text"), QMetaType::QString);
        assert(!r.error);
        QTest::newRow("global") << QStringLiteral("owned global value");
    }
    void copied_data() {
        QString name = QStringLiteral("local_number");
        auto r = qt_test_column(name, QMetaType::Int);
        assert(!r.error);
        name.fill(QChar('x')); // The retained column name must be independent.
        r = qt_test_column(QStringLiteral("local_number"), QMetaType::Int);
        assert(r.error == EEXIST);
        QTest::newRow("row") << 42;
        r = qt_test_column(QStringLiteral("too_late"), QMetaType::Int);
        assert(r.error == EPERM);
    }
    void copied() {
        using namespace bendqt;
        auto r = qt_test_data(QStringLiteral("local_number"), QMetaType::Int);
        assert(!r.error && r.result.word);
        auto *storage = static_cast<MetaStorage *>(entry(r.result.word)->value);
        assert(storage->type == QMetaType::fromType<int>() && *static_cast<int *>(storage->data) == 42);
        copied_number = r.result; // Survives the native table destruction.
        r = qt_test_data(QStringLiteral("global_text"), QMetaType::QString, true);
        assert(!r.error && r.result.word);
        storage = static_cast<MetaStorage *>(entry(r.result.word)->value);
        assert(*static_cast<QString *>(storage->data) == QStringLiteral("owned global value"));
        copied_text = r.result;
        r = qt_test_data(QStringLiteral("local_number"), QMetaType::Double);
        assert(r.error == EINVAL);
        r = qt_test_data(QStringLiteral("missing"), QMetaType::Int);
        assert(r.error == ENODATA);
        r = qt_test_column(QStringLiteral("from_test"), QMetaType::Int);
        assert(r.error == EPERM);
    }
public:
    BqtValue copied_number{}, copied_text{};
};

static void qtest_value_checks() {
    using namespace bendqt;
    BqtRequest timeout{};
    BQT_QTEST_TIMEOUT_GET(&timeout); assert(!timeout.error);
    const auto previous_timeout = timeout.result;
    timeout = {}; timeout.arguments[0] = wide_value(1234); BQT_QTEST_TIMEOUT_SET(&timeout);
    assert(!timeout.error && QTest::defaultTryTimeout.load() == std::chrono::milliseconds(1234));
    timeout = {}; BQT_QTEST_TIMEOUT_GET(&timeout); assert(!timeout.error && wide_bits(timeout.result) == 1234);
    timeout = {}; timeout.arguments[0] = previous_timeout; BQT_QTEST_TIMEOUT_SET(&timeout); assert(!timeout.error);
    auto r = qt_test_data(QStringLiteral("missing"), QMetaType::Int);
    assert(r.error == ENODATA);
    r = qt_test_column(QStringLiteral("missing"), QMetaType::Int);
    assert(r.error == ENODATA);
    r = {};
    r.arguments[0] = string_value(QStringLiteral("("));
    r.arguments[1] = string_value(QStringLiteral(")"));
    r.arguments[2] = sequence_value(2);
    r.arguments[2].items[0] = string_value(QStringLiteral("left"));
    r.arguments[2].items[1] = string_value(QStringLiteral("right"));
    BQT_QTEST_FORMAT(&r);
    assert(!r.error && QString::fromUtf8(r.result.text, r.result.size) == QStringLiteral("(left, right)"));
    for (auto &argument : r.arguments) discard_value(argument);
    discard_value(r.result);
    r = {};
    r.arguments[0] = string_value(QString(1, QChar(0)));
    r.arguments[1] = string_value(QString());
    r.arguments[2] = sequence_value(0);
    BQT_QTEST_FORMAT(&r);
    assert(r.error == EINVAL);
    for (auto &argument : r.arguments) discard_value(argument);
    BqtNativeQtTestFixture test;
    char program[] = "bend-qt-native-test";
    char *arguments[] = {program, nullptr};
    assert(QTest::qExec(&test, 1, arguments) == 0);
    auto *number = static_cast<MetaStorage *>(entry(test.copied_number.word)->value);
    auto *text = static_cast<MetaStorage *>(entry(test.copied_text.word)->value);
    assert(*static_cast<int *>(number->data) == 42);
    assert(*static_cast<QString *>(text->data) == QStringLiteral("owned global value"));
    discard_value(test.copied_number); discard_value(test.copied_text);
    std::puts("QT612_NATIVE_QTEST_VALUES_OK variadic_list=1 nul_rejected=1 no_session=1 stable_column_name=1 data_session=1 type_guard=1 missing_column=1 owned_row_copies=1 atomic_timeout=1");
}
#include "qtest-values-native.moc"
#endif
