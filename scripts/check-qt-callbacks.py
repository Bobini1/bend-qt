#!/usr/bin/env python3
"""Maintainer-only check of Bend handlers that Qt runs; never publishes a package.

Builds one focused package for the handler fixtures, adds native probe effects
that make Qt call the installed handlers, and runs every fixture through the
consumer build (`bend main.bend -o app`).
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import callbacks
import native_objects
import representations
import overload_names
from generate import Generator
from lifetime import evaluate_tables, cpp_tables
from backend import compile_backend, versioned_include_paths
from upstream import prepare as prepare_upstream
import qt_targets


# This is a test-module selection, not the production class inventory. The
# proxy subset below is discovered from the fixtures themselves.
SUITE_MODULES = ('QtMultimedia', 'Qt3DCore', 'Qt3DRender', 'QtDesigner', 'QtQuick3D',
                 'QtRemoteObjects', 'QtScxml', 'QtSerialBus', 'QtSql', 'QtWebEngineCore', 'QtWebView', 'QtWebSockets',
                 'QtPositioning', 'QtLocation', 'QtTextToSpeech', 'QtNetworkAuth', 'QtHttpServer',
                 'QtQuickTest', 'QtTest', 'QtPrintSupport', 'QtCanvasPainter', 'Qt3DAnimation', 'QtStateMachine')

EXAMPLES = [('callbacks', 'QT612_CALLBACKS_OK'), ('qml-types', 'QT612_QML_TYPES_OK'),
            ('properties', 'QT612_PROPERTIES_OK'),
            ('typed-data', 'QT612_TYPED_DATA_OK'), ('qml-creatable', 'QT612_QML_CREATABLE_OK'),
            ('thread-pool-await', 'QT612_THREAD_POOL_AWAIT_OK'),
            ('mutable-callbacks', 'QT612_MUTABLE_CALLBACKS_OK'), ('factory-callbacks', 'QT612_FACTORY_CALLBACKS_OK'),
            ('graphics-callbacks', 'QT612_GRAPHICS_CALLBACKS_OK'), ('scenegraph-callbacks', 'QT612_SCENEGRAPH_CALLBACKS_OK'),
            ('retained-callbacks', 'QT612_RETAINED_CALLBACKS_OK')]

# Fixture, marker, and what it needs: Qt modules, or 'rhi'.
FIXTURES = [
    ('renderer-interface-views', 'QT_RENDERER_INTERFACE_VIEWS_OK', ()),
    ('action-scopes', 'QT612_ACTION_SCOPES_OK', ()),
    ('resource-growth', 'QT612_RESOURCE_GROWTH_OK', ()),
    ('registry-boundaries', 'QT612_REGISTRY_BOUNDARIES_OK', ()),
    ('metadata-limits', 'QT612_METADATA_LIMITS_OK', ()),
    ('pool-await', 'QT612_POOL_AWAIT_OK', ()),
    ('callback-depth', 'QT612_CALLBACK_DEPTH_OK', ()),
    ('qt-objects', 'QT612_QT_OBJECTS_OK', ()),
    ('qt-object-worker', 'QT612_QT_OBJECT_WORKER_OK', ()),
    ('qml-created-objects', 'QT612_QML_CREATED_OBJECTS_OK', ()),
    ('qml-extension-inheritance', 'QT612_QML_EXTENSION_INHERITANCE_OK', ()),
    ('qml-factory-failures', 'QT612_QML_FACTORY_FAILURES_OK', ()),
    ('qml-registration-modes', 'QT612_QML_REGISTRATION_MODES_OK', ()),
    ('qml-constructors', 'QT612_QML_CONSTRUCTORS_OK', ()),
    ('method-metadata', 'QT612_METHOD_METADATA_OK', ()),
    ('runtime-enums', 'QT612_RUNTIME_ENUMS_OK', ()),
    ('generic-variants', 'QT612_GENERIC_VARIANTS_OK', ()),
    ('value-types', 'QT612_VALUE_TYPES_OK', ()),
    ('metadata-arguments', 'QT612_METADATA_ARGUMENTS_OK', ()),
    ('metadata-signal-arguments', 'QT612_METADATA_SIGNAL_ARGUMENTS_OK', ()),
    ('convenience-apis', 'QT612_CONVENIENCE_APIS_OK', ()),
    ('range-model-versions', 'QT_RANGE_MODEL_BEND_OK', ()),
    ('audio-buffer-bytes', 'QT612_AUDIO_BUFFER_BYTES_OK', ('QtMultimedia',)),
    ('quick-test-runner', 'QT612_QUICK_TEST_RUNNER_OK', ('QtQuickTest',)),
    ('qml-list-properties', 'QT612_QML_LIST_PROPERTIES_OK', ()),
    ('callback-surfaces', 'QT612_CALLBACK_SURFACES_OK', ()),
    ('http-server-callbacks', 'QT612_HTTP_SERVER_CALLBACKS_OK', ('QtHttpServer',)),
    ('oauth-parameter-callbacks', 'QT612_OAUTH_PARAMETER_CALLBACKS_OK', ('QtNetworkAuth',)),
    ('canvas-grab-callbacks', 'QT612_CANVAS_GRAB_CALLBACKS_OK', ('QtCanvasPainter', 'rhi')),
    ('function-pointer-callbacks', 'QT612_FUNCTION_POINTER_CALLBACKS_OK', ()),
    ('data-stream-values', 'QT612_DATA_STREAM_VALUES_OK', ()),
    ('metadata-arrow', 'QT612_METADATA_ARROW_OK', ()),
    ('native-value-forms', 'QT612_NATIVE_VALUE_FORMS_OK', ()),
    ('explicit-copy-values', 'QT612_EXPLICIT_COPY_VALUES_OK', ('QtWebSockets',)),
    ('value-pointer-calls', 'QT612_VALUE_POINTER_CALLS_OK', ('QtPositioning', 'QtSerialBus', 'QtNetworkAuth', 'QtHttpServer', 'QtTextToSpeech')),
    ('event-dispatcher-transfer', 'QT612_EVENT_DISPATCHER_TRANSFER_OK', ()),
    ('child-lookup-options', 'QT612_CHILD_LOOKUP_OPTIONS_OK', ()),
    ('protected-members', 'QT612_PROTECTED_MEMBERS_OK', ()),
    ('protected-lifetimes', 'QT612_PROTECTED_LIFETIMES_OK', ('QtPrintSupport',)),
    ('protected-fields', 'QT612_PROTECTED_FIELDS_OK', ()),
    ('native-result-views', 'QT612_NATIVE_RESULT_VIEWS_OK', ('QtSql',)),
    ('core-pointer-results', 'QT612_CORE_POINTER_RESULTS_OK', ()),
    ('core-keyframes', 'QT612_CORE_KEYFRAMES_OK', ('Qt3DAnimation',)),
    ('qobject-interface-helpers', 'QT612_QOBJECT_INTERFACE_HELPERS_OK', ('QtDesigner', 'QtSql')),
    ('mutex-lockers', 'QT612_MUTEX_LOCKERS_OK', ()),
    ('cursor-guards', 'QT612_CURSOR_GUARDS_OK', ()),
    ('render-factory-results', 'QT612_RENDER_FACTORY_RESULTS_OK', ()),
    ('io-pipe', 'QT612_IO_PIPE_OK', ()),
    ('touch-sequences', 'QT612_TOUCH_SEQUENCES_OK', ('QtTest',)),
    ('dynamic-properties', 'QT612_DYNAMIC_PROPERTIES_OK', ()),
    ('transition-constructors', 'QT612_TRANSITION_CONSTRUCTORS_OK', ('QtStateMachine',)),
    ('reverse-pointer-callbacks', 'QT612_REVERSE_POINTER_CALLBACKS_OK', ('QtLocation', 'QtWebEngineCore')),
    ('model-source-index', 'QT612_MODEL_SOURCE_INDEX_OK', ()),
    ('post-routines', 'QT612_POST_ROUTINES_OK', ()),
    ('property-bindings', 'QT612_PROPERTY_BINDINGS_OK', ()),
    ('property-attributes', 'QT612_PROPERTY_ATTRIBUTES_OK', ()),
    ('nondefault-properties', 'QT612_NONDEFAULT_PROPERTIES_OK', ()),
    ('typed-connection-modes', 'QT612_TYPED_CONNECTION_MODES_OK', ()),
    ('unicode-metadata', 'QT612_UNICODE_METADATA_OK', ()),
    ('error-messages', 'QT612_ERROR_MESSAGES_OK', ()),
    ('qml-singleton-extensions', 'QT612_QML_SINGLETON_EXTENSIONS_OK', ()),
    ('qml-script-singletons', 'QT612_QML_SCRIPT_SINGLETONS_OK', ()),
    ('property-map-subclasses', 'QT612_PROPERTY_MAP_SUBCLASSES_OK', ()),
    ('legacy-charts', 'QT612_LEGACY_CHARTS_OK', ('QtCharts', 'QtDataVisualization')),
    ('opaque-data', 'QT612_OPAQUE_DATA_OK', ()),
    ('custom-signals', 'QT612_CUSTOM_SIGNAL_CONTRACTS_OK', ()),
    ('native-signal-arguments', 'QT612_NATIVE_SIGNAL_ARGUMENTS_OK', ()),
    ('native-argument-types', 'QT612_NATIVE_ARGUMENT_TYPES_OK', ()),
    ('signal-connection-modes', 'QT612_SIGNAL_CONNECTION_MODES_OK', ()),
    ('native-pointer-arguments', 'QT612_NATIVE_POINTER_ARGUMENTS_OK', ()),
    ('synchronous-signals', 'QT612_SYNCHRONOUS_SIGNALS_OK', ()),
    ('callback-events', 'QT612_CALLBACK_EVENTS_OK', ()),
    ('image-provider-callbacks', 'QT612_IMAGE_PROVIDER_CALLBACKS_OK', ()),
    ('async-image-provider', 'QT612_ASYNC_IMAGE_PROVIDER_OK', ()),
    ('scenegraph-material-render', 'QT_SCENEGRAPH_MATERIAL_RENDER_OK', ()),
    ('scenegraph-material-instances', 'QT_SCENEGRAPH_MATERIAL_INSTANCES_OK', ()),
    ('native-image-plugin', 'QT_NATIVE_IMAGE_PLUGIN_OK', ()),
    ('callback-retention-cycle', 'QT612_CALLBACK_RETENTION_CYCLE_OK', ()),
    ('texture-provider-callbacks', 'QT612_TEXTURE_PROVIDER_CALLBACKS_OK', ()),
    ('device-callbacks', 'QT612_DEVICE_CALLBACKS_OK', ()),
    ('accessible-callbacks', 'QT612_ACCESSIBLE_CALLBACKS_OK', ()),
    ('qml-interface-callbacks', 'QT612_QML_INTERFACE_CALLBACKS_OK', ()),
    ('render-value-callbacks', 'QT612_RENDER_VALUE_CALLBACKS_OK', ()),
    ('editor-factory-callbacks', 'QT612_EDITOR_FACTORY_CALLBACKS_OK', ()),
    ('icon-hooks', 'QT612_ICON_HOOKS_OK', ()),
    ('callback-state-expiry', 'QT612_CALLBACK_STATE_EXPIRY_OK', ()),
    ('sampled-images', 'QT612_SAMPLED_IMAGES_OK', ('rhi',)),
    ('callback-role-span', 'QT612_CALLBACK_ROLE_SPAN_OK', ()),
    ('message-handlers', 'QT612_MESSAGE_HANDLERS_OK', ()),
    ('protected-destructors', 'QT612_PROTECTED_DESTRUCTORS_OK', ()),
    ('accessible-facets', 'QT612_ACCESSIBLE_FACETS_OK', ()),
    ('video-buffers', 'QT612_VIDEO_BUFFERS_OK', ('QtMultimedia',)),
    ('synchronous-references', 'QT612_SYNCHRONOUS_REFERENCES_OK', ('QtSql',)),
    ('module-callbacks', 'QT612_MODULE_CALLBACKS_OK', ('QtScxml', 'QtSerialBus', 'QtDesigner')),
    ('instancing-callbacks', 'QT612_INSTANCING_CALLBACKS_OK', ('QtQuick3D',)),
    ('scxml-event-callbacks', 'QT612_SCXML_EVENT_CALLBACKS_OK', ('QtScxml',)),
    ('operator-callbacks', 'QT612_OPERATOR_CALLBACKS_OK', ('Qt3DRender',)),
    ('function-callbacks', 'QT612_FUNCTION_CALLBACKS_OK', ('QtRemoteObjects', 'QtWebEngineCore')),
    ('webview-unavailable', 'QT612_WEBVIEW_UNAVAILABLE_OK', ('QtWebView',)),
    ('webview-callbacks', 'QT612_WEBVIEW_CALLBACKS_OK', ('QtWebView',)),
    ('rhi-lifetimes', 'QT612_RHI_LIFETIMES_OK', ('rhi',)),
    ('rhi-cleanup', 'QT612_RHI_CLEANUP_OK', ('rhi',)),
]


def runtime_programs(only=(), modules=(), rhi=False, examples=True):
    available = set(modules) | ({'rhi'} if rhi else set())
    programs = []
    if examples:
        programs += [(name, (ROOT / 'examples/qt612' / (name + '.bend')).read_text(), marker)
                     for name, marker in EXAMPLES if not only or name in only]
    programs += [(name, (ROOT / 'scripts/fixtures' / (name + '.bend')).read_text(), marker)
                 for name, marker, needs in FIXTURES
                 if available.issuperset(needs) and (not only or name in only)]
    if only:
        programs = [program for program in programs if program[0] in only]
        missing = set(only) - {program[0] for program in programs}
        if missing:
            raise ValueError('Unknown or unavailable callback fixture: ' + ', '.join(sorted(missing)))
    return programs


# Native probes: maintainer-only effects that make Qt call installed handlers.
UNIT = dict(bend='Unit', raw='Unit')
WORD = dict(bend='U32', raw='U32')
BOOL = dict(bend='Bool', raw='U32')
STRING = dict(kind='string', bend='String', raw='String')


def handle(name):
    return dict(bend=name, raw='U32')


# Shared C++ for the probes, placed after the runtime, before the generated
# dispatch code.
PROBE_SUPPORT = r'''
extern "C" void bqt_abi_call(BqtRequest *);
alignas(NativeTracked<QEvent>) static unsigned char probe_fixed_event[sizeof(NativeTracked<QEvent>)];
static bool probe_fixed_event_active = false;

// The Qt operation this probe runs already has a failed handler.
static bool probe_handler_failed() { return CallFrame::current && CallFrame::current->handler_error; }

static QMetaMethod probe_native_signal(BqtRequest *r, QObject *object) {
    int index = object->metaObject()->indexOfSignal("nativeValues(QPushButton*,QColor,QVariantMap,QVariant,QVariantList)");
    if (index < 0) { fail(r, ENOENT, "Missing typed native signal"); return {}; }
    return object->metaObject()->method(index);
}

static bool probe_emit_native_signal(QObject *object, const QMetaMethod &method, QPushButton *button,
                                     QVariantMap extra = {}) {
    QColor color(Qt::red);
    QChar text_data[] = {QChar('M'), QChar('a'), QChar('p')};
    const QString text = QString::fromRawData(text_data, 3);
    QVariantMap map{{"count", 42}, {"title", text}};
    map.insert(extra);
    QVariant value(text);
    QVariantList list{42};
    bool ok = method.invoke(object, Qt::DirectConnection, Q_ARG(QPushButton*, button), Q_ARG(QColor, color),
        Q_ARG(QVariantMap, map), Q_ARG(QVariant, value), Q_ARG(QVariantList, list));
    std::fill(std::begin(text_data), std::end(text_data), QChar('x'));
    color = Qt::blue; map.clear(); value.clear(); list.clear();
    return ok;
}

// Runs `work` on another thread while the main thread runs a Qt event loop,
// so Qt can bring the calls `work` makes to Bend on the main thread.
template<class Work> static void probe_on_thread(Work &&work)
{
    std::atomic<bool> done{false};
    std::thread worker([&] { work(); done.store(true, std::memory_order_release); });
    QEventLoop loop;
    QTimer timer;
    QObject::connect(&timer, &QTimer::timeout, &loop, [&] { if (done.load(std::memory_order_acquire)) loop.quit(); });
    timer.start(1);
    loop.exec();
    worker.join();
}

// Registers an override object the probe made itself; Bend then installs its
// handlers. Native code keeps ownership.
template<class Base, class Proxy> static uint32_t probe_register(BqtRequest *r, Proxy *value, uint16_t type)
{
    QObject *object = nullptr;
    if constexpr (std::is_base_of_v<QObject, Base>) object = static_cast<QObject *>(value);
    auto id = insert(r, static_cast<Base *>(value), object, type, nullptr, false, NativeTraits<Base>::cast);
    if (r->error) return 0;
    value->bqt_receiver = id;
    callback_observe(id, value->bqt_alive, &value->bqt_handlers);
    if (!object) mark_native_observed(id);
    return id;
}

// Runs a Qt event loop until `ready` answers true, the time is up or a
// handler fails.
static bool probe_wait(const std::function<bool()> &ready, int ms)
{
    QDeadlineTimer deadline(ms);
    while (!ready() && !deadline.hasExpired()) {
        if (probe_handler_failed()) return false;
        QEventLoop loop;
        QTimer::singleShot(1, &loop, &QEventLoop::quit);
        loop.exec();
    }
    return ready();
}
'''

PROBE_GLOBALS = r'''
static uint32_t probe_saved_state = 0;
static uint32_t probe_native_variant = 0;
static uint32_t probe_saved_span = 0;
static uint32_t probe_event_deleted = 0;
static uint32_t rhi_cleanup_hits = 0;
static uint32_t protected_print_engine_deleted = 0;
static uint32_t protected_paint_engine_deleted = 0;
static std::atomic<uint32_t> probe_messages{0};
static QtMessageHandler probe_previous_handler;
class CallbackSurfaceServer : public QTcpServer {
public:
    CallbackSurfaceServer() {
        QObject::connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = nextPendingConnection();
                QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                QObject::connect(socket, &QTcpSocket::readyRead, socket, [socket] {
                    QByteArray request = socket->property("request").toByteArray() + socket->readAll();
                    socket->setProperty("request", request);
                    if (!request.contains("\r\n\r\n") || socket->property("sent").toBool()) return;
                    socket->setProperty("sent", true);
                    const QByteArray body = request.startsWith("HEAD ") ? QByteArray{} : QByteArray("rest-ok");
                    socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
                        + QByteArray::number(body.size()) + "\r\nConnection: close\r\n\r\n" + body);
                    socket->disconnectFromHost();
                });
            }
        });
    }
};
'''


def probe_definitions(g, args, modules, shader_path):
    """(fixtures, public name, params, result, C++ body, has_self)."""
    ids = g.ids
    probes = []

    def add(fixtures, public, params, result, body, has_self=False):
        if isinstance(fixtures, str):
            fixtures = (fixtures,)
        probes.append((fixtures, 'CallbackProbe.' + public, params, result, body, has_self))

    add(('scenegraph-material-render', 'scenegraph-material-instances'), 'materialShaderPrefix', [], STRING,
        'r->result = string_value(QString::fromUtf8(' + json.dumps(str(args.work / 'scenegraph-material')) + ')); return true;')
    add('native-image-plugin', 'imagePluginPath', [], STRING,
        'r->result = string_value(QString::fromUtf8(' + json.dumps(str(args.work / 'image-plugin')) + ')); return true;')

    if 'QAbstractTransition' in ids:
        add('transition-constructors', 'transitionVirtual', [('transition', handle('QAbstractTransition')), ('source', handle('QState'))], BOOL, f'''
    NativeCallScope scope;
    auto *transition = get<QAbstractTransition>(r, r->arguments[0].word, {ids['QAbstractTransition']});
    auto *source = get<QState>(r, r->arguments[1].word, {ids['QState']}, true, false);
    if (r->error) return true;
    struct Access : QAbstractTransition {{
        static auto test() {{ return &Access::eventTest; }}
        static auto run() {{ return &Access::onTransition; }}
    }};
    QEvent event(QEvent::User);
    const bool accepted = (transition->*Access::test())(&event);
    (transition->*Access::run())(&event);
    r->result.word = !accepted && transition->sourceState() == source && transition->parent() == source;
    return true;''')

    add('dynamic-properties', 'dynamicSet', [('object', handle('QObject')), ('name', STRING), ('value', handle('QVariant'))], BOOL, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    auto *value = get<QVariant>(r, r->arguments[2].word, {ids['QVariant']}, false, false);
    if (r->error) return true;
    r->result.word = object->setProperty(r->arguments[1].text, *value);
    return true;''')

    add('convenience-apis', 'contextTranslator', [], handle('QTranslator'), f'''
    struct ContextTranslator : QTranslator {{
        bool isEmpty() const override {{ return false; }}
        QString translate(const char *context, const char *source, const char *, int) const override {{
            return QString::fromUtf8(context) + ':' + QString::fromUtf8(source);
        }}
    }};
    r->result.word = own(r, static_cast<QTranslator *>(new ContextTranslator), {ids['QTranslator']});
    r->result.owned_handle = r->result.word;
    return true;''')

    if 'QPyTextObject' in ids:
        add('qobject-interface-helpers', 'qobjectHelperInterfaces',
            [(name, handle('QObject')) for name in ('text', 'parser', 'source', 'container', 'member', 'property', 'menu')], WORD, f'''
    NativeCallScope scope;
    QObject *values[7] = {{}};
    for (unsigned i = 0; i < 7; ++i) values[i] = get<QObject>(r, r->arguments[i].word, {ids['QObject']});
    if (r->error) return true;
    r->result.word = qobject_cast<QTextObjectInterface *>(values[0]) &&
        qobject_cast<QQmlParserStatus *>(values[1]) && qobject_cast<QQmlPropertyValueSource *>(values[2]) &&
        qobject_cast<QDesignerContainerExtension *>(values[3]) && qobject_cast<QDesignerMemberSheetExtension *>(values[4]) &&
        qobject_cast<QDesignerPropertySheetExtension *>(values[5]) && qobject_cast<QDesignerTaskMenuExtension *>(values[6]);
    return true;''')
        add('qobject-interface-helpers', 'textObjectHelper', [('object', handle('QObject'))], WORD, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    if (r->error) return true;
    auto *interface = qobject_cast<QTextObjectInterface *>(object);
    if (!interface) return fail(r, EINVAL, "Text object has no native interface metadata");
    QTextDocument document;
    QTextCharFormat format; format.setObjectType(QTextFormat::UserObject + 37);
    const QSizeF size = interface->intrinsicSize(&document, 0, format);
    QImage image(100, 100, QImage::Format_ARGB32_Premultiplied); image.fill(Qt::transparent);
    QPainter painter(&image);
    interface->drawObject(&painter, QRectF(0, 0, 19, 27), &document, 0, format);
    document.documentLayout()->registerHandler(QTextFormat::UserObject + 37, object);
    QTextCursor cursor(&document); cursor.insertText(QString(QChar::ObjectReplacementCharacter), format);
    document.adjustSize(); document.drawContents(&painter);
    document.documentLayout()->unregisterHandler(QTextFormat::UserObject + 37, object);
    r->result.word = size == QSizeF(19, 27);
    return true;''')

    add('core-pointer-results', 'cloneableIconEngine', [], handle('QIconEngine'), f'''
    class Engine final : public QIconEngine {{
    public:
        void paint(QPainter *, const QRect &, QIcon::Mode, QIcon::State) override {{}}
        QIconEngine *clone() const override {{ return new Engine(*this); }}
        QString key() const override {{ return QStringLiteral("CorePointerIcon"); }}
        QString iconName() override {{ return QStringLiteral("CorePointerIcon"); }}
    }};
    r->result.word = own(r, static_cast<QIconEngine *>(new Engine), {ids['QIconEngine']});
    r->result.owned_handle = r->result.word;
    return true;''')
    add('core-pointer-results', 'isCloseEvent', [('event', handle('QEvent'))], BOOL, f'''
    NativeCallScope scope;
    auto *event = get<QEvent>(r, r->arguments[0].word, {ids['QEvent']});
    if (r->error) return true;
    r->result.word = dynamic_cast<QCloseEvent *>(event) != nullptr;
    return true;''')

    add(('convenience-apis', 'range-model-versions'), 'rangeNativeEditing', [('model', handle('QRangeModel'))], BOOL, f'''
    NativeCallScope scope;
    auto *model = get<QRangeModel>(r, r->arguments[0].word, {ids['QRangeModel']});
    if (r->error) return true;
    const int row = model->rowCount();
    bool good = model->insertRows(row, 1);
    auto index = model->index(row, 0);
    good = good && model->setData(index, QVariant::fromValue(static_cast<QObject *>(model)));
    good = good && model->data(index).value<QObject *>() == model;
    good = good && model->data(index, Qt::RangeModelDataRole).value<QObject *>() == model;
    good = good && model->setData(index, 81) && model->data(index).toInt() == 81;
    good = good && model->removeRows(row, 1);
    if (model->columnCount() > 1) {{
        good = good && model->insertColumns(1, 1);
        good = good && model->setData(model->index(0, 1), 19) && model->data(model->index(0, 1)).toInt() == 19;
        good = good && model->removeColumns(1, 1);
    }}
    r->result.word = good;
    return true;''')

    add(('convenience-apis', 'range-model-versions'), 'rangeNativeSelf', [('model', handle('QRangeModel'))], BOOL, f'''
    NativeCallScope scope;
    auto *model = get<QRangeModel>(r, r->arguments[0].word, {ids['QRangeModel']});
    if (r->error) return true;
    const auto index = model->index(0, 0);
    r->result.word = model->setData(index, QVariant::fromValue(static_cast<QObject *>(model)));
    return true;''')

    if {'QPrinter', 'QPrintEngine', 'QPaintEngine'}.issubset(ids):
        add('protected-lifetimes', 'ownedPrintEngine', [], handle('QPrintEngine'), f'''
    class Engine final : public QPrintEngine {{
        QHash<int, QVariant> properties;
    public:
        ~Engine() override {{ ++protected_print_engine_deleted; }}
        void setProperty(PrintEnginePropertyKey key, const QVariant &value) override {{ properties.insert(int(key), value); }}
        QVariant property(PrintEnginePropertyKey key) const override {{ return properties.value(int(key)); }}
        bool newPage() override {{ return true; }}
        bool abort() override {{ return true; }}
        int metric(QPaintDevice::PaintDeviceMetric) const override {{ return 96; }}
        QPrinter::PrinterState printerState() const override {{ return QPrinter::Idle; }}
    }};
    r->result.word = own(r, static_cast<QPrintEngine *>(new Engine), {ids['QPrintEngine']});
    r->result.owned_handle = r->result.word;
    return true;''')
        add('protected-lifetimes', 'ownedPaintEngine', [], handle('QPaintEngine'), f'''
    class Engine final : public QPaintEngine {{
    public:
        ~Engine() override {{ ++protected_paint_engine_deleted; }}
        bool begin(QPaintDevice *) override {{ return true; }}
        bool end() override {{ return true; }}
        void updateState(const QPaintEngineState &) override {{}}
        void drawPixmap(const QRectF &, const QPixmap &, const QRectF &) override {{}}
        Type type() const override {{ return User; }}
    }};
    r->result.word = own(r, static_cast<QPaintEngine *>(new Engine), {ids['QPaintEngine']});
    r->result.owned_handle = r->result.word;
    return true;''')
        add('protected-lifetimes', 'printerWithVirtualPaintEngine', [('engine', handle('QPaintEngine'))], handle('QPrinter'), f'''
    NativeCallScope scope;
    auto *engine = get<QPaintEngine>(r, r->arguments[0].word, {ids['QPaintEngine']});
    if (r->error) return true;
    class Printer final : public QPrinter {{
        QPaintEngine *other;
    public:
        explicit Printer(QPaintEngine *value) : other(value) {{}}
        QPaintEngine *paintEngine() const override {{ return other; }}
    }};
    r->result.word = own(r, static_cast<QPrinter *>(new Printer(engine)), {ids['QPrinter']});
    r->result.owned_handle = r->result.word;
    return true;''')
        add('protected-lifetimes', 'printerNativeEngines', [('printer', handle('QPrinter')), ('printing', handle('QPrintEngine')),
                                                        ('painting', handle('QPaintEngine')), ('virtualEngine', handle('QPaintEngine'))], BOOL, f'''
    NativeCallScope scope;
    auto *printer = get<QPrinter>(r, r->arguments[0].word, {ids['QPrinter']});
    auto *printing = get<QPrintEngine>(r, r->arguments[1].word, {ids['QPrintEngine']});
    auto *painting = get<QPaintEngine>(r, r->arguments[2].word, {ids['QPaintEngine']});
    auto *other = get<QPaintEngine>(r, r->arguments[3].word, {ids['QPaintEngine']});
    if (r->error) return true;
    r->result.word = printer->printEngine() == printing && printer->QPrinter::paintEngine() == painting && printer->paintEngine() == other;
    return true;''')
        add('protected-lifetimes', 'printerEngineDestructions', [], WORD, '''
    r->result.word = (protected_print_engine_deleted << 16) | protected_paint_engine_deleted;
    return true;''')

    add('protected-fields', 'foreignFields', [], handle('QObject'), f'''
    r->result.word = own(r, static_cast<QObject *>(new ForeignProtectedFields), {ids['QObject']});
    r->result.owned_handle = r->result.word;
    return true;''')
    add('protected-fields', 'foreignMaterial', [('owner', handle('QObject'))], handle('QSGOpaqueTextureMaterial'), f'''
    NativeCallScope scope;
    auto *owner = get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    auto *fixture = owner ? dynamic_cast<ForeignProtectedFields *>(owner) : nullptr;
    if (r->error) return true;
    if (!fixture) return fail(r, EINVAL, "Not a foreign field fixture");
    auto *material = dynamic_cast<QSGOpaqueTextureMaterial *>(fixture->node.material());
    auto current = +[](BqtRequest *request, uint32_t id) -> const void * {{
        auto *value = protected_fields_owner<QObject>(request, id, {ids['QObject']});
        auto *fixture = value ? dynamic_cast<ForeignProtectedFields *>(value) : nullptr;
        return fixture ? dynamic_cast<QSGOpaqueTextureMaterial *>(fixture->node.material()) : nullptr;
    }};
    r->result.word = protected_fields_borrow(r, material, {ids['QSGOpaqueTextureMaterial']}, r->arguments[0].word, current, false);
    r->result.borrowed_handle = r->result.word;
    return true;''')
    add('protected-fields', 'materialFiltering', [('material', handle('QSGOpaqueTextureMaterial'))], WORD, f'''
    NativeCallScope scope;
    auto *material = get<QSGOpaqueTextureMaterial>(r, r->arguments[0].word, {ids['QSGOpaqueTextureMaterial']}, false, false);
    if (r->error) return true;
    r->result.word = uint32_t(material->filtering());
    return true;''')

    if {'QCanvasRhiPaintDriver', 'QCanvasOffscreenCanvas', 'QRhi'}.issubset(ids):
        add('canvas-grab-callbacks', 'canvasFixture', [], handle('QObject'), f'''
    auto value = std::make_unique<CanvasCallbackFixture>();
    if (!value->rhi || value->canvas.isNull()) return fail(r, EIO, "Cannot create the Null-RHI canvas fixture");
    r->result.word = own(r, static_cast<QObject *>(value.release()), {ids['QObject']});
    r->result.owned_handle = r->result.word;
    return true;''')
        add('canvas-grab-callbacks', 'canvasDriver', [('fixture', handle('QObject'))], handle('QCanvasRhiPaintDriver'), f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    if (r->error) return true;
    auto *fixture = dynamic_cast<CanvasCallbackFixture *>(object);
    if (!fixture) return fail(r, EINVAL, "Not a canvas callback fixture");
    r->result.word = register_native_borrow(r, fixture->factory.paintDriver(), {ids['QCanvasRhiPaintDriver']}, r->arguments[0].word);
    r->result.borrowed_handle = r->result.word;
    return true;''')
        add('canvas-grab-callbacks', 'canvasValue', [('fixture', handle('QObject'))], handle('QCanvasOffscreenCanvas'), f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    if (r->error) return true;
    auto *fixture = dynamic_cast<CanvasCallbackFixture *>(object);
    if (!fixture) return fail(r, EINVAL, "Not a canvas callback fixture");
    r->result.word = own(r, new QCanvasOffscreenCanvas(fixture->canvas), {ids['QCanvasOffscreenCanvas']});
    r->result.owned_handle = r->result.word;
    return true;''')
        add('canvas-grab-callbacks', 'churnReadback', [], UNIT, '''
    static std::vector<QByteArray> buffers;
    for (int i = 0; i < 128; ++i) buffers.push_back(QByteArray(8 * 8 * 4, char(0x7f)));
    return true;''')

    if 'QAbstractOAuth' in ids:
        add('oauth-parameter-callbacks', 'modifyParameters', [('oauth', handle('QAbstractOAuth'))], BOOL, f'''
    NativeCallScope scope;
    auto *oauth = get<QAbstractOAuth>(r, r->arguments[0].word, {ids['QAbstractOAuth']});
    if (r->error) return true;
    const auto function = oauth->modifyParametersFunction();
    if (!function) return fail(r, EINVAL, "No native OAuth parameter function was installed");
    QMultiMap<QString, QVariant> values;
    values.insert(QStringLiteral("kept"), 7);
    function(QAbstractOAuth::Stage::RequestingAccessToken, &values);
    r->result.word = values.value(QStringLiteral("kept")).toInt() == 7
        && values.value(QStringLiteral("added")).toString() == QStringLiteral("new");
    return true;''')
        add('oauth-parameter-callbacks', 'hasModifyParameters', [('oauth', handle('QAbstractOAuth'))], BOOL, f'''
    NativeCallScope scope;
    auto *oauth = get<QAbstractOAuth>(r, r->arguments[0].word, {ids['QAbstractOAuth']});
    if (r->error) return true;
    r->result.word = bool(oauth->modifyParametersFunction());
    return true;''')

    if 'QHttpServer' in ids:
        add('http-server-callbacks', 'httpListen', [('server', handle('QHttpServer'))], BOOL, f'''
    NativeCallScope scope;
    auto *server = get<QHttpServer>(r, r->arguments[0].word, {ids['QHttpServer']});
    if (r->error) return true;
    auto tcp = std::make_unique<QTcpServer>(server);
    if (!tcp->listen(QHostAddress::LocalHost, 0)) return fail(r, EIO, "Cannot listen for HTTP callback fixture");
    server->setProperty("probePort", tcp->serverPort());
    r->result.word = server->bind(tcp.get());
    if (r->result.word) tcp.release();
    return true;''')
        add('http-server-callbacks', 'httpRequest', [('server', handle('QHttpServer')), ('path', STRING)], STRING, f'''
    NativeCallScope scope;
    auto *server = get<QHttpServer>(r, r->arguments[0].word, {ids['QHttpServer']});
    if (r->error) return true;
    const auto path = QString::fromUtf8(r->arguments[1].text, qsizetype(r->arguments[1].size));
    QNetworkAccessManager manager;
    auto *reply = manager.get(QNetworkRequest(QUrl(QStringLiteral("http://127.0.0.1:%1%2")
        .arg(server->property("probePort").toUInt()).arg(path))));
    if (!probe_wait([&] {{ return reply->isFinished(); }}, 3000)) {{
        if (!probe_handler_failed()) return fail(r, ETIMEDOUT, "The HTTP route callback did not finish");
        return true;
    }}
    r->result = string_value(QString::fromUtf8(reply->readAll()) + QStringLiteral("|")
        + QString::fromUtf8(reply->rawHeader("X-Bend")));
    return true;''')

    add('callback-surfaces', 'restServer', [], handle('QTcpServer'), f'''
    auto value = std::make_unique<CallbackSurfaceServer>();
    if (!value->listen(QHostAddress::LocalHost, 0)) return fail(r, EIO, "Cannot start the local REST fixture");
    r->result.word = own(r, static_cast<QTcpServer *>(value.release()), {ids['QTcpServer']});
    r->result.owned_handle = r->result.word;
    return true;''')
    add('callback-surfaces', 'restUrl', [('server', handle('QTcpServer'))], STRING, f'''
    NativeCallScope scope;
    auto *value = get<QTcpServer>(r, r->arguments[0].word, {ids['QTcpServer']});
    if (r->error) return true;
    r->result = string_value(QStringLiteral("http://127.0.0.1:%1/").arg(value->serverPort()));
    return true;''')
    add('callback-surfaces', 'waitCalls', [('object', handle('QObject')), ('count', WORD)], BOOL, f'''
    NativeCallScope scope;
    auto *value = get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    if (r->error) return true;
    r->result.word = probe_wait([&] {{ return value->property("calls").toUInt() == r->arguments[1].word; }}, 3000);
    return true;''')
    add('callback-surfaces', 'finishReply', [('reply', handle('QNetworkReply'))], BOOL, f'''
    NativeCallScope scope;
    auto *value = get<QNetworkReply>(r, r->arguments[0].word, {ids['QNetworkReply']});
    if (r->error) return true;
    r->result.word = probe_wait([&] {{ return value->isFinished(); }}, 3000);
    return true;''')

    add('function-pointer-callbacks', 'constAccessible', [('widget', handle('QWidget'))], handle('QAccessibleInterface'), f'''
    NativeCallScope scope;
    auto *widget = get<QWidget>(r, r->arguments[0].word, {ids['QWidget']});
    if (r->error) return true;
    const auto *value = QAccessible::queryAccessibleInterface(widget);
    r->result.word = NativeFunctionCallbacks::accessible_borrow(r, value);
    r->result.borrowed_handle = r->result.word;
    return true;''')

    add('function-pointer-callbacks', 'accessibleFactoryNamed', [('widget', handle('QWidget')),
        ('name', STRING), ('clear', BOOL)], BOOL, f'''
    NativeCallScope scope;
    auto *widget = get<QWidget>(r, r->arguments[0].word, {ids['QWidget']});
    if (r->error) return true;
    if (r->arguments[2].word) {{
        if (auto *old = QAccessible::queryAccessibleInterface(widget))
            QAccessible::deleteAccessibleInterface(QAccessible::uniqueId(old));
    }}
    auto *value = QAccessible::queryAccessibleInterface(widget);
    const auto expected = QString::fromUtf8(r->arguments[1].text, qsizetype(r->arguments[1].size));
    r->result.word = value && value->text(QAccessible::Name) == expected;
    return true;''')

    add('method-metadata', 'parentMethodDispatch', [('self', handle('QObject'))], BOOL, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    const auto *parent = object->metaObject()->superClass();
    if (!parent) return fail(r, EINVAL, "The override probe needs a Bend parent class");
    const auto method = parent->method(parent->indexOfMethod("compose(QString,int)"));
    QString answer, text = QStringLiteral("native");
    const int count = 7;
    const bool invoked = method.invoke(object, Qt::DirectConnection, Q_RETURN_ARG(QString, answer),
        Q_ARG(QString, text), Q_ARG(int, count));
    r->result.word = invoked && answer == QStringLiteral("derived-native7");
    return true;
''', True)

    add('nondefault-properties', 'nondefaultRead', [('self', handle('QObject'))], BOOL, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    const auto type = QMetaType::fromType<QFontInfo>();
    if (type.isDefaultConstructible()) return fail(r, EINVAL, "The nondefault native probe lost its premise");
    bool good = true;
    for (const char *name : {{"option", "accessor"}}) {{
        auto property = object->metaObject()->property(object->metaObject()->indexOfProperty(name));
        QVariant value = property.read(object);
        if (value.metaType() != type) return fail(r, EINVAL, "Nondefault QMetaProperty::read lost its native type");
        good = good && static_cast<const QFontInfo *>(value.constData())->pixelSize() == 22;
        value = QQmlProperty::read(object, QString::fromUtf8(name));
        if (value.metaType() != type) return fail(r, EINVAL, "Nondefault QQmlProperty::read lost its native type");
        good = good && static_cast<const QFontInfo *>(value.constData())->pixelSize() == 22;
    }}
    auto method = object->metaObject()->method(object->metaObject()->indexOfMethod("optionResult()"));
    QFontInfo output{{QFont()}};
    good = method.invoke(object, Qt::DirectConnection, qReturnArg(output)) && good;
    r->result.word = good && output.pixelSize() == 22;
    return true;''', True)

    method_names = {m['bend_name'] for m in g.methods}
    if {'QTableView.setItemDelegateForRow', 'QMimeData.urls'}.issubset(method_names):
        set_delegate = '@REGISTRY_SET_DELEGATE@'
        get_urls = '@REGISTRY_GET_URLS@'
        add('registry-boundaries', 'retentionAtLimit', [('self', handle('QTableView')), ('fresh', handle('QStyledItemDelegate'))], BOOL, f'''
    NativeCallScope scope;
    auto *view = get<QTableView>(r, r->self, {ids['QTableView']});
    auto *fresh = get<QStyledItemDelegate>(r, r->arguments[0].word, {ids['QStyledItemDelegate']});
    if (r->error) return true;
    while (grow_registry()) {{}}
    struct Reservations {{
        std::vector<uint32_t> indices;
        ~Reservations() {{ for (auto index : indices) retention_reserved[index] = false; }}
    }} reserved;
    for (uint32_t i = 0; i < capacity; ++i) if (!retentions[i].owner && !retention_reserved[i]) {{
        reserved.indices.push_back(i); retention_reserved[i] = true;
    }}
    BqtRequest refused{{}}; refused.scope = r->scope; refused.operation = {set_delegate}; refused.self = r->self;
    refused.arguments[0].word = 1; refused.arguments[1].word = r->arguments[0].word;
    bqt_abi_call(&refused);
    if (refused.error != ENOSPC || view->itemDelegateForRow(1))
        return fail(r, EFAULT, "Full retention admission changed the native row or lost ENOSPC");
    BqtRequest replacement{{}}; replacement.scope = r->scope; replacement.operation = {set_delegate}; replacement.self = r->self;
    replacement.arguments[0].word = 0; replacement.arguments[1].word = r->arguments[0].word;
    bqt_abi_call(&replacement);
    if (replacement.error || view->itemDelegateForRow(0) != fresh)
        return fail(r, EFAULT, "A full retention table could not replace its existing edge");
    r->result.word = 1; return true;''', True)
        add('registry-boundaries', 'outputRollbackAtLimit', [('self', handle('QMimeData'))], BOOL, f'''
    NativeCallScope scope;
    get<QMimeData>(r, r->self, {ids['QMimeData']});
    if (r->error) return true;
    while (grow_registry()) {{}}
    auto live = [] {{ uint32_t count = 0; for (const auto &value : entries) if (value.value) ++count; return count; }};
    uint32_t before = live();
    struct Retired {{
        std::vector<uint32_t> indices;
        ~Retired() {{ for (auto index : indices) entries[index].retired = false; }}
    }} retired;
    bool available = false;
    for (uint32_t i = 1; i < capacity; ++i) if (!entries[i].value && !entries[i].retired) {{
        if (!available) {{ available = true; continue; }}
        retired.indices.push_back(i); entries[i].retired = true;
    }}
    if (!available) return fail(r, ENOSPC, "No slot is available for the partial-output fixture");
    BqtRequest output{{}}; output.scope = r->scope; output.operation = {get_urls}; output.self = r->self;
    bqt_abi_call(&output);
    if (output.error != ENOSPC || live() != before)
        return fail(r, EFAULT, "Partial output at the handle limit failed to roll back");
    r->result.word = 1; return true;''', True)

    add('qt-object-worker', 'memberOnMain', [], BOOL,
        'r->result.word = QThread::currentThread() == main_thread; return true;')
    add('qt-object-worker', 'membersFromWorker', [('self', handle('QObject')), ('reject', BOOL)], BOOL, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    if (!object_move_allowed(r, r->self)) return true;
    bool good = false;
    bool reject = r->arguments[0].word;
    probe_on_thread([&] {{
        auto *worker = QThread::currentThread();
        bool moved = false;
        if (!QMetaObject::invokeMethod(application, [&] {{ moved = object->moveToThread(worker); }}, Qt::BlockingQueuedConnection) || !moved)
            return;
        if (reject) {{
            good = QMetaObject::invokeMethod(object, "failWork", Qt::DirectConnection);
        }} else {{
            good = object->property("stored").toInt() == 5 && object->property("computed").toInt() == 43;
            good = object->setProperty("stored", 41) && good;
            good = object->setProperty("written", 9) && good;
            int output = -1;
            good = QMetaObject::invokeMethod(object, "increment", Qt::DirectConnection,
                Q_RETURN_ARG(int, output), Q_ARG(int, 43)) && output == 44 && good;
            int index = object->metaObject()->indexOfProperty("stored");
            QMetaType type;
            void *arguments[] = {{&type}};
            object->qt_metacall(QMetaObject::RegisterPropertyMetaType, index, arguments);
            good = type == QMetaType::fromType<int>() && good;
        }}
        good = object->moveToThread(main_thread) && good;
    }});
    r->result.word = good;
    return true;''', True)

    add('opaque-data', 'opaqueDropOnWorker', [('value', handle('QVariant'))], UNIT, f'''
    auto *value = get<QVariant>(r, r->arguments[0].word, {ids['QVariant']});
    if (r->error) return true;
    QVariant moved = std::move(*value);
    std::thread worker([payload = std::move(moved)]() mutable {{ payload.clear(); }});
    worker.join();
    return true;''')
    add('opaque-data', 'opaqueSignalFromWorker', [('self', handle('QObject')), ('value', handle('QVariant'))], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    auto *value = get<QVariant>(r, r->arguments[0].word, {ids['QVariant']});
    if (r->error) return true;
    QMetaMethod signal;
    for (int i = object->metaObject()->methodOffset(); i < object->metaObject()->methodCount(); ++i) {{
        auto method = object->metaObject()->method(i);
        if (method.methodType() == QMetaMethod::Signal && method.name() == "delivered") signal = method;
    }}
    if (!signal.isValid() || signal.parameterCount() != 1 || signal.parameterMetaType(0) != value->metaType())
        return fail(r, EINVAL, "Missing typed opaque-data signal");
    QVariant payload = *value;
    QByteArray type = signal.parameterTypes().front();
    bool emitted = false;
    std::thread worker([&] {{ emitted = signal.invoke(object, Qt::DirectConnection, QGenericArgument(type.constData(), payload.constData())); payload.clear(); }});
    worker.join();
    if (!emitted) return fail(r, EIO, "The worker could not emit opaque data");
    return true;''', True)
    add('opaque-data', 'opaqueFlush', [], UNIT,
        'QCoreApplication::sendPostedEvents(nullptr, QEvent::MetaCall); QCoreApplication::processEvents(); return true;')

    add(('custom-signals', 'native-signal-arguments'), 'customRememberConnection', [('connection', dict(bend='Connection', raw='U32'))], UNIT,
        'probe_saved_state = r->arguments[0].word; return true;')
    add('native-signal-arguments', 'nativeSaveVariant', [('value', handle('QVariant'))], UNIT,
        'probe_native_variant = r->arguments[0].word; return true;')
    add('native-signal-arguments', 'nativeSavedVariantExpired', [], BOOL,
        'r->result.word = probe_native_variant && !entry(probe_native_variant); return true;')
    native_objects = f'''NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    auto *button = get<QPushButton>(r, r->arguments[0].word, {ids['QPushButton']});
    if (r->error) return true;
    auto method = probe_native_signal(r, object);
    if (r->error) return true;
'''
    add('native-signal-arguments', 'nativeSignalFromWorker', [('self', handle('QObject')), ('button', handle('QPushButton'))], UNIT,
        native_objects + '''
    bool emitted = false;
    std::thread worker([&] { emitted = probe_emit_native_signal(object, method, button); });
    worker.join();
    if (!emitted) return fail(r, EINVAL, "Cannot invoke typed signal");
    QCoreApplication::processEvents();
    return true;''', True)
    add('native-signal-arguments', 'nativeSignalQueuedDisconnect', [('self', handle('QObject')), ('button', handle('QPushButton'))], UNIT,
        native_objects + '''
    button->setText("before-disconnect");
    std::thread worker([&] { probe_emit_native_signal(object, method, button); });
    worker.join();
    auto *saved = connection(probe_saved_state);
    if (!saved) return fail(r, ESTALE, "Missing native signal connection");
    close_connection(*saved);
    QCoreApplication::processEvents();
    if (button->text() != "before-disconnect") return fail(r, EINVAL, "Disconnected queued handler ran");
    return true;''', True)
    add('native-signal-arguments', 'nativeSignalDeletedArgument', [('self', handle('QObject')), ('nested', BOOL)], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    if (r->arguments[0].word) {{
        QPushButton button;
        auto nested = std::make_unique<QObject>();
        auto method = probe_native_signal(r, object);
        if (r->error) return true;
        QVariantMap extra{{{{"nested", QVariantMap{{{{"objects", QVariantList{{QVariant::fromValue(nested.get())}}}}}}}}}};
        std::thread worker([&] {{ probe_emit_native_signal(object, method, &button, extra); }});
        worker.join();
        nested.reset();
        QCoreApplication::processEvents();
    }} else {{
        int index = object->metaObject()->indexOfSignal("buttonReady(QPushButton*)");
        if (index < 0) return fail(r, ENOENT, "Missing button signal");
        auto method = object->metaObject()->method(index);
        auto button = std::make_unique<QPushButton>();
        std::thread worker([&] {{ method.invoke(object, Qt::DirectConnection, Q_ARG(QPushButton*, button.get())); }});
        worker.join();
        button.reset();
        QCoreApplication::processEvents();
    }}
    return true;''', True)
    add('native-signal-arguments', 'nativeSignalInterop', [('self', handle('QObject')), ('button', handle('QPushButton'))], BOOL,
        native_objects + '''
    bool typed = false;
    QObject context;
    auto connected = QMetaObject::connect(object, method, &context, [&](QPushButton *value) { typed = value == button; });
    if (!connected) return fail(r, EINVAL, "Native QPushButton slot cannot connect");
    QQmlEngine engine;
    engine.rootContext()->setContextProperty("backend", object);
    QQmlComponent component(&engine);
    component.setData(R"QML(import QtQml
import QtQuick
QtObject {
    id: root
    property bool valid: false
    property Connections link: Connections {
        target: backend
        function onNativeValues(button, color, details, value, values) {
            root.valid = button.text === "typed" && String(color) === "#ff0000"
                && details.title === "Map" && details.count === 42 && value === "Map" && values[0] === 42
        }
    }
})QML", QUrl());
    std::unique_ptr<QObject> root(component.create());
    if (!root) return fail(r, EINVAL, "Cannot create native signal QML observer");
    if (!probe_emit_native_signal(object, method, button)) return fail(r, EINVAL, "Cannot emit native signal to QML");
    r->result.word = typed && root->property("valid").toBool();
    return true;''', True)
    add('custom-signals', 'customDisconnectSaved', [], UNIT, '''
    auto *value = connection(probe_saved_state);
    if (!value) return fail(r, ESTALE, "The saved custom signal connection is stale");
    close_connection(*value);
    return true;''')
    add('custom-signals', 'customSignalFromWorker', [('self', handle('QObject'))], WORD, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    int index = object->metaObject()->indexOfSignal("progressChanged(int,QString)");
    if (index < 0) return fail(r, ENOENT, "Missing Bend-declared signal");
    auto method = object->metaObject()->method(index);
    std::thread worker([&] {{
        QChar source[] = {{QChar('W'), QChar('o'), QChar('r'), QChar('k'), QChar('e'), QChar('r')}};
        QString text = QString::fromRawData(source, 6);
        method.invoke(object, Qt::DirectConnection, Q_ARG(int, 42), Q_ARG(QString, text));
        std::fill(std::begin(source), std::end(source), QChar('x'));
    }});
    worker.join();
    QCoreApplication::processEvents();
    r->result.word = 1;
    return true;''', True)

    add('signal-connection-modes', 'rawSnapshots', [('self', handle('QObject'))], WORD, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    char saved_data[] = {{'R', 'a', 'w'}};
    bool stored = object->setProperty("saved", QVariant(QByteArray::fromRawData(saved_data, 3)));
    std::fill(std::begin(saved_data), std::end(saved_data), 'x');
    int index = object->metaObject()->indexOfSignal("rawData(QString,QByteArray,QVariantMap,QVariant)");
    if (index < 0) return fail(r, ENOENT, "Missing raw-data snapshot signal");
    auto method = object->metaObject()->method(index);
    bool emitted = false;
    std::thread worker([&] {{
        QChar text_data[] = {{QChar('R'), QChar('a'), QChar('w')}};
        char byte_data[] = {{'R', 'a', 'w'}};
        QString text = QString::fromRawData(text_data, 3);
        QByteArray bytes = QByteArray::fromRawData(byte_data, 3);
        QVariantMap map{{{{"bytes", bytes}}, {{"text", text}}}};
        QVariant nested(QVariantMap{{{{"values", QVariantList{{text, bytes}}}}}});
        emitted = method.invoke(object, Qt::DirectConnection, Q_ARG(QString, text), Q_ARG(QByteArray, bytes),
            Q_ARG(QVariantMap, map), Q_ARG(QVariant, nested));
        std::fill(std::begin(text_data), std::end(text_data), QChar('x'));
        std::fill(std::begin(byte_data), std::end(byte_data), 'x');
    }});
    worker.join();
    QCoreApplication::processEvents();
    r->result.word = stored && emitted;
    return true;''', True)

    add('metadata-signal-arguments', 'metadataSignalFromWorker', [('self', handle('QObject')),
        ('source', handle('QMetaProperty'))], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    auto *source = get<QMetaProperty>(r, r->arguments[0].word, {ids['QMetaProperty']});
    if (r->error) return true;
    int index = object->metaObject()->indexOfSignal("metadataReady(QMetaProperty)");
    if (index < 0) return fail(r, ENOENT, "Missing metadata signal");
    auto method = object->metaObject()->method(index);
    auto copy = *source;
    std::thread worker([&] {{ method.invoke(object, Qt::DirectConnection, Q_ARG(QMetaProperty, copy)); }});
    worker.join();
    return true;''', True)
    add('metadata-signal-arguments', 'immutableMetadataSignalFromWorker', [('self', handle('QObject'))], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    int index = object->metaObject()->indexOfSignal("metadataReady(QMetaProperty)");
    if (index < 0) return fail(r, ENOENT, "Missing metadata signal");
    auto method = object->metaObject()->method(index);
    auto copy = object->metaObject()->property(object->metaObject()->indexOfProperty("payload"));
    std::thread worker([&] {{ method.invoke(object, Qt::DirectConnection, Q_ARG(QMetaProperty, copy)); }});
    worker.join();
    return true;''', True)
    add('reverse-pointer-callbacks', 'layoutMargins', [('item', handle('QGraphicsLayoutItem'))], BOOL, f'''
    NativeCallScope scope;
    auto *item = get<QGraphicsLayoutItem>(r, r->arguments[0].word, {ids['QGraphicsLayoutItem']});
    if (r->error) return true;
    qreal left = -1, right = -1, bottom = -1;
    item->getContentsMargins(&left, nullptr, &right, &bottom);
    r->result.word = left == 1 && right == 3 && bottom == 4;
    return true;''')
    add('reverse-pointer-callbacks', 'paintLines', [('engine', handle('QPaintEngine')), ('worker', BOOL)], UNIT, f'''
    NativeCallScope scope;
    auto *engine = get<QPaintEngine>(r, r->arguments[0].word, {ids['QPaintEngine']});
    if (r->error) return true;
    auto paint = [&] {{ const QLine values[] = {{QLine(1,2,3,4), QLine(5,6,7,8)}}; engine->drawLines(values, 2); }};
    if (r->arguments[1].word) probe_on_thread(paint); else paint();
    return true;''')
    if 'QGeoServiceProviderFactory' in ids:
        add('reverse-pointer-callbacks', 'geoFactoryOutputs', [('factory', handle('QGeoServiceProviderFactory'))], BOOL, f'''
    NativeCallScope scope;
    auto *factory = get<QGeoServiceProviderFactory>(r, r->arguments[0].word, {ids['QGeoServiceProviderFactory']});
    if (r->error) return true;
    QGeoServiceProvider::Error error = QGeoServiceProvider::NoError;
    QString text;
    bool valid = !factory->createGeocodingManagerEngine({{}}, &error, &text)
        && error == QGeoServiceProvider::NotSupportedError && text == QStringLiteral("Bend provider error");
    error = QGeoServiceProvider::NoError; text.clear();
    valid = valid && !factory->createPlaceManagerEngine({{}}, &error, &text)
        && error == QGeoServiceProvider::NotSupportedError && text == QStringLiteral("Bend provider error");
    error = QGeoServiceProvider::NoError; text.clear();
    valid = valid && !factory->createRoutingManagerEngine({{}}, &error, &text)
        && error == QGeoServiceProvider::NotSupportedError && text == QStringLiteral("Bend provider error");
    valid = valid && !factory->createGeocodingManagerEngine({{}}, nullptr, nullptr);
    r->result.word = valid;
    return true;''')
    if 'QWebEnginePage' in ids:
        add('reverse-pointer-callbacks', 'javascriptPrompt', [('page', handle('QWebEnginePage'))], BOOL, f'''
    NativeCallScope scope;
    auto *page = get<QWebEnginePage>(r, r->arguments[0].word, {ids['QWebEnginePage']});
    if (r->error) return true;
    struct Access : QWebEnginePage {{ static constexpr auto member() {{ return &Access::javaScriptPrompt; }} }};
    QString answer;
    const bool accepted = (page->*Access::member())(QUrl(QStringLiteral("https://bend.example")), QStringLiteral("question"), QStringLiteral("default"), &answer);
    r->result.word = accepted && answer == QStringLiteral("Bend answer");
    return true;''')
    add('qml-list-properties', 'qmlListSignalFromWorker', [('self', handle('QObject')),
        ('value', handle('QVariant'))], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    auto *value = get<QVariant>(r, r->arguments[0].word, {ids['QVariant']}, false, false);
    if (r->error) return true;
    const auto copy = *value;
    int index = object->metaObject()->indexOfSignal("listReady(QQmlListProperty<QPushButton>)");
    if (index < 0) return fail(r, ENOENT, "Missing authored list signal");
    auto method = object->metaObject()->method(index);
    bool delivered = false;
    std::thread worker([&] {{
        delivered = method.invoke(object, Qt::DirectConnection, QGenericArgument(copy.typeName(), copy.constData()));
    }});
    worker.join();
    if (!delivered) return fail(r, EINVAL, "Native worker could not emit the typed list signal");
    return true;''', True)
    add('qml-list-properties', 'qmlListCallbacksFromWorker', [('value', handle('QVariant'))], BOOL, f'''
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->arguments[0].word, {ids['QVariant']}, false, false);
    if (r->error) return true;
    if (value->metaType() != QMetaType::fromType<QQmlListProperty<QPushButton>>())
        return fail(r, EINVAL, "The worker probe needs an exact native QPushButton list");
    auto view = value->value<QQmlListProperty<QPushButton>>();
    bool valid = false;
    probe_on_thread([&] {{ valid = view.count && view.at && view.count(&view) == 1 && view.at(&view, 0); }});
    r->result.word = valid;
    return true;''')
    add('metadata-signal-arguments', 'unknownMetadataSignalFromWorker', [('self', handle('QObject'))], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    int index = object->metaObject()->indexOfSignal("metadataReady(QMetaProperty)");
    if (index < 0) return fail(r, ENOENT, "Missing metadata signal");
    auto method = object->metaObject()->method(index);
    QQmlPropertyMap unobserved;
    unobserved.insert(QStringLiteral("payload"), QStringLiteral("native"));
    auto copy = unobserved.metaObject()->property(unobserved.metaObject()->indexOfProperty("payload"));
    probe_on_thread([&] {{ method.invoke(object, Qt::DirectConnection, Q_ARG(QMetaProperty, copy)); }});
    return true;''', True)
    add('native-pointer-arguments', 'nativePointerFromWorker', [('self', handle('QObject')),
        ('painter', handle('QPainter')), ('device', handle('QPaintDevice')), ('synchronous', BOOL)], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    auto *painter = get<QPainter>(r, r->arguments[0].word, {ids['QPainter']});
    auto *device = get<QPaintDevice>(r, r->arguments[1].word, {ids['QPaintDevice']});
    if (r->error) return true;
    int index = object->metaObject()->indexOfSignal("nativePointers(QPainter*,QPaintDevice*,QSGNode*)");
    if (index < 0) return fail(r, ENOENT, "Missing native pointer signal");
    auto method = object->metaObject()->method(index);
    auto emit_signal = [&] {{
        QSGNode *node = nullptr;
        method.invoke(object, Qt::DirectConnection, Q_ARG(QPainter*, painter), Q_ARG(QPaintDevice*, device), Q_ARG(QSGNode*, node));
    }};
    if (r->arguments[2].word) probe_on_thread(emit_signal);
    else {{ std::thread worker(emit_signal); worker.join(); }}
    return true;''', True)
    add('native-pointer-arguments', 'nativePointerUnregistered', [('self', handle('QObject')), ('unknown', BOOL)], UNIT, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    int index = object->metaObject()->indexOfSignal("nativePointers(QPainter*,QPaintDevice*,QSGNode*)");
    if (index < 0) return fail(r, ENOENT, "Missing native pointer signal");
    auto method = object->metaObject()->method(index);
    QPainter local_painter;
    QImage local_image;
    QPainter *painter = r->arguments[0].word ? reinterpret_cast<QPainter *>(uintptr_t(0x42)) : &local_painter;
    QPaintDevice *device = &local_image;
    QSGNode *node = nullptr;
    method.invoke(object, Qt::DirectConnection, Q_ARG(QPainter*, painter), Q_ARG(QPaintDevice*, device), Q_ARG(QSGNode*, node));
    return true;''', True)
    add('native-pointer-arguments', 'nativePointerDeleteEvent', [('value', handle('QEvent'))], UNIT, f'''
    auto *value = get<QEvent>(r, r->arguments[0].word, {ids['QEvent']});
    if (r->error) return true;
    std::thread worker([value] {{ delete value; }});
    worker.join();
    return true;''')
    add('native-pointer-arguments', 'nativePointerObservationCount', [], WORD, '''
    auto &state = native_pointer_index();
    QMutexLocker lock(&state.mutex);
    r->result.word = uint32_t(state.values.size());
    return true;''')
    add('native-pointer-arguments', 'nativeFixedEvent', [], handle('QEvent'), f'''
    if (probe_fixed_event_active) return fail(r, EBUSY, "The fixed-address event is still alive");
    auto *value = new(probe_fixed_event) NativeTracked<QEvent>(QEvent::User);
    probe_fixed_event_active = true;
    auto destroy = +[](void *pointer) {{
        static_cast<NativeTracked<QEvent> *>(pointer)->~NativeTracked<QEvent>();
        probe_fixed_event_active = false;
    }};
    r->result.word = insert(r, static_cast<QEvent *>(value), nullptr, {ids['QEvent']}, destroy, true, NativeTraits<QEvent>::cast);
    r->result.owned_handle = r->result.word;
    return true;''')

    add('custom-signals', 'customSignalInterop', [('self', handle('QObject'))], WORD, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    auto *meta = object->metaObject();
    int index = meta->indexOfSignal("progressChanged(int,QString)");
    if (index < 0) return fail(r, ENOENT, "Missing Bend-declared signal");
    auto signal = meta->method(index);
    QTimer timer;
    auto start = timer.metaObject()->method(timer.metaObject()->indexOfSlot("start(int)"));
    auto connection = QObject::connect(object, signal, &timer, start);
    if (!connection) return fail(r, EINVAL, "Custom signal cannot connect to a Qt slot");
    QQmlEngine engine;
    engine.rootContext()->setContextProperty("backend", object);
    QQmlComponent component(&engine);
    component.setData(R"QML(import QtQml
QtObject {{
    id: root
    property int received: 0
    property string title: ""
    property Connections connection: Connections {{
        target: backend
        function onProgressChanged(value, label) {{ root.received = value; root.title = label }}
    }}
}})QML", QUrl());
    std::unique_ptr<QObject> root(component.create());
    if (!root) return fail(r, EINVAL, "QML could not observe the custom signal");
    if (!signal.invoke(object, Qt::DirectConnection, Q_ARG(int, 42), Q_ARG(QString, QString("Native"))))
        return fail(r, EINVAL, "Qt could not invoke the custom signal");
    if (!timer.isActive() || timer.interval() != 42 || root->property("received").toInt() != 42 || root->property("title").toString() != "Native")
        return fail(r, EINVAL, "Qt or QML missed the custom signal");
    std::thread worker([&] {{
        QString text = "Worker";
        signal.invoke(object, Qt::DirectConnection, Q_ARG(int, 43), Q_ARG(QString, text));
        text.fill('x');
    }});
    worker.join();
    QCoreApplication::processEvents();
    if (timer.interval() != 43 || root->property("received").toInt() != 43 || root->property("title").toString() != "Worker")
        return fail(r, EINVAL, "Queued custom signal arguments were not copied");
    r->result.word = 1;
    return true;''', True)

    add('synchronous-signals', 'authentication', [('self', handle('QNetworkAccessManager'))], WORD, f'''
    NativeCallScope scope;
    auto *manager = get<QNetworkAccessManager>(r, r->self, {ids['QNetworkAccessManager']});
    if (r->error) return true;
    QAuthenticator authenticator;
    authenticator.setRealm(QStringLiteral("Bend native authentication fixture"));
    manager->authenticationRequired(nullptr, &authenticator);
    r->result.word = authenticator.user() == QStringLiteral("bend-user") &&
        authenticator.password() == QStringLiteral("bend-password") &&
        authenticator.realm() == QStringLiteral("Bend native authentication fixture");
    return true;''', True)

    add('synchronous-signals', 'authenticationOnThread', [('self', handle('QNetworkAccessManager'))], WORD, f'''
    NativeCallScope scope;
    auto *manager = get<QNetworkAccessManager>(r, r->self, {ids['QNetworkAccessManager']});
    if (r->error) return true;
    QAuthenticator authenticator;
    authenticator.setRealm(QStringLiteral("Bend native authentication fixture"));
    probe_on_thread([&] {{ manager->authenticationRequired(nullptr, &authenticator); }});
    r->result.word = authenticator.user() == QStringLiteral("bend-user") &&
        authenticator.password() == QStringLiteral("bend-password");
    return true;''', True)

    add('image-provider-callbacks', 'imageProvider', [('self', handle('QQuickImageProvider')), ('invalid', WORD)], WORD, f'''
    NativeCallScope scope;
    auto *provider = get<QQuickImageProvider>(r, r->self, {ids['QQuickImageProvider']});
    if (r->error) return true;
    if (r->arguments[0].word) {{
        provider->requestImage(QStringLiteral("null-invalid"), nullptr, QSize(4, 3));
        return true;
    }}
    QSize size(1, 2);
    auto image = provider->requestImage(QStringLiteral("image"), &size, QSize(4, 3));
    auto no_size = provider->requestImage(QStringLiteral("null"), nullptr, QSize(4, 3));
    r->result.word = image.size() == QSize(4, 3) && size == QSize(4, 3) && no_size.size() == QSize(4, 3);
    return true;''', True)

    add('async-image-provider', 'asyncImage', [('engine', handle('QQmlEngine')), ('probe', handle('QObject'))], BOOL, f'''
    NativeCallScope scope;
    auto *engine = get<QQmlEngine>(r, r->arguments[0].word, {ids['QQmlEngine']});
    auto *probe = get<QObject>(r, r->arguments[1].word, {ids['QObject']});
    if (r->error) return true;
    QQuickWindow window;
    window.resize(16, 16);
    QQmlComponent component(engine);
    component.setData(R"qml(import QtQuick
Image {{ width: 16; height: 16; cache: false; source: "image://bend-async/ready" }}
)qml", QUrl(QStringLiteral("file:///bend/async-image.qml")));
    if (component.isError()) return fail(r, EINVAL, "The QML async image component failed");
    std::unique_ptr<QObject> root(component.create());
    auto *image = qobject_cast<QQuickItem *>(root.get());
    if (!image) return fail(r, EINVAL, "The QML async image was not created");
    image->setParentItem(window.contentItem());
    window.show();
    if (!probe_wait([&] {{ return image->property("status").toInt() == 1; }}, 10000))
        return fail(r, ETIMEDOUT, "QML did not consume the Bend image response");
    const auto pixels = window.grabWindow();
    if (pixels.isNull() || pixels.pixelColor(4, 4) != QColor(Qt::red))
        return fail(r, EIO, "The Bend async image did not render red pixels");
    image->setProperty("source", QUrl(QStringLiteral("image://bend-async/cancel")));
    if (!probe_wait([&] {{ return probe->objectName() == QStringLiteral("pending"); }}, 10000))
        return fail(r, ETIMEDOUT, "QML did not request the cancellable Bend image");
    auto *response = get<QQuickImageResponse>(r, probe->property("pendingResponse").toUInt(), {ids['QQuickImageResponse']});
    if (r->error) return true;
    QPointer<QQuickImageResponse> pending_response(response);
    image->setProperty("source", QUrl());
    r->result.word = probe_wait([&] {{ return pending_response.isNull() && probe->objectName() == QStringLiteral("cancelled"); }}, 10000);
    window.hide();
    root.reset();
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    collect_pending();
    return true;''')

    add('texture-provider-callbacks', 'textureProvider', [('self', handle('QQuickImageProvider'))], WORD, f'''
    NativeCallScope scope;
    auto *provider = get<QQuickImageProvider>(r, r->self, {ids['QQuickImageProvider']});
    if (r->error) return true;
    QSize size(1, 2);
    auto *factory = provider->requestTexture(QStringLiteral("texture"), &size, QSize(4, 3));
    r->result.word = factory && factory->textureSize() == QSize(4, 3) && size == QSize(4, 3);
    delete factory; // Qt's pixmap cache owns the returned factory.
    return true;''', True)

    add('callback-retention-cycle', 'prepareCycle', [('self', handle('QWindow')), ('owner', handle('QObject'))], UNIT, f'''
    NativeCallScope scope;
    get<QWindow>(r, r->self, {ids['QWindow']});
    get<QObject>(r, r->arguments[0].word, {ids['QObject']});
    if (r->error) return true;
    BqtRequest link{{}}; link.self = r->arguments[0].word;
    int index = prepare_retention(&link, 0xffffffedu, 0, r->self);
    if (link.error) return fail(r, link.error, link.message);
    commit_retention(index, link.self, 0xffffffedu, 0, r->self, nullptr);
    return true;''', True)

    add('device-callbacks', 'device', [('self', handle('QIODevice')), ('mode', WORD)], WORD, f'''
    NativeCallScope scope;
    auto *device = get<QIODevice>(r, r->self, {ids['QIODevice']});
    if (r->error) return true;
    if (!device->open(QIODevice::ReadWrite | QIODevice::Unbuffered)) return fail(r, EIO, "Cannot open the probe device");
    const uint32_t mode = r->arguments[0].word;
    char storage[5] = {{'?', '?', '?', '?', '?'}};
    if (mode == 0) {{
        auto count = device->read(storage + 1, 3);
        auto written = device->write("x\\0y", 3);
        r->result.word = count == 3 && written == 3 && storage[0] == '?' && storage[1] == 'a' &&
                         storage[2] == 0 && storage[3] == 'b' && storage[4] == '?';
    }} else if (mode == 3) {{
        device->write("x", 1);
    }} else {{
        auto count = device->read(storage + 1, mode);
        if (std::memcmp(storage, "?????", 5)) {{ device->close(); return fail(r, EFAULT, "A rejected read changed the native buffer"); }}
        if (mode == 4) r->result.word = count == -1;
    }}
    device->close();
    return true;''', True)

    add('accessible-callbacks', 'accessibleText', [('self', handle('QAccessibleTextInterface')), ('invalid', WORD)], WORD, f'''
    NativeCallScope scope;
    auto *text = get<QAccessibleTextInterface>(r, r->self, {ids['QAccessibleTextInterface']});
    if (r->error) return true;
    int start = 123, end = 456;
    if (r->arguments[0].word) {{
        text->selection(99, nullptr, &end);
        if (end != 456) return fail(r, EFAULT, "A rejected reply changed a native output");
        return true;
    }}
    auto attributes = text->attributes(5, &start, &end);
    bool valid = attributes == QStringLiteral("weight:bold") && start == 2 && end == 9;
    text->selection(0, &start, &end);
    valid = valid && start == 1 && end == 4;
    text->selection(0, nullptr, &end);
    text->selection(0, nullptr, nullptr);
    r->result.word = valid && end == 4;
    return true;''', True)

    add('accessible-callbacks', 'accessibleItems', [('self', handle('QAccessibleSelectionInterface'))], WORD, f'''
    NativeCallScope scope;
    auto *selection = get<QAccessibleSelectionInterface>(r, r->self, {ids['QAccessibleSelectionInterface']});
    if (r->error) return true;
    auto first = selection->selectedItems();
    if (probe_handler_failed()) return true;
    auto second = selection->selectedItems();
    r->result.word = first.size() == 2 && second.size() == 2 && first[0] && first[1] && second[0] && second[1] &&
                     first[0] != first[1] && second[0] != second[1] && first[0] != second[0] && first[1] != second[1];
    return true;''', True)

    add('qml-interface-callbacks', 'qmlInterface', [('self', handle('QQmlExtensionInterface'))], UNIT, f'''
    NativeCallScope scope;
    auto *extension = get<QQmlExtensionInterface>(r, r->self, {ids['QQmlExtensionInterface']});
    if (r->error) return true;
    QQmlEngine engine;
    extension->registerTypes("org.Bend.\\xc3\\xa4");
    extension->registerTypes("");
    extension->registerTypes(nullptr);
    extension->initializeEngine(&engine, "org.Bend.\\xc3\\xa4");
    extension->initializeEngine(&engine, nullptr);
    return true;''', True)

    # Scene graph objects exist only while the GUI thread renders: the probe
    # makes them in a render scope and Bend installs their handlers.
    for public, name in [('newRenderState', 'QSGRenderNode::RenderState'), ('newRenderMaterial', 'QSGMaterial'),
                         ('newRenderText', 'QSGTextNode')]:
        add('render-value-callbacks', public, [], handle(name.replace('::', '.')), f'''
    GuiRenderScope render(r, 0);
    if (!render.active) return true;
    auto *value = new BqtProxy_{callbacks.ident(name)}();
    r->result.word = probe_register<{name}>(r, value, {ids[name]});
    if (r->error) delete value;
    return true;''')
    add('render-value-callbacks', 'renderValues', [('state', handle('QSGRenderNode.RenderState')),
        ('material', handle('QSGMaterial')), ('text', handle('QSGTextNode')), ('marker', handle('QObject'))], WORD, f'''
    NativeCallScope native_scope;
    GuiRenderScope render(r, 0);
    if (!render.active) return true;
    auto *state = get<QSGRenderNode::RenderState>(r, r->arguments[0].word, {ids['QSGRenderNode::RenderState']});
    auto *material = get<QSGMaterial>(r, r->arguments[1].word, {ids['QSGMaterial']});
    auto *text = get<QSGTextNode>(r, r->arguments[2].word, {ids['QSGTextNode']});
    auto *marker = get<QObject>(r, r->arguments[3].word, {ids['QObject']});
    if (r->error) return true;
    auto *first = state->clipRegion();
    auto *second = state->clipRegion();
    auto *matrix = state->projectionMatrix();
    bool valid = first && second && matrix && first != second && first->isEmpty() && second->isEmpty() && matrix->isIdentity();
    auto count = callback_material_types().size();
    auto *type1 = material->type();
    auto *type2 = material->type();
    valid = valid && type1 && type1 == type2 && callback_material_types().size() == count + 1;
    QTextLayout layout;
    text->addTextLayout(QPointF(), &layout);
    r->result.word = valid && marker->objectName() == QStringLiteral("private_virtual");
    delete state;
    delete material;
    delete text;
    collect_pending();
    return true;''')

    add('editor-factory-callbacks', 'editorFactory', [('self', handle('QItemEditorFactory'))], WORD, f'''
    NativeCallScope scope;
    auto *factory = get<QItemEditorFactory>(r, r->self, {ids['QItemEditorFactory']});
    if (r->error) return true;
    auto property = factory->valuePropertyName(7);
    auto *editor = factory->createEditor(7, nullptr);
    r->result.word = property == QByteArray("test") && editor && !editor->parent();
    delete editor;
    return true;''', True)

    add('icon-hooks', 'iconHooks', [('self', handle('QIconEngine'))], WORD, f'''
    NativeCallScope scope;
    auto *self = get<QIconEngine>(r, r->self, {ids['QIconEngine']});
    if (r->error) return true;
    bool initial = true;
    self->virtual_hook(QIconEngine::IsNullHook, &initial);
    if (initial) return fail(r, EINVAL, "The null hook did not update its bool");
    QIconEngine::ScaledPixmapArgument data;
    data.mode = QIcon::Active; data.state = QIcon::On; data.size = QSize(7, 9);
    data.scale = 2.0; data.pixmap = QPixmap(3, 5);
    self->virtual_hook(QIconEngine::ScaledPixmapHook, &data);
    if (data.pixmap.size() != QSize(11, 13) || data.size != QSize(7, 9) ||
        data.mode != QIcon::Active || data.state != QIcon::On || data.scale != 2.0)
        return fail(r, EINVAL, "The scaled-pixmap hook lost its inputs or output pixels");
    self->virtual_hook(1024, nullptr);
    r->result.word = 1;
    return true;''', True)

    add('callback-state-expiry', 'captureState', [('state', handle('QSGMaterialShader.RenderState'))], UNIT, f'''
    get<QSGMaterialShader::RenderState>(r, r->arguments[0].word, {ids['QSGMaterialShader::RenderState']});
    if (r->error) return true;
    probe_saved_state = r->arguments[0].word;
    return true;''')
    add(('callback-state-expiry', 'sampled-images'), 'newShader', [], handle('QSGMaterialShader'), f'''
    GuiRenderScope render(r, 0);
    if (!render.active) return true;
    auto *value = new BqtProxy_QSGMaterialShader();
    r->result.word = probe_register<QSGMaterialShader>(r, value, {ids['QSGMaterialShader']});
    if (r->error) delete value;
    return true;''')
    add('callback-state-expiry', 'stateExpiry', [('shader', handle('QSGMaterialShader'))], handle('QSGMaterialShader.RenderState'), f'''
    NativeCallScope scope;
    GuiRenderScope render(r, 0);
    if (!render.active) return true;
    auto *shader = get<QSGMaterialShader>(r, r->arguments[0].word, {ids['QSGMaterialShader']});
    if (r->error) return true;
    probe_saved_state = 0;
    // A default state: the handler copies it and never reads renderer data.
    QSGMaterialShader::RenderState state;
    shader->updateUniformData(state, nullptr, nullptr);
    delete shader;
    collect_pending();
    if (probe_handler_failed()) return true;
    r->result.word = probe_saved_state;
    if (!r->result.word) return fail(r, EINVAL, "The handler did not keep its state copy");
    return true;''')

    add('callback-role-span', 'captureSpan', [('span', handle('QModelRoleDataSpan'))], UNIT,
        'probe_saved_span = r->arguments[0].word; return true;')
    add('callback-role-span', 'roleSpan', [('self', handle('QAbstractListModel'))], handle('QModelRoleDataSpan'), f'''
    NativeCallScope scope;
    auto *model = get<QAbstractListModel>(r, r->self, {ids['QAbstractListModel']});
    if (r->error) return true;
    probe_saved_span = 0;
    QModelRoleData roles[] = {{QModelRoleData(Qt::DisplayRole)}};
    model->multiData(QModelIndex(), QModelRoleDataSpan(roles, 1));
    if (probe_handler_failed()) return true;
    if (roles[0].data().toString() != QStringLiteral("Bend role")) return fail(r, EINVAL, "The handler did not change the native role span");
    r->result.word = probe_saved_span;
    if (!r->result.word) return fail(r, EINVAL, "The handler did not keep a span copy");
    return true;''', True)

    if shader_path:
        name = json.dumps(str(shader_path))
        add('sampled-images', 'samplerPath', [], STRING, f'r->result = string_value(QString::fromUtf8({name})); return true;')
        add('sampled-images', 'samplerShader', [], handle('QShader'), f'''
    QFile file(QString::fromUtf8({name}));
    if (!file.open(QIODevice::ReadOnly)) return fail(r, EIO, "The probe shader file is missing");
    r->result.word = own(r, new QShader(QShader::fromSerialized(file.readAll())), {ids['QShader']});
    return true;''')
        add('sampled-images', 'prepareSampler', [('self', handle('QSGMaterialShader'))], WORD, f'''
    NativeCallScope scope;
    auto *shader = get<QSGMaterialShader>(r, r->arguments[0].word, {ids['QSGMaterialShader']});
    if (r->error) return true;
    QSGMaterialShaderPrivate::get(shader)->prepare(QShader::StandardShader);
    r->result.word = shader->combinedImageSamplerCount(1);
    return true;''')
        add('sampled-images', 'newSamplerBase', [], handle('QSGMaterialShader'), f'''
    if (!gui_render_depth) return fail(r, EPERM, "The probe shader needs a render scope");
    class Shader : public QSGMaterialShader {{ public: using QSGMaterialShader::setShaderFileName; }};
    auto shader = std::make_unique<NativeTracked<Shader>>();
    shader->setShaderFileName(QSGMaterialShader::FragmentStage, QString::fromUtf8({name}));
    QSGMaterialShaderPrivate::get(shader.get())->prepare(QShader::StandardShader);
    r->result.word = own<QSGMaterialShader>(r, shader.release(), {ids['QSGMaterialShader']});
    mark_native_observed(r->result.word);
    return true;''')
        add('sampled-images', 'newSampledTexture', [], handle('QSGTexture'), f'''
    if (!gui_render_depth) return fail(r, EPERM, "The probe texture needs a render scope");
    r->result.word = own<QSGTexture>(r, new SampledTextureProbe, {ids['QSGTexture']});
    return true;''')
        add('sampled-images', 'sampledImages', [('shader', handle('QSGMaterialShader')), ('mode', WORD)], WORD, f'''
    NativeCallScope scope;
    GuiRenderScope render(r, 0);
    if (!render.active) return true;
    auto *shader = dynamic_cast<BqtProxy_QSGMaterialShader *>(get<QSGMaterialShader>(r, r->arguments[0].word, {ids['QSGMaterialShader']}));
    if (r->error) return true;
    if (!shader) return fail(r, EINVAL, "The probe needs a Bend override shader");
    shader->bqt_shader_file(QSGMaterialShader::FragmentStage, QString::fromUtf8({name}));
    QSGMaterialShaderPrivate::get(shader)->prepare(QShader::StandardShader);
    if (shader->combinedImageSamplerCount(1) != 2) return fail(r, EINVAL, "Shader reflection did not expose two samplers");
    uint32_t before = sampled_texture_deleted;
    SampledTextureProbe existing;
    QSGTexture *images[2]{{nullptr, &existing}};
    QSGMaterialShader::RenderState state;
    QSGFlatColorMaterial material;
    shader->updateSampledImage(state, 1, images, &material, nullptr);
    if (r->arguments[1].word) {{
        if (!probe_handler_failed() || images[0] || images[1] != &existing) return fail(r, EFAULT, "A rejected reply changed the native array");
        CallFrame::current->handler_error = 0;
    }} else {{
        if (probe_handler_failed()) return true;
        if (!images[0] || images[1] != &existing || sampled_texture_deleted != before)
            return fail(r, EFAULT, "Retained textures changed before the shader was destroyed");
    }}
    delete shader;
    collect_pending();
    r->result.word = sampled_texture_deleted - before;
    return true;''')

    add('message-handlers', 'prepareMessages', [], UNIT, '''
    probe_messages = 0;
    probe_previous_handler = qInstallMessageHandler(+[](QtMsgType, const QMessageLogContext &, const QString &) {
        probe_messages.fetch_add(1, std::memory_order_acq_rel);
    });
    return true;''')
    add('message-handlers', 'restoreMessages', [], UNIT, '''
    qInstallMessageHandler(probe_previous_handler);
    return true;''')
    add('message-handlers', 'emitMessage', [('thread', BOOL)], WORD, '''
    auto emit_message = [] {
        QByteArray file("bend-native.cpp"), function("nativeMessage"), category("bend.fixture");
        QMessageLogger(file.constData(), 27, function.constData(), category.constData()).warning("Bend native \\u03bb");
    };
    auto before = probe_messages.load(std::memory_order_acquire);
    if (r->arguments[0].word) { std::thread other(emit_message); other.join(); }
    else emit_message();
    r->result.word = probe_messages.load(std::memory_order_acquire) - before;
    return true;''')

    add('protected-destructors', 'accessibleOwnership', [('self', handle('QAccessibleWidget')), ('native_delete', BOOL)], UNIT, f'''
    auto *self = get<QAccessibleWidget>(r, r->self, {ids['QAccessibleWidget']});
    if (r->error) return true;
    if (!self->isValid() || !self->object()) return fail(r, EINVAL, "The protected-destructor constructor lost its QWidget");
    if (r->arguments[0].word) {{
        if (!can_transfer_handle(r, r->self)) return true;
        auto native = QAccessible::registerAccessibleInterface(self);
        if (!native) return fail(r, EINVAL, "Qt accessible registration failed");
        set_owned(r->self, false);
        QAccessible::deleteAccessibleInterface(native);
        if (entry(r->self)) return fail(r, EINVAL, "Native deletion of a protected-destructor object was not observed");
    }}
    return true;''', True)

    if 'QtMultimedia' in modules:
        add('video-buffers', 'videoFailAllocation', [], UNIT, 'video_probe_fail_allocation = true; return true;')
        add('video-buffers', 'videoThread', [('buffer', handle('QAbstractVideoBuffer'))], WORD, f'''
    NativeCallScope scope;
    auto *buffer = get<QAbstractVideoBuffer>(r, r->arguments[0].word, {ids['QAbstractVideoBuffer']});
    if (r->error) return true;
    QAbstractVideoBuffer::MapData data;
    probe_on_thread([&] {{ data = buffer->map(QVideoFrame::ReadOnly); buffer->unmap(); }});
    r->result.word = uint32_t(data.planeCount);
    return true;''')

    if 'QtSql' in modules:
        add('synchronous-references', 'reference', [('self', handle('QSqlTableModel'))], WORD, f'''
    NativeCallScope scope;
    auto *model = get<QSqlTableModel>(r, r->self, {ids['QSqlTableModel']});
    if (r->error) return true;
    QSqlRecord record;
    record.append(QSqlField(QStringLiteral("score"), QMetaType::fromType<int>()));
    record.setValue(QStringLiteral("score"), 1);
    model->beforeInsert(record);
    r->result.word = record.value(QStringLiteral("score")).toInt() == 42;
    return true;''', True)

    if 'QCanBusFactory' in ids and 'QScxmlDataModel' in ids:
        add('module-callbacks', 'canFactory', [('self', handle('QCanBusFactory'))], WORD, f'''
    NativeCallScope scope;
    auto *factory = get<QCanBusFactory>(r, r->self, {ids['QCanBusFactory']});
    if (r->error) return true;
    QString error;
    auto *device = factory->createDevice(QStringLiteral("virtual"), &error);
    bool valid = device && error == QStringLiteral("created");
    delete device;
    auto devices = factory->availableDevices(&error);
    r->result.word = valid && devices.isEmpty() && error == QStringLiteral("queried");
    return true;''', True)
        add('module-callbacks', 'scxmlModel', [('self', handle('QScxmlDataModel'))], WORD, f'''
    NativeCallScope scope;
    auto *model = get<QScxmlDataModel>(r, r->self, {ids['QScxmlDataModel']});
    if (r->error) return true;
    bool ok = false;
    bool value = model->evaluateToBool(7, &ok);
    bool valid = ok && value;
    auto text = model->evaluateToString(7, &ok);
    r->result.word = valid && ok && text == QStringLiteral("answer");
    return true;''', True)
        add('module-callbacks', 'scxmlLoader', [('self', handle('QScxmlCompiler.Loader'))], WORD, f'''
    NativeCallScope scope;
    auto *loader = get<QScxmlCompiler::Loader>(r, r->self, {ids['QScxmlCompiler::Loader']});
    if (r->error) return true;
    QStringList errors;
    auto data = loader->load(QStringLiteral("source"), QStringLiteral("base"), &errors);
    r->result.word = data == QByteArray("ok") && errors == QStringList{{QStringLiteral("diagnostic")}};
    return true;''', True)
    if 'QDesignerFormWindowInterface' in ids:
        # PySide omits two opaque pure virtuals, so the generated override
        # cannot be built; this probe completes it.
        add('module-callbacks', 'newDesignerForm', [], handle('QDesignerFormWindowInterface'), f'''
    class ConcreteForm : public BqtProxy_QDesignerFormWindowInterface {{
    public:
        using BqtProxy_QDesignerFormWindowInterface::BqtProxy_QDesignerFormWindowInterface;
        QtResourceSet *resourceSet() const override {{ return nullptr; }}
        void setResourceSet(QtResourceSet *) override {{}}
    }};
    auto *form = new ConcreteForm();
    r->result.word = probe_register<QDesignerFormWindowInterface>(r, form, {ids['QDesignerFormWindowInterface']});
    if (r->error) delete form;
    return true;''')
        add('module-callbacks', 'designerSelection', [('self', handle('QDesignerFormWindowInterface'))], WORD, f'''
    NativeCallScope scope;
    auto *form = get<QDesignerFormWindowInterface>(r, r->self, {ids['QDesignerFormWindowInterface']});
    if (r->error) return true;
    QWidget first, second;
    QList<QWidget *> widgets{{&first, &second}};
    form->simplifySelection(&widgets);
    r->result.word = widgets.size() == 1 && widgets[0] == &second;
    delete form;
    return true;''', True)

    if 'QQuick3DInstancing' in ids:
        add('instancing-callbacks', 'instancing', [('self', handle('QQuick3DInstancing'))], WORD, f'''
    NativeCallScope scope;
    auto *instancing = get<QQuick3DInstancing>(r, r->self, {ids['QQuick3DInstancing']});
    if (r->error) return true;
    int count = 123;
    auto data = instancing->instanceBuffer(&count);
    if (probe_handler_failed()) {{
        if (count != 123) return fail(r, EFAULT, "A rejected instance count reached native code");
        return true;
    }}
    r->result.word = count == 0 && data.isEmpty();
    return true;''', True)

    if 'QScxmlEvent' in ids:
        add('scxml-event-callbacks', 'scxmlEvent', [], handle('QScxmlEvent'), f'''
    probe_event_deleted = 0;
    auto event = std::make_unique<QScxmlEvent>();
    event->setName(QStringLiteral("owned event"));
    event->setData(QVariant::fromValue(std::shared_ptr<int>(new int(1), [](int *value) {{ ++probe_event_deleted; delete value; }})));
    r->result.word = own(r, event.release(), {ids['QScxmlEvent']});
    return true;''')
        add('scxml-event-callbacks', 'scxmlDeleted', [], WORD, 'r->result.word = probe_event_deleted; return true;')

    if 'Qt3DRender::QTextureImageDataGenerator' in ids:
        add('operator-callbacks', 'operators', [('self', handle('Qt3DRender.QTextureImageDataGenerator')), ('thread', BOOL)], WORD, f'''
    NativeCallScope scope;
    auto *generator = get<Qt3DRender::QTextureImageDataGenerator>(r, r->self, {ids['Qt3DRender::QTextureImageDataGenerator']});
    if (r->error) return true;
    uint32_t valid = 0;
    auto run = [&] {{
        auto result = (*generator)();
        valid = result && result->width() == 16 && (*generator == *generator);
    }};
    if (r->arguments[0].word) probe_on_thread(run);
    else run();
    r->result.word = valid;
    return true;''', True)
        # A native copy keeps the override alive after Bend releases its
        # holder; the last copy goes on another thread.
        add('operator-callbacks', 'retainGenerator', [('self', handle('Shared_Qt3DRender__QTextureImageDataGenerator'))], UNIT, f'''
    NativeCallScope scope;
    auto *holder = get<Shared_Qt3DRender__QTextureImageDataGenerator>(r, r->self, {ids['Shared_Qt3DRender__QTextureImageDataGenerator']});
    if (r->error) return true;
    if (probe_shared_generator) return fail(r, EBUSY, "The probe already holds a generator");
    probe_shared_generator = new Shared_Qt3DRender__QTextureImageDataGenerator(*holder);
    return true;''', True)
        add('operator-callbacks', 'releaseGenerator', [], WORD, '''
    if (!probe_shared_generator) return fail(r, EINVAL, "The probe holds no generator");
    std::unique_ptr<Shared_Qt3DRender__QTextureImageDataGenerator> holder(std::exchange(probe_shared_generator, nullptr));
    uint32_t valid = 0;
    probe_on_thread([&] {
        auto result = (**holder)();
        valid = result && result->width() == 16 && (**holder == **holder);
        holder.reset();
    });
    QCoreApplication::sendPostedEvents();
    r->result.word = valid;
    return true;''')

    if 'QWebEnginePage' in ids or 'QWebView' in ids:
        add(('function-callbacks', 'webview-callbacks'), 'awaitObjectName', [('self', handle('QObject')), ('name', STRING)], BOOL, f'''
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, {ids['QObject']});
    if (r->error) return true;
    auto expected = QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size));
    QPointer<QObject> guard(object);
    r->result.word = probe_wait([&] {{ return !guard || guard->objectName() == expected; }}, 10000) && guard;
    return true;''', True)
    if 'QWebEnginePage' in ids and 'QRemoteObjectHostBase' in ids:
        add('function-callbacks', 'loadPage', [('self', handle('QWebEnginePage'))], UNIT, f'''
    NativeCallScope scope;
    auto *page = get<QWebEnginePage>(r, r->self, {ids['QWebEnginePage']});
    if (r->error) return true;
    bool loaded = false, ok = false;
    auto connection = QObject::connect(page, &QWebEnginePage::loadFinished, page, [&](bool value) {{ loaded = true; ok = value; }});
    page->setHtml(QStringLiteral("<html><body>Bend handler fixture</body></html>"));
    bool completed = probe_wait([&] {{ return loaded; }}, 10000);
    QObject::disconnect(connection);
    if (!completed || !ok) return fail(r, ETIMEDOUT, "The local WebEngine page did not load");
    return true;''', True)
        # A registry, a source exposing one object, and a proxy host whose
        # filter Bend sets with proxyWithHandler.
        add('function-callbacks', 'startRemote', [], handle('QRemoteObjectHostBase'), f'''
    if (probe_remote) return fail(r, EBUSY, "The remote hosts already run");
    QString suffix = QString::number(QCoreApplication::applicationPid());
    auto remote = std::make_unique<RemoteProbe>(QUrl("local:bend-handler-registry-" + suffix),
        QUrl("local:bend-handler-source-" + suffix), QUrl("local:bend-handler-proxy-" + suffix));
    if (!remote->source.enableRemoting(&remote->object, QStringLiteral("bend-source")))
        return fail(r, EIO, "The source host did not expose its object");
    r->result.word = borrow(r, static_cast<QRemoteObjectHostBase *>(&remote->proxy), {ids['QRemoteObjectHostBase']});
    if (r->error) return true;
    probe_remote = remote.release();
    return true;''')
        add('function-callbacks', 'remoteRegistry', [], STRING,
            'r->result = string_value(QStringLiteral("local:bend-handler-registry-") + QString::number(QCoreApplication::applicationPid())); return true;')
        add('function-callbacks', 'stopRemote', [], UNIT, 'delete std::exchange(probe_remote, nullptr); return true;')

    if 'QWebView' in ids:
        add('webview-unavailable', 'hideWebViewPlugins', [], UNIT, 'QCoreApplication::setLibraryPaths({}); return true;')
        add('webview-callbacks', 'prepareWebView', [('self', handle('QWebView'))], UNIT, f'''
    NativeCallScope scope;
    auto *view = get<QWebView>(r, r->self, {ids['QWebView']});
    if (r->error) return true;
    bool complete = false, succeeded = false;
    auto connection = QObject::connect(view, &QWebView::loadingChanged, view, [&](const QWebViewLoadingInfo &info) {{
        if (info.status() == QWebViewLoadingInfo::LoadStatus::Succeeded || info.status() == QWebViewLoadingInfo::LoadStatus::Failed) {{
            complete = true; succeeded = info.status() == QWebViewLoadingInfo::LoadStatus::Succeeded;
        }}
    }});
    view->loadHtml(QStringLiteral("<html><body>Bend QWebView handler fixture</body></html>"));
    bool finished = probe_wait([&] {{ return complete; }}, 10000);
    QObject::disconnect(connection);
    if (!finished || !succeeded) return fail(r, ETIMEDOUT, "The QWebView document did not load");
    return true;''', True)

    if args.rhi:
        add('rhi-cleanup', 'cleanupHit', [('key', WORD)], UNIT,
            'if (r->arguments[0].word == 2) return fail(r, EINVAL, "A removed handler ran"); ++rhi_cleanup_hits; return true;')
        add('rhi-cleanup', 'cleanupHits', [], WORD, 'r->result.word = rhi_cleanup_hits; return true;')
        add(('rhi-cleanup', 'rhi-lifetimes'), 'rhiDeleteNative', [('self', handle('QRhi'))], UNIT, f'''
    auto *self = get<QRhi>(r, r->self, {ids['QRhi']});
    if (r->error) return true;
    delete self;
    return true;''', True)
        add('rhi-lifetimes', 'rhiExternalFrame', [('self', handle('QRhi')), ('begin', BOOL)], UNIT, f'''
    auto *self = get<QRhi>(r, r->self, {ids['QRhi']});
    if (r->error) return true;
    auto *identity = rhi_identity(r->self);
    if (!identity || identity->domain->frame_owned) return fail(r, EINVAL, "The probe needs a frame Bend does not own");
    QRhi::FrameOpResult result;
    if (r->arguments[0].word) {{
        if (self->isRecordingFrame()) return fail(r, EBUSY, "A frame is already recording");
        QRhiCommandBuffer *commands = nullptr;
        result = self->beginOffscreenFrame(&commands);
    }} else {{
        if (!self->isRecordingFrame()) return fail(r, EPERM, "The probe frame ended early");
        result = self->endOffscreenFrame();
    }}
    if (result != QRhi::FrameOpSuccess) return fail(r, EIO, "The native frame operation failed");
    return true;''', True)
        add('rhi-lifetimes', 'rhiAbortFrame', [('self', handle('QRhi')), ('throw', BOOL)], UNIT, f'''
    auto *self = get<QRhi>(r, r->self, {ids['QRhi']});
    if (r->error || !rhi_begin_frame_ready(r, r->self)) return true;
    RhiFrameStartGuard rollback(r, self, nullptr);
    QRhiCommandBuffer *commands = nullptr;
    if (self->beginOffscreenFrame(&commands) != QRhi::FrameOpSuccess) return fail(r, EIO, "The native frame did not begin");
    r->result.word = borrow(r, commands, {ids['QRhiCommandBuffer']});
    if (r->error) return true;
    if (r->arguments[0].word) throw std::bad_alloc();
    return fail(r, ENOMEM, "Injected conversion failure");''', True)
    return probes


def emit_probes(g, probes, selected):
    for fixtures, public, params, result, body, has_self in probes:
        if not selected.intersection(fixtures):
            continue
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'case {operation}: {{\n{body}\n}}')
        g.emit_effect(public, params, result, operation, has_self=has_self)


def runtime_checks(work, qt, programs, jobs=2):
    spec = importlib.util.spec_from_file_location('qt612_checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    (work / 'receipt.json').write_text(json.dumps({'verification_complete': False,
        'expected_programs': [p[0] for p in programs]}, indent=2) + '\n')
    render_env = dict(QT_QUICK_BACKEND='', QSG_RHI_BACKEND='opengl',
                      QT_QPA_PLATFORM='xcb', LIBGL_ALWAYS_SOFTWARE='1')
    receipt = checks.check_package(work, programs, os.environ.copy(), [qt], work / 'consumer', jobs=jobs,
                                  runtime_overrides={name: render_env for name in ('scenegraph-material-render', 'scenegraph-material-instances')})
    receipt['expected_programs'] = [p[0] for p in programs]
    receipt['fixture_sha256'] = {name: hashlib.sha256(source.encode()).hexdigest()
                                 for name, source, marker in programs}
    if 'post-routines' in receipt['expected_programs']:
        controls = work / 'post-routine-controls'
        subprocess.run(['python3', str(ROOT / 'scripts/check-qt-post-routines.py'),
                        '--package', str(work), '--work', str(controls), '--qt-root', str(qt)],
                       cwd=ROOT, check=True)
        receipt['post_routine_controls'] = json.loads((controls / 'receipt.json').read_text())
    if {run['program'] for run in receipt['runs']} != set(receipt['expected_programs']):
        raise RuntimeError('The receipt is missing a fixture run')
    selection = work / 'suite-inputs.json'
    if selection.exists():
        receipt['generator_inputs'] = json.loads(selection.read_text())
    if 'custom-signals' in receipt['expected_programs']:
        subprocess.run(['python3', str(ROOT / 'scripts/check-qt-custom-signal-types.py'), '--package', str(work)],
                       cwd=ROOT, check=True)
        receipt['custom_signal_types'] = json.loads((work / 'custom-signal-types/receipt.json').read_text())
    if 'qt-objects' in receipt['expected_programs']:
        subprocess.run(['python3', str(ROOT / 'scripts/check-qt-object-types.py'), '--package', str(work)],
                       cwd=ROOT, check=True)
        receipt['qt_object_types'] = json.loads((work / 'qt-object-types/receipt.json').read_text())
    receipt['verification_complete'] = True
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/callbacks')
    parser.add_argument('--syntax-only', action='store_true')
    parser.add_argument('--emit-only', action='store_true')
    parser.add_argument('--skip-runtime', action='store_true')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--only', action='append', default=[], help='Run only the named fixture; may be repeated')
    parser.add_argument('--skip-examples', action='store_true', help='Leave out the handler examples from examples/qt612')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--sql-signals', action='store_true', help='Add the QtSql module for mutable reference signals')
    parser.add_argument('--module', action='append', default=[], help='Add a whole module from the production extraction')
    parser.add_argument('--complete-module', action='append', default=[], help='Compile every supported method and override in this module, in addition to fixture dependencies')
    parser.add_argument('--proxy-class', action='append', default=[], help='Also emit these override classes')
    parser.add_argument('--rhi', action='store_true', help='Include the version-bound RHI classes for lifecycle checks')
    parser.add_argument('--all-features', action='store_true', help='Run every fixture from one production extraction')
    parser.add_argument('--source-work', type=Path, default=ROOT / 'build/qt612', help='Production extraction directory (api.json, headers.h, upstream.json) with the selected modules')
    parser.add_argument('--name-lock', type=Path, help='Use the name inventory of an alternate generation profile')
    parser.add_argument('--minimal-signal-codecs', action='store_true',
                        help='Focused control only: emit primitive and fixture-referenced signal codecs')
    args = parser.parse_args()
    args.work = args.work.resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    if args.all_features:
        args.rhi = args.sql_signals = True
        args.module = list(dict.fromkeys([*args.module, *SUITE_MODULES]))
    if args.minimal_signal_codecs and (args.all_features or args.complete_module):
        parser.error('Complete module/all-feature checks require the complete signal codec inventory')
    extra_modules = list(dict.fromkeys(args.module + args.complete_module + (['QtSql'] if args.sql_signals else [])))
    programs = runtime_programs(args.only, extra_modules, args.rhi, not args.skip_examples)
    if args.runtime_only:
        runtime_checks(args.work, args.qt_root, programs, args.jobs)
        return
    profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
    version = qt_targets.installed_version(args.qt_root)
    target = qt_targets.target(version)
    profile['minimum_qt'] = version
    snapshot = args.source_work.resolve()
    upstream = json.loads((snapshot / 'upstream.json').read_text())
    if upstream['commit'] != target['shiboken_commit']:
        raise ValueError('The extraction does not match the pinned PySide source')
    headers, _, modules, _, _ = prepare_upstream(
        Path.home() / '.cache/bend-qt-generator' / ('pyside-setup' if version == qt_targets.DEFAULT else 'pyside-setup-' + version), args.qt_root,
        list(dict.fromkeys([*profile['qt_modules'], *extra_modules])), args.work, limited_abi=args.rhi)
    missing = set(modules) - set(upstream['modules'])
    if missing:
        raise ValueError('Regenerate the production API or select --source-work with these modules: ' + ', '.join(sorted(missing)))
    source_headers = (snapshot / 'headers.h').read_text()
    coherent_headers = headers.read_text()
    for include in re.findall(r'^#include <(rhi/[^>]+)>', coherent_headers, re.M):
        if '#include <' + include + '>' not in source_headers:
            raise ValueError('The production extraction lacks the selected RHI header: ' + include)
    api = json.loads((snapshot / 'api.json').read_text())
    import qobject_interfaces
    qobject_interfaces.restore(api, args.work, require_complete=False)
    import qio_pipe
    qio_pipe.restore(api, args.work, require_complete=False)
    packages = {'PySide6.' + module for module in modules}
    all_classes = {c['name']: c for c in api['classes']}
    selected = {c['name'] for c in api['classes'] if
                (c['package'] in packages and (args.rhi or '/rhi/' not in c.get('source_file', ''))) or
                (args.rhi and c['package'] == 'BendQt' and '/rhi/' in c.get('source_file', ''))}
    pending = [all_classes[name] for name in selected if '/rhi/' in all_classes[name].get('source_file', '')]

    def field_types(t):
        yield t['name']
        for child in t.get('instantiations', []):
            yield from field_types(child)
    while pending:
        c = pending.pop()
        for field in c.get('fields', []):
            if not field['public'] or field.get('removed'):
                continue
            for name in field_types(field['type']):
                if name in all_classes and name not in selected:
                    selected.add(name)
                    pending.append(all_classes[name])
    api['classes'] = [c for c in api['classes'] if c['name'] in selected]
    api['global_functions'] = [f for f in api.get('global_functions', [])
                               if f.get('package', 'PySide6.QtCore') in packages]
    profile.update(qt_modules=modules, limited_abi=args.rhi)
    sources = '\n'.join(p[1] for p in programs)
    (args.work / 'suite-inputs.json').write_text(json.dumps({
        'source_work': str(snapshot), 'pyside_commit': target['shiboken_commit'], 'qt_modules': modules,
        'all_features': args.all_features,
        'snapshot_sha256': {name: hashlib.sha256((snapshot / name).read_bytes()).hexdigest()
                            for name in ('api.json', 'headers.h', 'upstream.json')},
        'fixture_headers_sha256': hashlib.sha256(coherent_headers.encode()).hexdigest(),
        'expected_programs': [p[0] for p in programs]
    }, indent=2) + '\n')
    native_objects.refine_traits(api, args.qt_root, profile['qt_modules'], args.work, 'clang++-19')
    name_lock = overload_names.NameLock.load(args.name_lock) if args.name_lock else None
    if name_lock: name_lock.path = None  # Focused checks never write a production lock.
    generator = Generator(api, profile, name_lock)
    generator.collect()
    def select_signal_codecs(g):
        if not args.minimal_signal_codecs:
            return
        required = {'QObject.arg', 'QVariant.arg'} | set(re.findall(r'Qt\.([A-Za-z0-9_.]+\.(?:arg|valueArg))\(', sources))
        # Shared convenience declarations are typechecked too, even when this
        # fixture does not call them (for example Qml.factoryMethod).
        for template in [*(ROOT / 'generator/templates').glob('*.bend'), *(ROOT / 'generator').glob('*.py')]:
            required.update(re.findall(r'\b([A-Za-z0-9_.]+\.(?:arg|valueArg))\(', template.read_text()))
        original = g.custom_signal_arguments
        keep = {public for public, _, _ in original if public and ('.' not in public or public in required)}
        leaves = {kind['bend'] for public, _, kind in original if public in keep}
        def primitive_container(kind):
            children = kind.get('children', [])
            return bool(children) and all(child['bend'] in leaves or primitive_container(child) for child in children)
        g.custom_signal_arguments = [(public, cpp, kind) for public, cpp, kind in original
            if public in keep or (public is None and primitive_container(kind))]
        included = {cpp for _, cpp, _ in g.custom_signal_arguments}
        for _, cpp, _ in original:
            if cpp not in included:
                g.custom_signal_excluded_types[cpp] = 'Outside this focused fixture signal codec inventory'
        selection = json.loads((args.work / 'suite-inputs.json').read_text())
        selection['fixture_signal_codecs'] = sorted(included)
        (args.work / 'suite-inputs.json').write_text(json.dumps(selection, indent=2) + '\n')
    if args.complete_module:
        packages_to_check = {'PySide6.' + module for module in args.complete_module}
        module_classes = {c['name'] for c in api['classes'] if c['package'] in packages_to_check}
        (args.work / 'module-coverage.json').write_text(json.dumps(dict(
            modules=args.complete_module,
            classes=sorted(module_classes),
            generated=[dict(name=m['bend_name'], signature=m['function']['signature'], arguments=[a['bend'] for a in m['args']], result=m['return']['bend']) for m in generator.methods if m['class'] in module_classes],
            excluded=[e for e in generator.excluded if e['class'] in module_classes]), indent=2) + '\n')
    named = set(re.findall(r'Qt\.([A-Za-z0-9_.]+)', sources))
    import convenience_apis
    named.update(convenience_apis.dependencies(generator, named))
    named.update(re.sub(r'(\.connect_[A-Za-z0-9_]+?)With(?=__|$)', r'\1', name)
                 for name in tuple(named) if '.connect_' in name)
    complete_packages = {'PySide6.' + module for module in args.complete_module}
    complete_classes = {c['name'] for c in api['classes'] if c['package'] in complete_packages}
    generator.methods = [m for m in generator.methods if m['bend_name'] in named or m['class'] in complete_classes or
                         (args.rhi and m['class'].startswith('QRhi'))]
    callbacks.prepare(generator)
    if any(item['owner'] == 'QProcess' and item['function']['name'] == 'setChildProcessModifier'
           for item in generator.callback_functions):
        raise AssertionError('A post-fork QProcess modifier must never run Bend')
    factories = set(re.findall(r'Qt\.([A-Za-z_][A-Za-z0-9_.]*)\.newOverride(?:_|\b)', sources))
    native_bases = {c['name'].replace('::', '.') for c in generator.callback_classes}
    factories.update(name for name in re.findall(r'Qt\.([A-Za-z_][A-Za-z0-9_.]*)\.define\(', sources)
                     if name in native_bases)
    required = {callbacks.ident(name) for name in args.proxy_class}
    if 'Qt.QObject.newWithSignals(' in sources:
        required.add('QObject')
    names = {p[0] for p in programs}
    # Overrides the probes construct themselves.
    for fixture, classes in [('render-value-callbacks', ('QSGRenderNode::RenderState', 'QSGMaterial', 'QSGTextNode')),
                             ('callback-state-expiry', ('QSGMaterialShader',)), ('sampled-images', ('QSGMaterialShader',)),
                             ('module-callbacks', ('QDesignerFormWindowInterface',))]:
        if fixture in names:
            required.update(callbacks.ident(name) for name in classes)
    generator.callback_classes = [c for c in generator.callback_classes if
                                  c['name'] in complete_classes or callbacks.ident(c['name']) in required or c['name'].replace('::', '.') in factories or
                                  'Shared_' + callbacks.ident(c['name']) in factories]
    selection = json.loads((args.work / 'suite-inputs.json').read_text())
    selection['fixture_proxy_classes'] = [c['name'] for c in generator.callback_classes]
    selection['complete_modules'] = args.complete_module
    selection['complete_module_methods'] = {module: sum(m['class'] in {c['name'] for c in api['classes'] if c['package'] == 'PySide6.' + module} for m in generator.methods) for module in args.complete_module}
    (args.work / 'suite-inputs.json').write_text(json.dumps(selection, indent=2) + '\n')

    shader_path = None
    if 'native-image-plugin' in names:
        from qt_fixture_plugins import prepare_image_plugin
        prepare_image_plugin(args.qt_root, args.work)
    if names.intersection(('scenegraph-material-render', 'scenegraph-material-instances')):
        for stage in ('vert', 'frag'):
            subprocess.run([str(args.qt_root / 'bin/qsb'), '--qt6', '-b', '-o', str(args.work / ('scenegraph-material.' + stage + '.qsb')),
                            str(ROOT / 'scripts/fixtures' / ('scenegraph-material.' + stage))], check=True)
    if 'sampled-images' in names:
        shader_path = args.work / 'samplers.frag.qsb'
        fragment = args.work / 'samplers.frag'
        fragment.write_text('#version 440\nlayout(location=0) in vec2 uv;\nlayout(location=0) out vec4 color;\n'
                            'layout(binding=1) uniform sampler2D images[2];\n'
                            'void main() { color = texture(images[0],uv) + texture(images[1],uv); }\n')
        subprocess.run([str(args.qt_root / 'bin/qsb'), '-o', str(shader_path), str(fragment)], check=True)
    probes = probe_definitions(generator, args, extra_modules, shader_path)
    # Probe defs follow the generated handler wrappers they may name.
    emit_handlers = callbacks.emit
    import custom_signals
    prepare_arguments = custom_signals.prepare

    def prepare_fixture_arguments(g):
        prepare_arguments(g)
        select_signal_codecs(g)

    def emit_with_probes(g):
        emit_handlers(g)
        emit_probes(g, probes, names)
    callbacks.emit = emit_with_probes
    custom_signals.prepare = prepare_fixture_arguments
    try:
        bend, effects, native = generator.emit()
    finally:
        callbacks.emit = emit_handlers
        custom_signals.prepare = prepare_arguments
    for placeholder, name in [('@REGISTRY_SET_DELEGATE@', 'QTableView.setItemDelegateForRow'),
                              ('@REGISTRY_GET_URLS@', 'QMimeData.urls')]:
        if placeholder in native:
            operations = {m['operation'] for m in generator.methods if m['bend_name'] == name}
            if len(operations) != 1:
                raise RuntimeError('The registry probe requires one generated operation for ' + name)
            native = native.replace(placeholder, str(operations.pop()))
    tables = evaluate_tables(args.work)
    abi = qt_targets.abi((ROOT / 'generator/templates/abi.h').read_text(), generator.argument_capacity, version)
    aliases = ''.join(f'using {name} = {source};\n' for name, source in api['typedefs'].items() if name in generator.ids)
    aliases += representations.aliases(generator)
    qml_prefix, qml_suffix = callbacks.qml_sources(generator, args.qt_root, args.work)
    globals = PROBE_GLOBALS
    if 'protected-fields' in names:
        globals += '''struct ForeignProtectedFields : QObject { QSGSimpleTextureNode node; };\n'''
    if 'canvas-grab-callbacks' in names:
        globals += '''class CanvasCallbackFixture : public QObject {
public:
    std::unique_ptr<QRhi> rhi;
    QCanvasPainterFactory factory;
    QCanvasOffscreenCanvas canvas;
    CanvasCallbackFixture() {
        QRhiNullInitParams params;
        rhi.reset(QRhi::create(QRhi::Null, &params));
        if (rhi) if (auto *painter = factory.create(rhi.get())) canvas = painter->createCanvas(QSize(8, 8));
    }
    ~CanvasCallbackFixture() override {
        if (!canvas.isNull()) factory.painter()->destroyCanvas(canvas);
        factory.destroy();
    }
};
'''
    if shader_path:
        coherent_headers += '#include <QtQuick/private/qsgmaterialshader_p.h>\n'
        globals += '''static uint32_t sampled_texture_deleted = 0;
class SampledTextureProbe : public QSGTexture {
public:
    ~SampledTextureProbe() override { ++sampled_texture_deleted; }
    qint64 comparisonKey() const override { return qint64(quintptr(this)); }
    QSize textureSize() const override { return {1, 1}; }
    bool hasAlphaChannel() const override { return false; }
    bool hasMipmaps() const override { return false; }
};
'''
    video_probe = 'video-buffers' in names and 'QtMultimedia' in extra_modules
    if video_probe:
        globals += 'static bool video_probe_fail_allocation;\n'
    if 'operator-callbacks' in names and 'Shared_Qt3DRender__QTextureImageDataGenerator' in generator.ids:
        globals += 'static Shared_Qt3DRender__QTextureImageDataGenerator *probe_shared_generator;\n'
    if 'function-callbacks' in names and 'QRemoteObjectHostBase' in generator.ids:
        globals += '''struct RemoteProbe {
    QRemoteObjectRegistryHost registry;
    QRemoteObjectHost source;
    QRemoteObjectHost proxy;
    QObject object;
    RemoteProbe(const QUrl &registry_url, const QUrl &source_url, const QUrl &proxy_url)
        : registry(registry_url), source(source_url, registry_url), proxy(proxy_url) {}
};
static RemoteProbe *probe_remote;
'''
    source = (coherent_headers + qml_prefix + '#include <QtCore/QEventLoop>\n#include <thread>\n' + aliases +
              '#define BQT_BUNDLED_RUNTIME_NATIVE 1\n' + (ROOT / 'generator/templates/runtime_paths.cpp').read_text() +
              'namespace bendqt {\n' + globals + '}\n' + (ROOT / 'generator/templates/runtime.cpp').read_text() + qml_suffix)
    source = (source.replace('// @ABI@', abi).replace('// @LIFETIME@', cpp_tables(tables))
              .replace('// @NATIVE_OBJECTS@', native_objects.traits(generator))
              .replace('// @DISPATCH@', PROBE_SUPPORT + native))
    if video_probe:
        site = 'auto frame=std::make_unique<QVideoFrame>();'
        if source.count(site) != 1:
            raise RuntimeError('The video allocation fault site changed')
        source = source.replace(site, 'if (video_probe_fail_allocation) { video_probe_fail_allocation=false; throw std::bad_alloc(); }\n    ' + site)
    if 'module-callbacks' in names:
        # Only this probe derives from a generated override.
        source = source.replace('class BqtProxy_QDesignerFormWindowInterface final :', 'class BqtProxy_QDesignerFormWindowInterface :')
    (args.work / 'wrappers.cpp').write_text(source)
    (args.work / 'qt.bend').write_text(bend)
    (args.work / 'callbacks.json').write_text(json.dumps(callbacks.inventory(generator), indent=2) + '\n')
    # Keep the complete transport inputs with a reviewable emit-only snapshot.
    # Packaging it later must use the operation table that produced qt.bend.
    modules = profile['qt_modules']
    additional = [module for module in modules if module not in ('QtCore', 'QtGui', 'QtWidgets')]
    libraries = [f'    void *libraries[{len(additional) + 1}] = {{lib}};']
    for i, module in enumerate(additional, 1):
        libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                      f'    if (!libraries[{i}]) return dlerror();']
    (args.work / 'abi.h').write_text(abi)
    (args.work / 'effects.generated.c').write_text(effects)
    (args.work / 'libraries.generated.c').write_text('\n'.join(libraries))
    effect = (ROOT / 'generator/templates/effects.c').read_text()
    (args.work / 'effects.template.c').write_text(effect)
    if args.emit_only:
        return
    if args.syntax_only:
        flags = ['clang++-19', '-std=c++17', '-fsyntax-only', '-ferror-limit=0', '-fexceptions', '-frtti',
                 '-I' + str(args.qt_root / 'include'), '-I' + str(args.qt_root / 'mkspecs/linux-g++')]
        flags += ['-I' + str(args.qt_root / 'include' / module) for module in modules]
        flags += ['-I' + str(path) for path in versioned_include_paths(args.qt_root, modules)]
        if '// BQT_AUXILIARY_BEGIN ' in source:
            import native_shards
            try:
                native_shards.check_syntax(args.work / 'wrappers.cpp', args.work, flags)
            except RuntimeError as error:
                (args.work / 'syntax.log').write_text(str(error) + '\n')
                sys.exit(str(error))
            (args.work / 'syntax.log').write_text('PASS: shared runtime and every bounded operation/factory unit; see native-syntax.json\n')
        else:
            checked = subprocess.run([*flags, args.work / 'wrappers.cpp'], capture_output=True, text=True)
            (args.work / 'syntax.log').write_text(checked.stdout + checked.stderr)
            if checked.returncode:
                errors = [line for line in (checked.stdout + checked.stderr).splitlines() if ' error: ' in line]
                print('\n'.join(errors[:40]))
                sys.exit('C++ compilation failed; see ' + str(args.work / 'syntax.log'))
        print(f'PASS native syntax: {len(generator.callback_classes)} override classes', flush=True)
        return
    # The object compiler validates all selected bodies. A separate syntax pass
    # would repeat the expensive frontend work before producing the same objects.
    try:
        assembly, imports, metadata = compile_backend(args.work / 'wrappers.cpp', args.qt_root, args.work, 'clang++-19', modules)
    except subprocess.CalledProcessError as error:
        (args.work / 'backend-error.log').write_text(error.stdout + error.stderr)
        raise
    (args.work / 'syntax.log').write_text('PASS: syntax checked by object compilation or its dependency-verified cache\n')
    measured = metadata.get('proxy_constructibility')
    if measured is not None:
        if len(measured) != len(generator.callback_classes):
            raise RuntimeError('The compiled override inventory has the wrong length')
        generator.callback_native_constructible = dict(zip((c['name'] for c in generator.callback_classes), measured))
        (args.work / 'callbacks.json').write_text(json.dumps(callbacks.inventory(generator), indent=2) + '\n')
    for key, value in [('ABI', abi), ('ASSEMBLY', assembly), ('IMPORTS', imports), ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
        effect = effect.replace('// @' + key + '@', value)
    (args.work / 'qt.c').write_text(effect)
    print('PASS dlopen packaging: override classes and handler transport', flush=True)
    if args.skip_runtime:
        return
    runtime_checks(args.work, args.qt_root, programs, args.jobs)


if __name__ == '__main__':
    main()
