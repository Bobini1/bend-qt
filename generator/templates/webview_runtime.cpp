static bool webview_backend_ready(BqtRequest *r)
{
    // QWebViewFactory calls qFatal when its backend plugin cannot be found.
    // Use public loader metadata to turn missing/unloadable installed backends
    // into checked construction failures without importing Qt private ABI.
    bool found = false;
    for (const auto &directory : QCoreApplication::libraryPaths()) {
        QDir plugins(directory + QStringLiteral("/webview"));
        for (const auto &file : plugins.entryList(QDir::Files)) {
            QPluginLoader loader(plugins.absoluteFilePath(file));
            const auto metadata = loader.metaData();
            if (metadata.value(QStringLiteral("IID")).toString()
                    != QStringLiteral("org.qt-project.Qt.QWebViewPluginInterface")) continue;
            found = true;
            // Qt's factory may fall back to the first available backend. Do
            // not admit a directory containing a matching unloadable plugin.
            if (!loader.instance()) { fail(r, ENOTSUP, "The installed QtWebView backend plugin could not be loaded"); return false; }
        }
    }
    if (!found) { fail(r, ENOTSUP, "QtWebView requires an installed runtime backend plugin"); return false; }
    return true;
}
