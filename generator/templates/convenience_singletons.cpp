static bool convenience_singleton(BqtRequest *r) {
    NativeCallScope scope;
    auto *engine = get<QQmlEngine>(r, r->self, @QML_ENGINE_ID@);
    if (r->error) return true;
    const int code = BendSignalApi::argument_type(r, r->arguments[0]);
    if (r->error) return true;
    const auto type = BendSignalApi::meta_type(code);
    const bool script = type == QMetaType::fromType<QJSValue>();
    if (!script && !type.flags().testFlag(QMetaType::PointerToQObject))
        return fail(r, EINVAL, "A singleton descriptor must be a QObject type or QJSValue");
    const uint32_t mode = r->arguments[1].word;
    if (mode > 1) return fail(r, EINVAL, "Invalid singleton lookup mode");
    const int id = int32_t(r->arguments[2].word);
    const QString uri = QString::fromUtf8(r->arguments[3].text, qsizetype(r->arguments[3].size));
    const QString name = QString::fromUtf8(r->arguments[4].text, qsizetype(r->arguments[4].size));
    if (script) {
        const auto value = mode ? engine->singletonInstance<QJSValue>(uri, name) : engine->singletonInstance<QJSValue>(id);
        scope.value_origin = r->self;
        r->result = BendSignalApi::write_value(r, code, &value);
    } else {
        auto *object = mode ? engine->singletonInstance<QObject *>(uri, name) : engine->singletonInstance<QObject *>(id);
        if (object && object->thread() != main_thread) return fail(r, EXDEV, "Singleton belongs to another Qt thread");
        if (object && !retain_js_exposure(r, r->self, borrow(r, object, @QOBJECT_ID@))) return true;
        QVariant value = QVariant::fromValue(object);
        if (!value.convert(type)) return fail(r, EINVAL, "Singleton has a different QObject type");
        r->result = BendSignalApi::write_value(r, code, value.constData());
    }
    return true;
}
