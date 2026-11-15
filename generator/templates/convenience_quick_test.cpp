static int convenience_quick_test(BqtRequest *r, const QString &name, QStringList arguments,
                                 QString directory, QObject *setup) {
    static bool running = false;
    if (running) { fail(r, EBUSY, "Qt Quick Test cannot run recursively"); return 0; }
    struct Reset { bool &active; ~Reset() { active = false; } } reset{running};
    running = true;
    if (directory.isEmpty()) directory = QDir::currentPath();
    if (arguments.isEmpty()) arguments.append(name);
    if (arguments.size() > INT_MAX) { fail(r, E2BIG, "Too many Qt Quick Test arguments"); return 0; }
    const auto suite = name.toUtf8(), path = directory.toUtf8();
    if (suite.contains(char(0)) || path.contains(char(0))) { fail(r, EINVAL, "Qt Quick Test names and paths cannot contain NUL"); return 0; }
    std::vector<QByteArray> storage;
    std::vector<char *> argv;
    storage.reserve(size_t(arguments.size()));
    argv.reserve(size_t(arguments.size()) + 1);
    for (const auto &argument : arguments) {
        storage.push_back(argument.toUtf8());
        if (storage.back().contains(char(0))) { fail(r, EINVAL, "Qt Quick Test arguments cannot contain NUL"); return 0; }
        argv.push_back(storage.back().data());
    }
    argv.push_back(nullptr);
    // Qt reuses the QApplication owned by Qt.run and calls normal metaobject
    // methods on setup. The test runner owns each temporary QML engine.
    return quick_test_main_with_setup(int(arguments.size()), argv.data(), suite.constData(), path.constData(), setup);
}
