// A typed facade over Qt's ordinary property binding engine. The declared
// metatype is preserved, including runtime-defined QObject pointer metatypes.
// Qt executes each binding against a real QPropertyData<T> temporary; QVariant
// is only the owning transport between this facade and the QObject fields.
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

class Storage : public QUntypedPropertyData, public std::enable_shared_from_this<Storage> {
protected:
    const QMetaType declared_type;
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

    Storage(QMetaType type, Read read, Write write)
        : declared_type(type), read_value(std::move(read)), write_value(std::move(write)) {}

public:
    virtual ~Storage() = default;
    virtual QUntypedBindable bindable(bool writable) = 0;
    virtual bool setEvaluator(Read compute) = 0;
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
};

template<class T> class TypedStorage final : public Storage {
    static const T &value_data(const QVariant &value) {
        if constexpr (std::is_same_v<T, QVariant>) return value;
        else return *static_cast<const T *>(value.constData());
    }
    QVariant pack(const T &value) const {
        if constexpr (std::is_same_v<T, QVariant>) return value;
        else return QVariant(declared_type, &value);
    }
    std::optional<T> read() const {
        track();
        auto value = read_value(false);
        return value ? std::optional<T>(std::in_place, value_data(*value)) : std::nullopt;
    }
    static bool evaluate(QMetaType type, QUntypedPropertyData *data,
                         QtPrivate::QPropertyBindingFunction function) {
        auto *self = static_cast<TypedStorage *>(data);
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
        QPropertyData<T> temporary(value_data(*previous));
        bool changed = function.vtable->call(type, &temporary, function.functor);
        if (!changed) return false;
        if (self->write_value(self->pack(temporary.valueBypassingBindings()), true)) return true;
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
            auto self = std::static_pointer_cast<const TypedStorage>(weak.lock());
            if (!self) return false;
            auto value = self->read();
            if (!value) return false;
            const T &next = *value;
            auto *target = static_cast<QPropertyData<T> *>(data);
            if constexpr (QTypeTraits::has_operator_equal_v<T>) {
                if (next == target->valueBypassingBindings()) return false;
            }
            target->setValueBypassingBindings(next);
            return true;
        };
        return QUntypedPropertyBinding(declared_type, std::move(evaluate_source), location);
    }
    template<bool Writable, bool DynamicType> static const QtPrivate::QBindableInterface *interface() {
        static const QtPrivate::QBindableInterface value = {
            [](const QUntypedPropertyData *data, void *destination) {
                auto *self = static_cast<const TypedStorage *>(data);
                if constexpr (DynamicType) {
                    // The tagged metatype query is the protocol used by Qt's
                    // QML proxy bindable and handled by QUntypedBindable itself.
                    // Runtime QObject pointers, enums and QML lists use it;
                    // their declared native storage remains typed and aligned.
                    auto pointer = reinterpret_cast<quintptr>(destination);
                    if (pointer & QtPrivate::QBindableInterface::MetaTypeAccessorFlag) {
                        *reinterpret_cast<QMetaType *>(pointer & ~QtPrivate::QBindableInterface::MetaTypeAccessorFlag) = self->declared_type;
                        return;
                    }
                }
                if (auto value = self->read()) *static_cast<T *>(destination) = *value;
            },
            Writable ? +[](QUntypedPropertyData *data, const void *source) {
                auto *self = static_cast<TypedStorage *>(data);
                self->write_value(self->pack(*static_cast<const T *>(source)), false);
            } : nullptr,
            [](const QUntypedPropertyData *data) {
                return static_cast<const TypedStorage *>(data)->current;
            },
            Writable ? +[](QUntypedPropertyData *data, const QUntypedPropertyBinding &binding) {
                return static_cast<TypedStorage *>(data)->set_binding(binding);
            } : nullptr,
            [](const QUntypedPropertyData *data, const QPropertyBindingSourceLocation &location) {
                return static_cast<const TypedStorage *>(data)->make_binding(location);
            },
            [](const QUntypedPropertyData *data, QPropertyObserver *observer) {
                observer->setSource(static_cast<const TypedStorage *>(data)->bindings);
            },
            DynamicType ? nullptr : +[] { return QMetaType::fromType<T>(); }
        };
        return &value;
    }

public:
    TypedStorage(QMetaType type, Read read, Write write)
        : Storage(type, std::move(read), std::move(write)) {}
    QUntypedBindable bindable(bool writable) override {
        if (writable) {
            auto scope = evaluationScope ? evaluationScope() : std::shared_ptr<void>{};
            if (!read_value(true)) writable = false;
        }
        if constexpr (std::is_pointer_v<T> || (std::is_integral_v<T> && sizeof(T) >= 4)) {
            if (declared_type != QMetaType::fromType<T>())
                return Interface(this, writable ? interface<true, true>() : interface<false, true>());
        }
        if (declared_type.flags().testFlag(QMetaType::IsQmlList) && declared_type != QMetaType::fromType<T>())
            return Interface(this, writable ? interface<true, true>() : interface<false, true>());
        return Interface(this, writable ? interface<true, false>() : interface<false, false>());
    }
    bool setEvaluator(Read compute) override {
        auto succeeded = std::make_shared<bool>(true);
        std::weak_ptr<Storage> weak = shared_from_this();
        auto evaluate_value = [compute = std::move(compute), succeeded, weak](QMetaType, QUntypedPropertyData *data) -> bool {
            auto self = std::static_pointer_cast<TypedStorage>(weak.lock());
            if (!self) { *succeeded = false; return false; }
            auto value = compute(false);
            if (!value) { *succeeded = false; self->evaluation_failed = true; return false; }
            const T &next = value_data(*value);
            if (!data) {
                if (self->write_value(self->pack(next), true)) return true;
                *succeeded = false; self->evaluation_failed = true;
                return false;
            }
            auto *target = static_cast<QPropertyData<T> *>(data);
            if constexpr (QTypeTraits::has_operator_equal_v<T>) {
                if (next == target->valueBypassingBindings()) return false;
            }
            target->setValueBypassingBindings(next);
            return true;
        };
        set_binding(QUntypedPropertyBinding(declared_type, std::move(evaluate_value), {}), true);
        return *succeeded && !bindingError().hasError();
    }
};

template<class T> static std::shared_ptr<Storage> make(QMetaType type, Read read, Write write) {
    if constexpr (std::is_copy_constructible_v<T> && std::is_copy_assignable_v<T>)
        return std::make_shared<TypedStorage<T>>(type, std::move(read), std::move(write));
    return {};
}
} // namespace BendPropertyBindings
