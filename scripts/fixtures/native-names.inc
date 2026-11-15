
    auto require = [](bool ok, const char *message) { if (!ok) { std::fprintf(stderr, "Native names: %s\n", message); throw std::runtime_error(message); } };
    struct ShutdownProbe {
        const char *retained = nullptr;
        ~ShutdownProbe() {
            if (!retained || std::strcmp(retained, "Fixture.Retained") != 0) std::abort();
            std::puts("QT612_NATIVE_NAMES_SHUTDOWN_OK");
        }
    };
    static ShutdownProbe shutdown_probe;
    auto text = [](const char *value) { BqtValue result{}; result.text = const_cast<char *>(value); result.size = std::strlen(value); return result; };
    auto clean = [&](uint32_t id) { BqtRequest request{}; request.self = id; destroy_object(&request); if (request.error) std::fprintf(stderr, "cleanup token %u: %u %s\n", id, request.error, request.message); require(!request.error, "Native-name fixture cleanup failed"); };
    BqtRequest call{};
    QByteArray output;
    uint32_t stream = own<QTextStream>(r, new QTextStream(&output), @QTextStream@);
    call.self = stream; call.arguments[0] = wide_value(0x1234);
    @STREAM@(&call); require(!call.error, "Address formatting failed");
    get<QTextStream>(r, stream, @QTextStream@)->flush();
    require(output == "0x1234", "Native pointer identity changed");
    clean(stream);
    call = {}; call.arguments[0] = text("identity"); call.arguments[1] = wide_value(0x1234);
    @HELP@(&call); require(!call.error && call.result.size > 0, "Unique connection name failed"); discard_value(call.result);
    call = {}; call.arguments[0] = wide_value(0x1234); call.arguments[1] = wide_value(0x1234);
    call.arguments[2] = text("actual"); call.arguments[3] = text("expected"); call.arguments[4] = text("fixture"); call.arguments[5].word = 1;
    @COMPARE@(&call); require(!call.error && call.result.word, "Pointer comparison failed");
    struct Plugin final : QQmlExtensionInterface {
        const char *registered = nullptr, *initialized = nullptr;
        void registerTypes(const char *name) override { registered = name; }
        void initializeEngine(QQmlEngine *, const char *name) override { initialized = name; }
    };
    auto *plugin = new Plugin;
    uint32_t extension = own<QQmlExtensionInterface>(r, plugin, @QQmlExtensionInterface@);
    uint32_t types = register_native_borrow(r, static_cast<QQmlTypesExtensionInterface *>(plugin), @QQmlTypesExtensionInterface@, extension);
    std::string uri("Fixture.Retained");
    call = {}; call.self = types; call.arguments[0] = text(uri.c_str());
    @REGISTER@(&call); require(!call.error, "Plugin type registration failed");
    call = {}; call.self = extension; call.arguments[0].word = 0; call.arguments[1] = text(uri.c_str());
    @ENGINE@(&call); require(!call.error, "Plugin initialization failed");
    uri.assign(2000, 'x');
    for (int i = 0; i < 1000; ++i) { auto other = std::to_string(i); intern_native_name(other.data(), other.size()); }
    require(std::strcmp(plugin->registered, "Fixture.Retained") == 0 && plugin->registered == plugin->initialized, "Plugin URI lifetime or interning failed");
    shutdown_probe.retained = plugin->registered;
    call = {}; call.self = types; call.arguments[0].text = const_cast<char *>("Bad\0Name"); call.arguments[0].size = 8;
    @REGISTER@(&call); require(call.error == EINVAL, "Plugin name did not reject embedded NUL");
    clean(extension);
    struct Monitor final : QGeoAreaMonitorSource {
        Monitor() : QGeoAreaMonitorSource(nullptr) {}
        const char *signal = nullptr;
        Error error() const override { return NoError; }
        QList<QGeoAreaMonitorInfo> activeMonitors() const override { return {}; }
        QList<QGeoAreaMonitorInfo> activeMonitors(const QGeoShape &) const override { return {}; }
        bool startMonitoring(const QGeoAreaMonitorInfo &) override { return true; }
        bool stopMonitoring(const QGeoAreaMonitorInfo &) override { return true; }
        AreaMonitorFeatures supportedAreaMonitorFeatures() const override { return {}; }
        bool requestUpdate(const QGeoAreaMonitorInfo &, const char *name) override { signal = name; return true; }
    };
    auto *monitor = new Monitor;
    uint32_t source = own<QGeoAreaMonitorSource>(r, monitor, @QGeoAreaMonitorSource@);
    uint32_t info = own<QGeoAreaMonitorInfo>(r, new QGeoAreaMonitorInfo("fixture"), @QGeoAreaMonitorInfo@);
    std::string signal("2areaExited(QGeoAreaMonitorInfo,QGeoPositionInfo)");
    call = {}; call.self = source; call.arguments[0].word = info; call.arguments[1] = text(signal.c_str());
    @MONITOR@(&call); require(!call.error && call.result.word, "Monitor signal registration failed");
    signal.assign(3000, 'y');
    require(std::strcmp(monitor->signal, "2areaExited(QGeoAreaMonitorInfo,QGeoPositionInfo)") == 0, "Monitor retained signal pointer expired");
    clean(info); clean(source);
    return true;
