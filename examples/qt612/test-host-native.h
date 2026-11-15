// Maintainer fixture: a host standing in for the Bend program. Qt starts
// through the real entry point, and a test sets `test_handler` to see what Qt
// passes to a Bend handler and to answer it.
#pragma once
#include <functional>

static std::function<int(uint32_t handler, const BqtValue *request)> test_handler;
static unsigned test_releases;

static int test_invoke(uint32_t handler, const BqtValue *request, const char **message)
{
    if (!test_handler) {
        *message = "The fixture expected no handler call";
        return EINVAL;
    }
    return test_handler(handler, request);
}
static void test_release(uint32_t) { ++test_releases; }
static size_t test_sources(BqtSource *, size_t, int64_t *wait_ms) { *wait_ms = -1; return 0; }
static int test_runnable() { return 0; }
static void test_run() {}
static void test_flush() {}

static void test_host_start(int argc, char **argv)
{
    static BqtHost host;
    host = BqtHost{argc, argv, test_invoke, test_release, test_sources, test_runnable, test_run, test_flush};
    const char *error = bqt_abi_start(&host);
    if (error) {
        std::fprintf(stderr, "Qt did not start: %s\n", error);
        std::exit(1);
    }
}
