// A typed facade over Qt's ordinary property binding engine. The declared
// metatype is preserved, including runtime-defined QObject pointer metatypes.
// Qt executes each binding against a real QPropertyData<T> temporary; QVariant
// is only the owning transport between this facade and the QObject fields.
//
// One Storage class serves every value type. The few steps that need T (the
// QPropertyData<T> temporary, T's operator== and assignment, and the typed
// QBindableInterface) are small per-type functions in Operations; the binding
// logic itself is compiled once rather than once for each of several thousand
// property types.
#include <QtCore/qproperty.h>
#include <QtCore/qvariant.h>
#include <functional>
#include <memory>
#include <optional>
#include <type_traits>
#include <cerrno>

namespace BendPropertyBindings {
using Read = std::function<std::optional<QVariant>(bool storage)>;
using Write = std::function<bool(QVariant value, bool from_binding)>;

// The per-type steps. equals is null when T has no operator==, matching a
// binding that always reports a change.
struct Operations {
    bool variant_value;
    bool dynamic_capable;
    QMetaType (*meta)();
    bool (*equals)(const void *next, const QUntypedPropertyData *target);
    void (*store)(QUntypedPropertyData *target, const void *next);
    void (*assign)(void *destination, const void *next);
    bool (*run)(QMetaType type, QtPrivate::QPropertyBindingFunction function, const void *previous,
                QMetaType declared, QVariant &result);
    const QtPrivate::QBindableInterface *typed[2];
};

class Storage final : public QUntypedPropertyData, public std::enable_shared_from_this<Storage> {
    const QMetaType declared_type;
    const Operations *const operations;
    Read read_value;
    Write write_value;
    QtPrivate::QPropertyBindingData bindings;
    QUntypedPropertyBinding current;
    bool internal_evaluation = false, evaluation_failed = false;
    int read_error = 0;

    class Interface final : public QUntypedBindable {
    public:
        Interface(Storage *data, const QtPrivate::QBindableInterface *interface)
            : QUntypedBindable(data, interface) {}
    };

    const void *value_data(const QVariant &value) const {
        return operations->variant_value ? static_cast<const void *>(&value) : value.constData();
    }
    QVariant pack(const void *value) const {
        return operations->variant_value ? *static_cast<const QVariant *>(value) : QVariant(declared_type, value);
    }
    std::optional<QVariant> read() const {
        track();
        return read_value(false);
    }
    // Writes next into a binding target of the declared type; false when equal.
    bool store(QUntypedPropertyData *target, const void *next) const {
        if (operations->equals && operations->equals(next, target)) return false;
        operations->store(target, next);
        return true;
    }
    static bool evaluate(QMetaType type, QUntypedPropertyData *data,
                         QtPrivate::QPropertyBindingFunction function) {
        auto *self = static_cast<Storage *>(data);
        auto keep = self->shared_from_this();
        auto scope = self->evaluationScope ? self->evaluationScope() : std::shared_ptr<void>{};
        self->evaluation_failed = false;
        self->read_error = 0;
        auto previous = self->read_value(true);
        if (!previous) {
            if (self->internal_evaluation && (!self->read_error || self->read_error == ENODATA))
                return function.vtable->call(type, nullptr, function.functor);
            self->evaluation_failed = true;
            return false;
        }
        QVariant next;
        if (!self->operations->run(type, function, self->value_data(*previous), self->declared_type, next))
            return false;
        if (self->write_value(std::move(next), true)) return true;
        self->evaluation_failed = true;
        return false;
    }
    QUntypedPropertyBinding set_binding(const QUntypedPropertyBinding &binding, bool internal = false) {
        auto previous = current;
        const bool previous_internal = internal_evaluation;
        internal_evaluation = internal;
        evaluation_failed = false;
        if (!internal && !binding.isNull()) {
            read_error = 0;
            if (!read_value(true)) {
                evaluation_failed = true;
                internal_evaluation = previous_internal;
                return previous;
            }
        }
        current = binding;
        bindings.setBinding(binding, this, nullptr, &evaluate);
        return previous;
    }
    QUntypedPropertyBinding make_binding(const QPropertyBindingSourceLocation &location) const {
        std::weak_ptr<const Storage> weak = shared_from_this();
        auto evaluate_source = [weak](QMetaType, QUntypedPropertyData *data) -> bool {
            auto self = weak.lock();
            if (!self) return false;
            auto value = self->read();
            if (!value) return false;
            return self->store(data, self->value_data(*value));
        };
        return QUntypedPropertyBinding(declared_type, std::move(evaluate_source), location);
    }
    static void typed_getter(const QUntypedPropertyData *data, void *destination) {
        auto *self = static_cast<const Storage *>(data);
        if (auto value = self->read()) self->operations->assign(destination, self->value_data(*value));
    }
    static void dynamic_getter(const QUntypedPropertyData *data, void *destination) {
        // The tagged metatype query is the protocol used by Qt's QML proxy
        // bindable and handled by QUntypedBindable itself. Runtime QObject
        // pointers, enums and QML lists use it; their declared native storage
        // remains typed and aligned.
        auto pointer = reinterpret_cast<quintptr>(destination);
        if (pointer & QtPrivate::QBindableInterface::MetaTypeAccessorFlag) {
            *reinterpret_cast<QMetaType *>(pointer & ~QtPrivate::QBindableInterface::MetaTypeAccessorFlag) =
                static_cast<const Storage *>(data)->declared_type;
            return;
        }
        typed_getter(data, destination);
    }
    static void setter(QUntypedPropertyData *data, const void *source) {
        auto *self = static_cast<Storage *>(data);
        self->write_value(self->pack(source), false);
    }
    static QUntypedPropertyBinding get_binding(const QUntypedPropertyData *data) {
        return static_cast<const Storage *>(data)->current;
    }
    static QUntypedPropertyBinding replace_binding(QUntypedPropertyData *data, const QUntypedPropertyBinding &binding) {
        return static_cast<Storage *>(data)->set_binding(binding);
    }
    static QUntypedPropertyBinding new_binding(const QUntypedPropertyData *data, const QPropertyBindingSourceLocation &location) {
        return static_cast<const Storage *>(data)->make_binding(location);
    }
    static void observe(const QUntypedPropertyData *data, QPropertyObserver *observer) {
        observer->setSource(static_cast<const Storage *>(data)->bindings);
    }
    static const QtPrivate::QBindableInterface *dynamic_interface(bool writable) {
        static const QtPrivate::QBindableInterface values[2] = {
            {&dynamic_getter, nullptr, &get_binding, nullptr, &new_binding, &observe, nullptr},
            {&dynamic_getter, &setter, &get_binding, &replace_binding, &new_binding, &observe, nullptr},
        };
        return &values[writable ? 1 : 0];
    }

public:
    Storage(QMetaType type, const Operations *operations, Read read, Write write)
        : declared_type(type), operations(operations), read_value(std::move(read)), write_value(std::move(write)) {}
    std::function<std::shared_ptr<void>()> evaluationScope;
    bool allowsInitialization() const { return internal_evaluation; }
    void readFailed(int code) { read_error = code; }
    QMetaType metaType() const { return declared_type; }
    void track() const { bindings.registerWithCurrentlyEvaluatingBinding(); }
    // Manual writes remove a binding even when the new value compares equal.
    void clear() { bindings.removeBinding(); current = {}; internal_evaluation = false; evaluation_failed = false; }
    void changed() { bindings.notifyObservers(this); }
    QPropertyBindingError bindingError() const {
        return evaluation_failed ? QPropertyBindingError(QPropertyBindingError::EvaluationError,
            QStringLiteral("The property binding could not read or write its value")) : current.error();
    }
    QUntypedBindable bindable(bool writable) {
        if (writable) {
            auto scope = evaluationScope ? evaluationScope() : std::shared_ptr<void>{};
            if (!read_value(true)) writable = false;
        }
        const bool foreign = declared_type != operations->meta();
        if (foreign && (operations->dynamic_capable || declared_type.flags().testFlag(QMetaType::IsQmlList)))
            return Interface(this, dynamic_interface(writable));
        return Interface(this, operations->typed[writable ? 1 : 0]);
    }
    bool setEvaluator(Read compute) {
        auto succeeded = std::make_shared<bool>(true);
        std::weak_ptr<Storage> weak = shared_from_this();
        auto evaluate_value = [compute = std::move(compute), succeeded, weak](QMetaType, QUntypedPropertyData *data) -> bool {
            auto self = weak.lock();
            if (!self) { *succeeded = false; return false; }
            auto value = compute(false);
            if (!value) { *succeeded = false; self->evaluation_failed = true; return false; }
            const void *next = self->value_data(*value);
            if (!data) {
                if (self->write_value(self->pack(next), true)) return true;
                *succeeded = false; self->evaluation_failed = true;
                return false;
            }
            return self->store(data, next);
        };
        set_binding(QUntypedPropertyBinding(declared_type, std::move(evaluate_value), {}), true);
        return *succeeded && !bindingError().hasError();
    }

    template<class T> struct Typed {
        static QMetaType meta() { return QMetaType::fromType<T>(); }
        static bool equals(const void *next, const QUntypedPropertyData *target) {
            return *static_cast<const T *>(next) == static_cast<const QPropertyData<T> *>(target)->valueBypassingBindings();
        }
        static void store(QUntypedPropertyData *target, const void *next) {
            static_cast<QPropertyData<T> *>(target)->setValueBypassingBindings(*static_cast<const T *>(next));
        }
        static void assign(void *destination, const void *next) {
            *static_cast<T *>(destination) = *static_cast<const T *>(next);
        }
        static bool run(QMetaType type, QtPrivate::QPropertyBindingFunction function, const void *previous,
                        QMetaType declared, QVariant &result) {
            QPropertyData<T> temporary(*static_cast<const T *>(previous));
            if (!function.vtable->call(type, &temporary, function.functor)) return false;
            // A reference (or an elided prvalue): types such as
            // QWebSocketCorsAuthenticator only have an explicit copy constructor.
            decltype(auto) value = temporary.valueBypassingBindings();
            if constexpr (std::is_same_v<T, QVariant>) result = value;
            else result = QVariant(declared, &value);
            return true;
        }
        static constexpr auto equality() {
            if constexpr (QTypeTraits::has_operator_equal_v<T>) return &equals;
            else return static_cast<bool (*)(const void *, const QUntypedPropertyData *)>(nullptr);
        }
        static inline const QtPrivate::QBindableInterface interfaces[2] = {
            {&typed_getter, nullptr, &get_binding, nullptr, &new_binding, &observe, &meta},
            {&typed_getter, &setter, &get_binding, &replace_binding, &new_binding, &observe, &meta},
        };
        static inline const Operations operations = {
            std::is_same_v<T, QVariant>, std::is_pointer_v<T> || (std::is_integral_v<T> && sizeof(T) >= 4), &meta,
            equality(), &store, &assign, &run, {&interfaces[0], &interfaces[1]}};
    };
};

template<class T> static std::shared_ptr<Storage> make(QMetaType type, Read read, Write write) {
    if constexpr (std::is_copy_constructible_v<T> && std::is_copy_assignable_v<T>)
        return std::make_shared<Storage>(type, &Storage::Typed<T>::operations, std::move(read), std::move(write));
    return {};
}
} // namespace BendPropertyBindings
