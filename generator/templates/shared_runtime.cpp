// Included by module-partitioned native payloads after shared_runtime.h.
#include <new>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <utility>
#include <type_traits>

namespace bendqt {
// This pointer is intentionally local to each native payload. All payloads
// receive the same service from their one packaged C effect before first use.
inline __attribute__((visibility("hidden"))) const BqtRuntimeServices *module_runtime_services = nullptr;

template<class T> static const char *runtime_state_layout() {
    return __PRETTY_FUNCTION__;
}

template<class T> static void runtime_state_destroy(T *value) {
    if constexpr (std::is_array_v<T>) {
        for (size_t index = std::extent_v<T>; index; --index)
            runtime_state_destroy(&(*value)[index - 1]);
    } else std::destroy_at(value);
}

template<class T, class Initialize>
static T &runtime_shared_state_init(const char *key, uint32_t flags, Initialize initialize,
                                    const char *layout = runtime_state_layout<T>()) {
    if (!module_runtime_services || module_runtime_services->version != BQT_RUNTIME_SERVICES_VERSION
            || !module_runtime_services->acquire)
        throw std::runtime_error("Shared Qt runtime was not attached");
    auto create = +[](void *argument) -> void * {
        void *memory = nullptr;
        try {
            if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__)
                memory = ::operator new(sizeof(T), std::align_val_t(alignof(T)));
            else memory = ::operator new(sizeof(T));
            // A moved namespace-scope object retains C++ static-storage zero
            // initialization, even when its user-provided constructor leaves
            // some members without explicit initializers.
            std::memset(memory, 0, sizeof(T));
            (*static_cast<Initialize *>(argument))(memory);
            return memory;
        } catch (...) {
            if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__)
                ::operator delete(memory, std::align_val_t(alignof(T)));
            else ::operator delete(memory);
            return nullptr;
        }
    };
    auto destroy = +[](void *value) {
        runtime_state_destroy(static_cast<T *>(value));
        if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__)
            ::operator delete(value, std::align_val_t(alignof(T)));
        else ::operator delete(value);
    };
    const char *error = nullptr;
    void *value = module_runtime_services->acquire(module_runtime_services->context,
        key, layout, sizeof(T), alignof(T), flags, create, &initialize, destroy, &error);
    if (!value) throw std::runtime_error(error ? error : "Cannot acquire shared Qt runtime storage");
    return *static_cast<T *>(value);
}

template<class T, class Make>
static T &runtime_shared_state(const char *key, uint32_t flags, Make make) {
    return runtime_shared_state_init<T>(key, flags, [&](void *memory) { ::new (memory) T(make()); });
}
}
