#ifdef BQT_PLATFORM_SURFACE
static void native_platform_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    auto *gui = qobject_cast<QGuiApplication *>(application);
    const auto app = borrow(&request, gui, BQT_PLATFORM_APP_TYPE);
    request = {}; request.arguments[0].word = app; BQT_PLATFORM_X11(&request);
    auto *x11 = gui->nativeInterface<QNativeInterface::QX11Application>();
    assert(!request.error && bool(request.result.word) == bool(x11));
    const auto native_x11 = request.result.word;
    if (x11) {
        request = {}; request.self = native_x11; BQT_PLATFORM_X11_CONNECTION(&request);
        assert(!request.error);
        const auto connection = request.result.word;
        request = {}; request.arguments[0].word = connection; BQT_PLATFORM_X11_ADDRESS(&request);
        assert(!request.error && wide_bits(request.result) == reinterpret_cast<uintptr_t>(x11->connection()));
        request = {}; request.self = connection; destroy_object(&request); assert(!request.error);
    }
    request = {}; request.arguments[0].word = app; BQT_PLATFORM_WAYLAND(&request);
    auto *wayland = gui->nativeInterface<QNativeInterface::QWaylandApplication>();
    assert(!request.error && bool(request.result.word) == bool(wayland));
    const auto native_wayland = request.result.word;
    if (wayland) {
        request = {}; request.self = native_wayland; BQT_PLATFORM_WAYLAND_DISPLAY(&request);
        assert(!request.error);
        const auto display = request.result.word;
        request = {}; request.arguments[0].word = display; BQT_PLATFORM_WAYLAND_ADDRESS(&request);
        assert(!request.error && wide_bits(request.result) == reinterpret_cast<uintptr_t>(wayland->display()));
        request = {}; request.self = display; destroy_object(&request); assert(!request.error);
    }
    auto *window = new QWindow;
    const auto owner = own(&request, window, BQT_PLATFORM_WINDOW_TYPE);
    window->create();
    request = {}; request.self = owner; BQT_PLATFORM_SURFACE(&request);
    assert(!request.error);
    const auto surface = request.result.word;
    request = {}; request.arguments[0].word = surface; BQT_PLATFORM_SURFACE_VALID(&request);
    assert(!request.error && request.result.word);
    request = {}; request.arguments[0].word = surface; BQT_PLATFORM_SURFACE_ADDRESS(&request);
    assert(!request.error && wide_bits(request.result) == reinterpret_cast<uintptr_t>(static_cast<QSurface *>(window)->surfaceHandle()));
    // An origin pin preserves the QWindow, not its replaceable platform object.
    window->destroy();
    request = {}; request.arguments[0].word = surface; BQT_PLATFORM_SURFACE_VALID(&request);
    assert(!request.error && !request.result.word);
    request = {}; request.arguments[0].word = surface; BQT_PLATFORM_SURFACE_ADDRESS(&request);
    assert(request.error == ESTALE);
    window->create();
    request = {}; request.arguments[0].word = surface; BQT_PLATFORM_SURFACE_VALID(&request);
    assert(!request.error && !request.result.word); // A detected invalidation never revives.
    for (auto id : {surface, owner}) {
        request = {}; request.self = id; destroy_object(&request); assert(!request.error);
    }
    if (native_x11) invalidate(native_x11);
    if (native_wayland) invalidate(native_wayland);
    invalidate(app); // The application's native lifetime is managed by this fixture.
    std::puts("QT612_NATIVE_PLATFORM_OK revision_getter=1 typed_identity=1 checked_address_snapshot=1 native_revalidation=1 no_revival=1 cleanup=1");
}
#endif
