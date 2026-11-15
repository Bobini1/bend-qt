#ifndef BQT_BUNDLE_TYPES
#define BQT_BUNDLE_TYPES
#include <stddef.h>
#include <stdint.h>
typedef struct BqtBundleBlock {
    size_t plain, packed;
    const char *encoded;
} BqtBundleBlock;
void bqt_bundle_add(size_t, const BqtBundleBlock *);
void bqt_bundle_enable(size_t);
#endif
