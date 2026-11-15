// Generated, compressed Linux ELF. Only the maintainer needs a C++ toolchain.
#include <sys/mman.h>
#include <sys/syscall.h>
#include <linux/memfd.h>
#include <fcntl.h>

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

static const char *bqt_load_payload(void) {
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
    int fd = (int)syscall(SYS_memfd_create, "bend-qt", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    if (fd < 0) { free(compressed); dlclose(zlib); return "Cannot create Qt payload memfd"; }
    if (ftruncate(fd, @ELF_SIZE@) != 0) {
        close(fd); free(compressed); dlclose(zlib); return "Cannot size Qt payload memfd";
    }
    void *mapping = mmap(NULL, @ELF_SIZE@, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (mapping == MAP_FAILED) {
        close(fd); free(compressed); dlclose(zlib); return "Cannot map Qt payload";
    }
    unsigned long size = @ELF_SIZE@;
    int status = inflate_bytes(mapping, &size, compressed, length);
    free(compressed);
    dlclose(zlib);
    munmap(mapping, @ELF_SIZE@);
    if (status != 0 || size != @ELF_SIZE@) { close(fd); return "Invalid compressed Qt payload"; }
    if (fcntl(fd, F_ADD_SEALS, F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL) != 0) {
        close(fd); return "Cannot seal Qt payload";
    }
    char path[64];
    snprintf(path, sizeof path, "/proc/self/fd/%d", fd);
    void *native = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    // Keep the descriptor and DSO for process lifetime. Apart from ensuring
    // native finalizers remain callable, a unique open path prevents dlopen's
    // pathname cache from confusing this payload with a later reused fd.
    if (!native) { const char *error = dlerror(); close(fd); return error; }
    symbol = dlsym(native, "bqt_abi_call");
    if (!symbol) return "Qt payload is missing bqt_abi_call";
    memcpy(&bqt_native_call, &symbol, sizeof symbol);
    symbol = dlsym(native, "bqt_abi_start");
    if (!symbol) return "Qt payload is missing bqt_abi_start";
    memcpy(&bqt_native_start, &symbol, sizeof symbol);
    symbol = dlsym(native, "bqt_abi_stop");
    if (!symbol) return "Qt payload is missing bqt_abi_stop";
    memcpy(&bqt_native_stop, &symbol, sizeof symbol);
    return NULL;
}
