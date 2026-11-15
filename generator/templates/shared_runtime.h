// Private process-wide storage shared by separately loaded native modules.
// Kept separate from the standalone ABI: ordinary profiles need no service.
#ifndef BQT_SHARED_RUNTIME_INTERFACE
#define BQT_SHARED_RUNTIME_INTERFACE
#include <stddef.h>
#include <stdint.h>

enum { BQT_RUNTIME_SERVICES_VERSION = 1, BQT_RUNTIME_THREAD_LOCAL = 1 };
typedef void *(*BqtStateCreate)(void *);
typedef void (*BqtStateDestroy)(void *);
typedef struct BqtRuntimeServices {
    uint32_t version;
    void *context;
    void *(*acquire)(void *, const char *, const char *, size_t, size_t,
                     uint32_t, BqtStateCreate, void *, BqtStateDestroy,
                     const char **);
} BqtRuntimeServices;
#endif
