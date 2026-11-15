static bool qt_test_text(BqtRequest *r, const QString &text) {
    if (text.contains(QChar(0))) { fail(r, EINVAL, "QtTest native strings cannot contain NUL"); return false; }
    return true;
}

static QString qt_test_format(BqtRequest *r, const QString &prefix, const QString &suffix,
                              const QList<QString> &arguments) {
    if (!qt_test_text(r, prefix) || !qt_test_text(r, suffix)) return {};
    QString result = prefix;
    for (qsizetype i = 0; i < arguments.size(); ++i) {
        if (!qt_test_text(r, arguments[i])) return {};
        if (i) result += QStringLiteral(", ");
        result += arguments[i];
    }
    result += suffix;
    return result;
}

#if BQT_HAS_EXACT_QT
static bool qt_test_private_session(BqtRequest *r) {
    auto *test = QTest::testObject();
    if (!test) { fail(r, ENODATA, "There is no active QtTest session"); return false; }
    if (test->thread() != QThread::currentThread()) {
        fail(r, EPERM, "QtTest data access must run on the test object's thread"); return false;
    }
    return true;
}

static void qt_test_private_add_column(BqtRequest *r, int id, const QString &name) {
    if (!qt_test_text(r, name) || !qt_test_private_session(r)) return;
    auto *table = QTestTable::currentTestTable();
    if (!table || QTest::runningTest() || table->dataCount() ||
            (QTestResult::currentTestData() && QTestResult::currentTestData()->parent() == table)) {
        fail(r, EPERM, "Columns may only be added to the current QtTest data table before its rows"); return;
    }
    QMetaType type(id);
    if (!meta_storage_type(r, type)) return;
    if (!type.isCopyConstructible()) { fail(r, ENOTSUP, "QtTest columns require a copyable metatype"); return; }
    auto bytes = name.toUtf8();
    if (table->indexOf(bytes.constData()) >= 0) { fail(r, EEXIST, "QtTest column already exists"); return; }
    QTest::addColumnInternal(id, intern_native_name(bytes.constData(), size_t(bytes.size())));
}

static uint32_t qt_test_private_data(BqtRequest *r, const QString &name, int id, bool global) {
    if (!qt_test_text(r, name) || !qt_test_private_session(r)) return 0;
    auto *row = global ? QTestResult::currentGlobalTestData() : QTestResult::currentTestData();
    auto *table = row ? row->parent() : nullptr;
    if (!table) { fail(r, ENODATA, "There is no current QtTest data row"); return 0; }
    auto bytes = name.toUtf8();
    int index = table->indexOf(bytes.constData());
    if (index < 0 || index >= row->dataCount()) { fail(r, ENODATA, "QtTest row has no value for this column"); return 0; }
    if (table->elementTypeId(index) != id) { fail(r, EINVAL, "QtTest column has a different metatype"); return 0; }
    QMetaType type(id);
    if (!meta_storage_type(r, type)) return 0;
    if (!type.isCopyConstructible()) { fail(r, ENOTSUP, "QtTest value is not copyable"); return 0; }
    const void *data = row->data(index);
    if (!data) { fail(r, ENODATA, "QtTest data value is uninitialized"); return 0; }
    // A selected native value first passes through the same owning-copy hooks
    // as ordinary method returns. These discover/pin document/model origins.
    ConversionValueGuard source_guard(BqtValue{});
    auto &source = source_guard.value;
@COPY_CASES@
    if (r->error) return 0;
    bool scalar = type.flags().testFlag(QMetaType::IsEnumeration);
    switch (id) {
    case QMetaType::Bool: case QMetaType::Int: case QMetaType::UInt:
    case QMetaType::LongLong: case QMetaType::ULongLong: case QMetaType::Double:
    case QMetaType::Float: case QMetaType::Short: case QMetaType::UShort:
    case QMetaType::Char: case QMetaType::SChar: case QMetaType::UChar:
    case QMetaType::Long: case QMetaType::ULong: case QMetaType::Char16: case QMetaType::Char32:
    case QMetaType::QChar: case QMetaType::QString: case QMetaType::QByteArray:
        scalar = true; break;
    default: break;
    }
    if (!source.word && !scalar) {
        fail(r, ENOTSUP, "QtTest custom metatype has no checked owning value representation"); return 0;
    }
    uint32_t result = create_meta_storage(r, type, data);
    if (!result) { if (!r->error) fail(r, ENOTSUP, "QtTest metatype copy failed"); return 0; }
    BqtValue output{}; output.word = output.owned_handle = result;
    ConversionValueGuard output_guard(output);
    if (source.word && !preserve_variant_origin(r, result, source.word)) return 0;
    if (!finish_model_index_ownership(r, result)) return 0;
    output_guard.release();
    return result;
}
#endif
