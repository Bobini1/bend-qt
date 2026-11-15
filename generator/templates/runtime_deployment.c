// The bundled Qt runtime is selected before the embedded binding payload.
#include <link.h>

static const char *const bqt_runtime_preload[] = {
// @PRELOAD@
    NULL
};
static const char *const bqt_runtime_modules[] = {
// @MODULES@
};
static char bqt_runtime_error[PATH_MAX + 256];

static int bqt_runtime_check_loaded(struct dl_phdr_info *info, size_t size, void *context) {
    (void)size; (void)context;
    const char *name = strrchr(info->dlpi_name, '/');
    name = name ? name + 1 : info->dlpi_name;
    if (strncmp(name, "libQt6", 6) && strncmp(name, "libicu", 6)) return 0;
    char real[PATH_MAX];
    size_t root_size = strlen(bqt_bundle_root);
    if (!realpath(info->dlpi_name, real) || strncmp(real, bqt_bundle_root, root_size)
            || real[root_size] != '/') {
        snprintf(bqt_runtime_error, sizeof bqt_runtime_error,
                 "A different Qt/ICU runtime is already loaded: %s", info->dlpi_name);
        return 1;
    }
    return 0;
}

static const char *bqt_runtime_path(char *path, size_t capacity, const char *relative) {
    if (snprintf(path, capacity, "%s/%s", bqt_bundle_root, relative) >= (int)capacity)
        return "Bundled Qt path is too long";
    return NULL;
}

static const char *bqt_runtime_prepare(void) {
    const char *error = bqt_bundle_materialize();
    if (error) return error;
    if (getenv("BEND_QT_LIBRARY"))
        return "BEND_QT_LIBRARY cannot replace a bundled runtime; use BEND_QT_RUNTIME with a complete matching Qt installation";
    if (dl_iterate_phdr(bqt_runtime_check_loaded, NULL)) return bqt_runtime_error;
    // The root is also passed to the native Qt startup, which registers an
    // internal qt.conf resource before constructing QApplication.
    char path[PATH_MAX];
    const char *const variables[][2] = {
        {"QT_PLUGIN_PATH", "plugins"}, {"QT_QPA_PLATFORM_PLUGIN_PATH", "plugins/platforms"},
        {"QML_IMPORT_PATH", "qml"}, {"QML2_IMPORT_PATH", "qml"},
        {"QTWEBENGINEPROCESS_PATH", "libexec/QtWebEngineProcess"},
        {"QTWEBENGINE_RESOURCES_PATH", "resources"},
        {"QTWEBENGINE_LOCALES_PATH", "translations/qtwebengine_locales"}
    };
    for (size_t i = 0; i < sizeof variables / sizeof *variables; ++i) {
        if ((error = bqt_runtime_path(path, sizeof path, variables[i][1]))) return error;
        if (setenv(variables[i][0], path, 1)) return "Cannot set bundled Qt runtime paths";
    }
    // Child processes, including QtWebEngineProcess, need their own runtime
    // search path at exec time. Keep OS driver/backend libraries available.
    const char *previous = getenv("LD_LIBRARY_PATH");
    size_t capacity = strlen(bqt_bundle_root) + (previous ? strlen(previous) : 0) + 7;
    char *search = malloc(capacity);
    if (!search) return "Cannot allocate the Qt child-process library path";
    snprintf(search, capacity, "%s/lib%s%s", bqt_bundle_root, previous && *previous ? ":" : "", previous ? previous : "");
    int failed = setenv("LD_LIBRARY_PATH", search, 1); free(search);
    if (failed) return "Cannot set the Qt child-process library path";
    for (size_t i = 0; bqt_runtime_preload[i]; ++i) {
        if (!bqt_bundle_contains(bqt_runtime_preload[i])) continue;
        if ((error = bqt_runtime_path(path, sizeof path, bqt_runtime_preload[i]))) return error;
        if (!dlopen(path, RTLD_NOW | RTLD_LOCAL)) return dlerror();
    }
    if (dl_iterate_phdr(bqt_runtime_check_loaded, NULL)) return bqt_runtime_error;
    return NULL;
}

static const char *bqt_runtime_load_modules(void **libraries) {
    char path[PATH_MAX];
    for (size_t i = 0; i < sizeof bqt_runtime_modules / sizeof *bqt_runtime_modules; ++i) {
        const char *error = bqt_runtime_path(path, sizeof path, bqt_runtime_modules[i]);
        if (error) return error;
        libraries[i] = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (!libraries[i]) return dlerror();
    }
    return NULL;
}
