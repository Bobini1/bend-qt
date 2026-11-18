// Generated, compressed Linux ELF. Only the maintainer needs a C++ toolchain.
// Each module's loader includes what it uses: a program importing only one
// module does not compile the base adapter's includes before it.
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
// @CACHE@

static const char bqt_payload[] =
// @PAYLOAD@
;
static void (*bqt_native_call)(BqtRequest *);
static const char *(*bqt_native_start)(const BqtHost *);
static int (*bqt_native_stop)(void);
void bqt_abi_call(BqtRequest *r) { bqt_native_call(r); }
const char *bqt_abi_start(const BqtHost *host) { return bqt_native_start(host); }
int bqt_abi_stop(void) { return bqt_native_stop(); }

static int bqt_base64_digit(unsigned char value) {
    if (value >= 'A' && value <= 'Z') return value - 'A';
    if (value >= 'a' && value <= 'z') return value - 'a' + 26;
    if (value >= '0' && value <= '9') return value - '0' + 52;
    if (value == '+') return 62;
    if (value == '/') return 63;
    return -1;
}

// The decoded module is a file in its own cache entry, named by its content,
// so later starts map it without decoding, and programs share its pages.
static const char bqt_payload_id[] = "@CACHE_ID@";
static int bqt_payload_use = -1;

// The stamp line for the cached module file, or 0 if it cannot be the module.
static int bqt_payload_stamp(int root, char record[256]) {
    struct stat st;
    if (fstatat(root, "native.so", &st, AT_SYMLINK_NOFOLLOW) || !S_ISREG(st.st_mode)
        || st.st_uid != getuid() || st.st_size != @ELF_SIZE@ || (st.st_mode & 0777) != 0500) return 0;
    snprintf(record, 256, "%s %llu %llu %llu %llu %lld %ld\n", bqt_payload_id,
             (unsigned long long)st.st_dev, (unsigned long long)st.st_ino, (unsigned long long)st.st_size,
             (unsigned long long)st.st_mode, (long long)st.st_mtim.tv_sec, (long)st.st_mtim.tv_nsec);
    return 1;
}

// Decodes the payload into a new file and commits it by rename.
static const char *bqt_decode_payload(int root, const char *entry) {
    // Qt's Linux runtime already depends on zlib. Resolve it dynamically so
    // the consumer still builds with only Bend's ordinary C dependencies.
    void *zlib = dlopen("libz.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!zlib) return dlerror();
    int (*inflate_bytes)(unsigned char *, unsigned long *, const unsigned char *, unsigned long);
    void *symbol = dlsym(zlib, "uncompress");
    if (!symbol) { dlclose(zlib); return "Missing zlib uncompress"; }
    memcpy(&inflate_bytes, &symbol, sizeof symbol);
    unsigned char *compressed = malloc(@COMPRESSED_SIZE@);
    if (!compressed) { dlclose(zlib); return "Cannot allocate Qt payload decoder"; }
    size_t length = 0;
    unsigned accumulator = 0, bits = 0;
    for (size_t i = 0; i < sizeof bqt_payload - 1; ++i) {
        if (bqt_payload[i] == '=') break;
        int digit = bqt_base64_digit((unsigned char)bqt_payload[i]);
        if (digit < 0) { free(compressed); dlclose(zlib); return "Invalid Qt payload encoding"; }
        accumulator = (accumulator << 6) | (unsigned)digit;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (length == @COMPRESSED_SIZE@) {
                free(compressed); dlclose(zlib); return "Qt payload exceeds its declared size";
            }
            compressed[length++] = (unsigned char)(accumulator >> bits);
        }
    }
    if (length != @COMPRESSED_SIZE@) {
        free(compressed); dlclose(zlib); return "Truncated Qt payload";
    }
    char temp[64];
    snprintf(temp, sizeof temp, ".native-%ld", (long)getpid());
    // A previous crashed start may have left this process-id name.
    unlinkat(root, temp, 0);
    int fd = openat(root, temp, O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) { free(compressed); dlclose(zlib); return bqt_cache_fail("native module file", entry); }
    const char *error = NULL;
    void *mapping = MAP_FAILED;
    if (ftruncate(fd, @ELF_SIZE@) != 0) error = bqt_cache_fail("native module size", entry);
    else if ((mapping = mmap(NULL, @ELF_SIZE@, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0)) == MAP_FAILED)
        error = bqt_cache_fail("native module mapping", entry);
    else {
        unsigned long size = @ELF_SIZE@;
        // zlib checks the stream's Adler-32 checksum.
        if (inflate_bytes(mapping, &size, compressed, length) != 0 || size != @ELF_SIZE@)
            error = "Invalid compressed Qt payload";
        munmap(mapping, @ELF_SIZE@);
    }
    free(compressed);
    dlclose(zlib);
    if (!error && fchmod(fd, 0500)) error = bqt_cache_fail("native module mode", entry);
    close(fd);
    if (!error && renameat(root, temp, root, "native.so")) error = bqt_cache_fail("native module commit", entry);
    if (error) unlinkat(root, temp, 0);
    return error;
}

static const char *bqt_load_payload(void) {
    char base[PATH_MAX], entry[PATH_MAX], record[256], path[PATH_MAX];
    int root = -1;
    const char *error = bqt_cache_base(base);
    if (!error) error = bqt_cache_hold(base, bqt_payload_id, entry, &root, &bqt_payload_use);
    if (error) return error;
    if (!bqt_payload_stamp(root, record) || !bqt_cache_ready(root, record)) {
        int lock = bqt_cache_lock(root);
        if (lock < 0) error = bqt_cache_fail("native module lock", entry);
        // Another program may have cached the module while this one waited.
        else if (!bqt_payload_stamp(root, record) || !bqt_cache_ready(root, record)) {
            unlinkat(root, ".ready", 0);
            error = bqt_decode_payload(root, entry);
            if (!error && !bqt_payload_stamp(root, record)) error = "The cached Qt native module changed while it was written";
            if (!error) error = bqt_cache_mark(root, record, entry);
        }
        if (lock >= 0) { flock(lock, LOCK_UN); close(lock); }
    }
    close(root);
    if (error) return error;
    if (snprintf(path, sizeof path, "%s/native.so", entry) >= (int)sizeof path) return "Qt cache path is too long";
    // The held entry cannot be collected, and a repair replaces the file by
    // rename, so the module stays mapped and its finalizers callable.
    void *native = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!native) return dlerror();
    void *symbol = dlsym(native, "bqt_abi_call");
    if (!symbol) return "Qt payload is missing bqt_abi_call";
    memcpy(&bqt_native_call, &symbol, sizeof symbol);
    symbol = dlsym(native, "bqt_abi_start");
    if (!symbol) return "Qt payload is missing bqt_abi_start";
    memcpy(&bqt_native_start, &symbol, sizeof symbol);
    symbol = dlsym(native, "bqt_abi_stop");
    if (!symbol) return "Qt payload is missing bqt_abi_stop";
    memcpy(&bqt_native_stop, &symbol, sizeof symbol);
    bqt_cache_collect(base);
    return NULL;
}
