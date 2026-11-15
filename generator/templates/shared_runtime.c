// The packaged C effect owns these records; no C++ runtime is exposed to Bend.
#include <pthread.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

typedef struct BqtStateSlot BqtStateSlot;
typedef struct BqtSharedStore BqtSharedStore;
typedef struct BqtSharedThread BqtSharedThread;
struct BqtSharedThread {
    BqtSharedThread *next;
    BqtSharedStore *store;
    bool closing;
};
struct BqtStateSlot {
    BqtStateSlot *next;
    char *key;
    char *layout;
    size_t size;
    size_t alignment;
    uint32_t flags;
    BqtSharedThread *thread;
    bool constructing;
    void *value;
    BqtStateDestroy destroy;
};
struct BqtSharedStore {
    pthread_mutex_t mutex;
    pthread_key_t thread_key;
    BqtSharedThread *threads;
    BqtStateSlot *first;
    bool closing;
};

static void bqt_shared_thread_drop(void *value) {
    BqtSharedThread *thread = (BqtSharedThread *)value;
    BqtSharedStore *store = thread->store;
    pthread_mutex_lock(&store->mutex);
    // POSIX clears the key before this callback. Keep it visible while state
    // destructors run, so recursive reads use the same thread identity.
    pthread_setspecific(store->thread_key, thread);
    thread->closing = true;
    BqtStateSlot **link = &store->first;
    while (*link) {
        BqtStateSlot *slot = *link;
        if (slot->thread != thread) { link = &slot->next; continue; }
        slot->destroy(slot->value);
        // A destructor may initialize unrelated process-wide state.
        link = &store->first;
        while (*link != slot) link = &(*link)->next;
        *link = slot->next;
        free(slot->key); free(slot->layout); free(slot);
        link = &store->first;
    }
    BqtSharedThread **owner = &store->threads;
    while (*owner != thread) owner = &(*owner)->next;
    *owner = thread->next;
    pthread_setspecific(store->thread_key, NULL);
    free(thread);
    pthread_mutex_unlock(&store->mutex);
}

static void *bqt_shared_acquire(void *context, const char *key, const char *layout,
                              size_t size, size_t alignment, uint32_t flags,
                              BqtStateCreate create, void *argument,
                              BqtStateDestroy destroy, const char **error) {
    BqtSharedStore *store = (BqtSharedStore *)context;
    *error = NULL;
    if (!store || !key || !*key || !layout || !size || !alignment || !create || !destroy
            || (flags & ~BQT_RUNTIME_THREAD_LOCAL)) {
        *error = "Invalid shared Qt runtime storage request";
        return NULL;
    }
    pthread_mutex_lock(&store->mutex);
    BqtSharedThread *thread = NULL;
    if (flags & BQT_RUNTIME_THREAD_LOCAL) {
        thread = (BqtSharedThread *)pthread_getspecific(store->thread_key);
        if (!thread && !store->closing) {
            thread = (BqtSharedThread *)calloc(1, sizeof(*thread));
            if (thread && !pthread_setspecific(store->thread_key, thread)) {
                thread->store = store;
                thread->next = store->threads;
                store->threads = thread;
            } else { free(thread); thread = NULL; }
        }
        if (!thread) {
            *error = "Cannot acquire Qt runtime thread storage";
            pthread_mutex_unlock(&store->mutex);
            return NULL;
        }
    }
    for (BqtStateSlot *slot = store->first; slot; slot = slot->next) {
        if (strcmp(slot->key, key)) continue;
        if (slot->size != size || slot->alignment != alignment || slot->flags != flags
                || strcmp(slot->layout, layout)) {
            *error = "Native Qt modules disagree on shared runtime storage";
            pthread_mutex_unlock(&store->mutex);
            return NULL;
        }
        if (slot->thread != thread) continue;
        if (slot->constructing) {
            *error = "Recursive initialization of the same Qt runtime storage";
            pthread_mutex_unlock(&store->mutex);
            return NULL;
        }
        void *value = slot->value;
        pthread_mutex_unlock(&store->mutex);
        return value;
    }
    if (store->closing || (thread && thread->closing)) {
        *error = "Qt runtime storage is shutting down";
        pthread_mutex_unlock(&store->mutex);
        return NULL;
    }
    BqtStateSlot *slot = (BqtStateSlot *)calloc(1, sizeof(*slot));
    if (slot) {
        slot->key = strdup(key);
        slot->layout = strdup(layout);
    }
    if (!slot || !slot->key || !slot->layout) {
        if (slot) { free(slot->key); free(slot->layout); free(slot); }
        *error = "Cannot allocate shared Qt runtime storage";
        pthread_mutex_unlock(&store->mutex);
        return NULL;
    }
    slot->size = size;
    slot->alignment = alignment;
    slot->flags = flags;
    slot->thread = thread;
    slot->constructing = true;
    slot->destroy = destroy;
    slot->next = store->first;
    store->first = slot;
    slot->value = create(argument);
    if (!slot->value) {
        // A recursive initializer may have inserted other storage in front.
        BqtStateSlot **link = &store->first;
        while (*link != slot) link = &(*link)->next;
        *link = slot->next;
        free(slot->key); free(slot->layout); free(slot);
        *error = "Cannot initialize shared Qt runtime storage";
        pthread_mutex_unlock(&store->mutex);
        return NULL;
    }
    slot->constructing = false;
    // Nested initialization must finish before its dependent is considered
    // initialized, matching C++'s reverse-completion destruction order.
    BqtStateSlot **link = &store->first;
    while (*link != slot) link = &(*link)->next;
    *link = slot->next;
    slot->next = store->first;
    store->first = slot;
    void *value = slot->value;
    pthread_mutex_unlock(&store->mutex);
    return value;
}

static bool bqt_shared_store_init(BqtSharedStore *store, BqtRuntimeServices *services) {
    memset(store, 0, sizeof(*store));
    pthread_mutexattr_t attributes;
    if (pthread_mutexattr_init(&attributes)) return false;
    int status = pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE);
    if (!status) status = pthread_mutex_init(&store->mutex, &attributes);
    pthread_mutexattr_destroy(&attributes);
    if (status) return false;
    if (pthread_key_create(&store->thread_key, bqt_shared_thread_drop)) {
        pthread_mutex_destroy(&store->mutex);
        return false;
    }
    services->version = BQT_RUNTIME_SERVICES_VERSION;
    services->context = store;
    services->acquire = bqt_shared_acquire;
    return true;
}

static bool bqt_shared_store_shutdown(BqtSharedStore *store) {
    pthread_mutex_lock(&store->mutex);
    store->closing = true;
    BqtSharedThread *current = (BqtSharedThread *)pthread_getspecific(store->thread_key);
    if (current) bqt_shared_thread_drop(current);
    if (store->threads) {
        // Native workers must quiesce before the process-wide runtime dies.
        // Keep all storage valid so their TLS destructors can still finish.
        pthread_mutex_unlock(&store->mutex);
        return false;
    }
    // Destruction reverses first initialization, including nested dependencies.
    while (store->first) {
        BqtStateSlot *slot = store->first;
        slot->destroy(slot->value);
        BqtStateSlot **link = &store->first;
        while (*link != slot) link = &(*link)->next;
        *link = slot->next;
        free(slot->key); free(slot->layout); free(slot);
    }
    pthread_mutex_unlock(&store->mutex);
    pthread_key_delete(store->thread_key);
    pthread_mutex_destroy(&store->mutex);
    return true;
}
