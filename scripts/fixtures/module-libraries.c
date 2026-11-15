// Integration evidence captured in the consumer after its real Qt calls.
#ifdef CID(Runtime.loadedLibraries)
static Term bqt_module_loaded_libraries(Env e, Term *f, IoWork *w) {
    FILE *stream = fopen("/proc/self/maps", "r");
    if (!stream) return io_str(e, "MAPS_READ_FAILED", 16);
    char *line = NULL, *text = NULL;
    size_t capacity = 0, size = 0;
    ssize_t length;
    while ((length = getline(&line, &capacity, stream)) >= 0) {
        if (!strstr(line, "libQt6")) continue;
        char *next = realloc(text, size + (size_t)length + 1);
        if (!next) { free(text); text = NULL; size = 0; break; }
        text = next;
        memcpy(text + size, line, (size_t)length);
        size += (size_t)length;
        text[size] = 0;
    }
    free(line); fclose(stream);
    Term result = io_str(e, text ? text : "", size);
    free(text);
    return result;
}
static void __attribute__((constructor)) bqt_module_loaded_libraries_register(void) {
    io_eff(CID(Runtime.loadedLibraries), bqt_module_loaded_libraries);
}
#endif
