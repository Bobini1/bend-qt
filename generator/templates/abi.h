// Shared layout compiled by the maintainer's C++ compiler and consumer's C compiler.
#ifndef BQT_NATIVE_ABI_INTERFACE
#define BQT_NATIVE_ABI_INTERFACE
enum { BQT_ARGUMENT_CAPACITY = @ARGUMENT_CAPACITY@ };
typedef struct BqtValue BqtValue;
struct BqtValue {
    uint32_t word;
    char *text;
    size_t size;
    uint32_t high;
    BqtValue *items;
    size_t count;
    uint32_t tag; // 0 scalar, 1 UTF-8 text, 2 sequence, 3 opaque Bend data
    uint32_t owned_handle; // rollback only: destroyed if the value is discarded
    uint32_t borrowed_handle; // liveness guard; never an ownership claim
    uint32_t owned_data; // one host-data lease, consumed or transferred with this value
};

// One call from Bend into Qt. It runs to completion on the calling thread.
typedef struct BqtRequest BqtRequest;
struct BqtRequest {
    uint32_t operation;
    uint32_t self;
    uint32_t scope;
    BqtValue arguments[BQT_ARGUMENT_CAPACITY];
    BqtValue result;
    int error;
    const char *message;
};

// A descriptor or deadline a Bend computation waits on.
typedef struct BqtSource {
    int fd;
    int writable;
} BqtSource;

enum { BQT_HANDLER_DONE = 0, BQT_HANDLER_WAITS = -1 };

// What the Bend program gives Qt. Every function runs on the main thread.
typedef struct BqtHost {
    int argc;
    char **argv;
    // Runs a Bend handler now. Answers BQT_HANDLER_DONE, an errno value with
    // its text in *message (valid until the next invoke), or
    // BQT_HANDLER_WAITS when the handler waits and continues as a computation.
    int (*invoke)(uint32_t handler, const BqtValue *request, const char **message);
    // Qt no longer holds the handler.
    void (*release)(uint32_t handler);
    // While Qt waits for events: what Bend's waiting computations wait on.
    // Answers the source count (capacity + 1 if they do not fit) and the
    // milliseconds to the nearest deadline, or -1 without one.
    size_t (*sources)(BqtSource *out, size_t capacity, int64_t *wait_ms);
    // Whether a Bend computation is ready to continue.
    int (*runnable)(void);
    // Continues every ready Bend computation up to its next wait.
    void (*run)(void);
    // Writes buffered standard output before Qt waits.
    void (*flush)(void);
    // Data access runs on the Bend thread. data_release is allocation-free
    // and may run on any thread; data_drain returns deferred drops to Bend.
    int (*data_exists)(uint32_t);
    int (*data_retain)(uint32_t);
    uint32_t (*data_clone)(uint32_t);
    void (*data_release)(uint32_t);
    void (*data_drain)(void);
    uint32_t (*data_count)(void);
#if defined(BQT_NATIVE_PARTITIONS)
    const BqtRuntimeServices *shared_runtime;
#endif
    // NULL in maintainer controls using an installed Qt; otherwise the
    // complete embedded or explicitly replaced runtime's absolute prefix.
    const char *runtime_root;
} BqtHost;
#include <string.h>

// A package build carries all bindings for one Qt runtime, including APIs
// outside Qt's stable public ABI. Reject a different runtime before loading
// its native payload; no operation is silently disabled by version selection.
#define BQT_QT_RUNTIME "6.12.0"
static inline const char *bqt_check_qt_version(const char *version) {
    return version && strcmp(version, BQT_QT_RUNTIME) == 0 ? NULL
        : "The selected runtime does not match this package's Qt " BQT_QT_RUNTIME "; use the bundled runtime or a complete matching replacement";
}
#endif

