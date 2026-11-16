# Bend types in QML

`QObject.define(name, properties)` declares a runtime class derived from QObject.
Use the native base's `.define` function to select another base, for example
`QQuickItem.define(name, properties)`. These functions return an `ObjectType` schema;
they do not create an instance. `Property.define`, `readOnly` and `constant` take
a name and a typed
argument descriptor, such as `string()`, `int32()`, `variantMap()` or
`QPushButton.arg()`. All these descriptors have the common type `TypeDescriptor`;
they also describe signal arguments, method arguments/results and conversions.
`ObjectType.withSignals` and `withMethods` add declarations.
`ObjectType.new(~schema)` uses the default native constructor. A generated
`Base.newAs(~schema, ...)` selects another constructor and returns the typed
instance. The advanced `ObjectType.attachUsing(~schema, acquire)` helper attaches
a schema to a `Base.newOverride(...)` action; `ObjectType.attach` accepts an
existing compatible object. Prefer `new` or `newAs` for ordinary construction.
Only generated subclassable QObject bases expose
`.define()`; final C++ classes are excluded. QQmlPropertyMap uses `new` or `newAs`
so its open metadata is constructed on the declared schema. Other native objects
that already manage incompatible dynamic metadata return ENOTSUP.
`ObjectType.derive(~parentSchema, name, properties)` declares a subclass of an
existing Bend schema. It inherits its properties, signals, methods and native
base. For example:

```python
def Card() -> Qt.ObjectType:
  Qt.QQuickItem.define("Card", [title()])

def DetailedCard() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Card(), "DetailedCard", [detail()])
```

`ObjectType.Instance(schema)` preserves the class name in the Bend type.
Use schema-aware helpers directly on that instance, for example
`ObjectType.set(~Card(), ~title(), card, "Hello")` and
`ObjectType.get(~Card(), ~title(), card)`. `call`, `handle`, `emit`, `connect`,
property accessor handlers and binding helpers follow the same pattern.
`ObjectType.asNativeBase` exposes inherited native operations and virtual handlers;
`as_QObject` passes it to Qt/QML. `ObjectType.arg(~schema)` carries that concrete
class in properties, signals and method arguments/results. `reference(name)`
supports self-references and mutually referring classes. Null references work
before that class is defined; a nonnull reference requires its definition.
Casts validate the native class, and a class name cannot be reused for a different
schema. Bound native class, enum and argument type names are reserved, including
before their metatypes are registered. A derived schema must have its own name.
Class and member names support Unicode identifiers.

`asNativeBase` returns the native base selected by the schema, including through
Bend schema inheritance. From that value, generated `Type.as_Ancestor` functions
select any exposed native ancestor without a runtime cast. `Type.cast(object)`
checks a native target, and `ObjectType.cast(~schema, object)` checks a Bend schema
target. These views share the same native object and ownership.

Properties have native storage, default values and automatic change signals.
For a public copyable non-QObject object type, `Class.valueArg()` selects an
owning native value instead of the pointer supplied by `Class.arg()`. This
distinguishes `QCommandLineOption` from `QCommandLineOption*` without introducing
another Bend value type. Classes already exposed as values use their ordinary
owning `arg()` descriptor.
Stored types and nonvoid method results must support owning copies. Values
without a default constructor start uninitialized; initialize their storage or
install a getter before reading them. An uninitialized read returns ENODATA.
A QVariant property starts with an invalid QVariant.
A property carrying arbitrary Bend Data must be initialized before its first
read; there is no default value for an arbitrary Data type. A QML class's
initializer is the place to set it. Direct Bend calls can return copyable values
without a default constructor. Native method output assignment additionally
requires an assignable result type. QML's JavaScript exposure follows Qt's value
type registration; a QVariant property can carry values without a QML value type.
`Property.get`, `set` and `writeStorage` use their typed descriptor. `writeStorage` updates
the backing value, including read-only properties; constants can be initialized
before their first read. `handleGetter` and `handleSetter` install typed Bend
accessors. Use `readStorage`/`writeStorage` inside those handlers to avoid recursion.
`writeStorage` emits the property's generated `nameChanged()` signal when the value
changes. A setter using external backing storage calls `Property.notify` after
changing that value. Constants have no setter or change signal; initialize
them with `writeStorage` before their first ordinary read.

`Property.withReset(property)` declares a Qt RESET function.
`Property.handleResetter(~property, ~S, ~handler, object, state)` installs its
`S -> Action(Unit)` handler on an instance. `Property.reset(~property, object)`,
`QMetaProperty.reset` and QML assignment of `undefined` invoke it. The handler
chooses the context-specific default and updates the property using `set` or
`writeStorage`. Reset can also be enabled on read-only properties. Calling reset without
a declared RESET returns ENOTSUP; a missing reset handler returns ENOSYS.

`Property.withStored(property, False{})` sets Qt's STORED metadata to false;
the default is true. This controls whether state-saving tools should save the
property independently. Its getter, setter, backing storage and change signal
continue to work. It does not change the behavior of `Property.writeStorage`. The
[property example](../examples/qt612/properties.bend) covers notifications,
constants, resetting, metadata inspection and QML.

The property API also exposes `withDesignable`, `withScriptable`, `withUser`,
`withFinal`, `withVirtual`, `withOverride`, `withRequired` and `withBindable`.
Each modifier takes a property and a Bool. `withRevision(property, minor)` and
`withVersionRevision(property, major, minor)` supply QML metadata revisions.
`withNotify(property, signal)` selects a signal with zero arguments or one
argument of the property's type. `withoutNotify(property)` omits the signal.
`ObjectType.withClassInfo` adds class metadata, and `withDefaultProperty` declares
QML's default property. The workspace's [property coverage table](../docs/property-system.md)
maps every Qt property attribute to its API and native fixture.

QObject property references are borrowed and guarded; parent or scope ownership
must keep them alive. Destroyed pointer targets read as null. Containers with
destroyed references fail with ESTALE. Qt value arguments remain owning copies.

`list(~element)` declares a native `QList` property, as a C++ `QList`
property would. QML reads it as a JavaScript array and can use it directly as
the model of a `Repeater` or `ListView`, with `modelData` for each element.
Setting it from Bend emits its change signal, so views and bindings follow the
new list. QML can assign an array to a writable list property. Elements can be
numbers, strings, QVariant, native or Bend-declared QObject classes
(`list(~ObjectType.arg(~Card()))`), values declared with `ValueType.define`,
and further lists (`list(~list(~int32()))`). QML reads the fields of such
values without `ValueType.register`, as it reads a plain `Q_GADGET`. An element
type without a compiled `QList` gets one at run time under the same name, such
as `QList<Card*>`, and QML iterates it through Qt's ordinary sequence
conversion. A list holding a destroyed object reads as ESTALE. The
[list model fixture](../scripts/fixtures/list-models.bend) checks these cases.

`Enum.define("ExampleCard::Status", [Enum.key("Idle", 0), Enum.key("Ready", 1)])`
declares a native enumeration. Add it to its owning class using
`ObjectType.withEnums(schema, [Status()])`, and use `Enum.arg(~Status())` in
properties, signals and methods. The qualified name supplies its scope before
the class exists, allowing properties to refer to their own class's enums.
Enums can also be used in signals and QVariant before that class exists.
`QMetaType.metaObject` and `QMetaEnum` expose an immutable namespace-style owner
at that point. Later declarations in the same scope and attaching the QObject
class update future lookups while existing metadata handles stay valid.
`Enum.value(~Status(), "Ready")` returns a typed `Action(Enum.Value(Status()))`.
Distinct qualified enum names remain distinct Bend and Qt metatypes.
`withFlags`, `withScoped`, `withUnsigned` and `with64Bit` select the native
representation; `withAlias` supplies a Q_FLAG enum-name alias. The default is a
scoped, signed 32-bit enum. Use `signedKey`, `wideKey` or `signedWideKey` for
negative and 64-bit entries. `Enum.bits` and `signed` recover the full numeric
representation; `or`, `and` and `xor` combine values of the same declared type.
QMetaEnum exposes these definitions, and a registered class exposes values in
QML as `Card.Status.Ready` and `Card.Ready`. QML's native JavaScript numeric
precision still applies to 64-bit enum values. Qt 6.12's QML enum constant
lookup also truncates values to 32 bits, even though native and Bend metadata
preserve all 64 bits. The [native enum control](../examples/qt612/runtime-enums-native.cpp)
checks that behavior against an ordinary moc-generated class.

`QVariant.fromValue(~argumentDescriptor, value)` boxes any supported native
descriptor, including scalar and enum values, typed containers, concrete QObject
pointers, Bend-authored enum values and `arg(~Payload)` data. The matching
`QVariant.toValue(~argumentDescriptor, variant)` checks the stored metatype;
opaque data also checks its Bend type witness. It returns a failure rather than
silently constructing a default value for the wrong type. `variant()` as the
descriptor returns a copy of the whole QVariant.
`canConvert(~descriptor, variant)` and `convert(~descriptor, variant)` expose
Qt's explicit native conversion checks and in-place conversion. The conversion
returns Bool and follows Qt's behavior when conversion fails. `new`, `clear`,
`isValid`, `isNull` and `metaType` supply the ordinary QVariant operations.
Copied values retain their native metadata and external-data origins through
immutable private leases. Boxed QObject references are retained while the
variant needs them; native deletion and changing dynamic metadata still produce
the normal stale-origin errors. Existing per-class `from_QClass`/`to_QClass`
helpers remain available. The [generic QVariant fixture](../scripts/fixtures/generic-variants.bend)
checks native types, conversions, containers, opaque data and metadata snapshots.

Stored property values, signal arguments and method/getter results carry these
origin leases across native copies and callback scope cleanup. This includes
raw metadata descriptors and values backed by external storage. A stored
QObject pointer remains borrowed. Dynamic metadata delivered from a native
worker must have a live observed origin; compiled Qt metadata and immutable
Bend schemas can be delivered directly.

`Method.define(name, argumentDescriptors, resultDescriptor)` declares a named
invokable. `Method.handle(~method, ~S, ~handler, object, state)` installs the
curried typed handler; `Method.call(~method, object, args...)` calls it in Bend.
QML uses `object.method(args...)` directly. Use `unit()` for a void result.
Methods and accessors must answer synchronously, as native Qt methods do.
`Method.withArgumentNames(method, names)` supplies the parameter names returned
by `QMetaMethod.parameterNames`; `withTag(method, tag)` supplies its Qt method
tag. `withRevision(method, minor)` and `withVersionRevision(method, major, minor)`
control member visibility when the class is registered with a corresponding QML
metadata revision. `withAccess(method, QMetaMethod.Access.Private())` selects
access metadata; the default is public. `withInvokable(method, True{})` declares
an ordinary invokable method instead of the default slot. Named methods may
override compatible inherited methods while keeping their return type.
The [method metadata fixture](../scripts/fixtures/method-metadata.bend)
checks introspection, Bend dispatch, QML revision filtering and overrides.
New QObjects returned by a member handler, including objects inside QVariant
containers, move from the handler's scope into the calling operation's scope.
Existing borrowed references retain their original ownership.

`Qml.registerSingletonInstance(~schema, uri, major, minor, name, instance)`
exports an existing instance for one engine. `registerSingleton` creates one
default instance per engine; `registerSingletonFactory` accepts a typed Bend
factory for initialization. Factories return unparented objects or engine
children; the engine owns them. These functions return `Qml.Registration(schema)`,
a typed registration controller distinct from an object instance. Use
`Qml.Registration.with(~schema, A, acquire, body)` for an explicit local lifetime;
automatic scopes also release it. Engines retain registrations they use until
destruction. `Qml.RegistrationHandle` covers schema-free registrations from
`registerUnavailable` and `registerScriptSingleton` and has its own lifetime
helpers. `registerSource` and `ValueType.register` return Qt type IDs.
Objects can also be supplied through `QQmlContext.setContextProperty`.
Runtime class declarations alone do not register a creatable QML element.
`Qml.registerSource` remains available for QML composite elements.

`Qml.registerType(~schema, uri, major, minor, name)` makes the class creatable
with normal QML syntax, such as `Card { title: "Hello" }`. A generated native
base with supported construction metadata is required. A default constructor
needs no additional handler. For another constructor, install
`Qml.handleConstructor` and return an instance constructed with `Base.newAs`.
It constructs the native object directly in Qt's allocation. Install a typed
initializer with
`Qml.handleCreate(~schema, ~S, ~initializer, registration, state)`, where the
initializer is `S -> ObjectType.Instance(schema) -> Action(Unit)`. It runs once
per new instance, after native construction and before QML bindings are
evaluated. It can initialize properties and install method or virtual handlers.
QQuickItem bases also retain their normal QML construction lifecycle.

`registerTypeRevision` and `registerTypeVersionRevision` select the member
revision visible to a registration. Singleton instance, default and factory
registrations have matching revision functions. Qt 6.12 records singleton
revisions but does not apply member revision filtering to JavaScript singleton
property lookup. The native control in
[singleton-revision-native.cpp](../examples/qt612/singleton-revision-native.cpp)
checks this Qt behavior.

`Qml.registerUncreatable(~schema, uri, major, minor, name, reason)` registers a
named type for property declarations and objects supplied from Bend, while
attempting to instantiate it in QML reports `reason`. Its native base need not
have a default constructor. `Qml.registerAnonymous(~schema, uri, major)` makes a
type recognizable when it occurs in a native property without introducing a QML
element name. It cannot be instantiated or named in QML property declarations.
`Qml.registerUnavailable(uri, major, minor, name, reason)` reserves an element
name whose construction reports the supplied reason, without requiring a class
schema. These functions return scoped registration handles like `registerType`.
The [registration modes fixture](../scripts/fixtures/qml-registration-modes.bend)
checks native property access, construction rejection messages and cleanup.

`ObjectType.withAttached(schema, attachedSchema)` declares an attached type.
`withExtension(schema, extensionSchema)` adds an extension. Their QML syntax
is `Card.label` and `card.detail`, respectively. The default factory creates
the declared QObject class. `Qml.handleAttached` and `handleExtension` install
factories of type `S -> QObject -> Action(ObjectType.Instance(relatedSchema))`.
The QObject argument is the target being attached to or extended. The factory's
result becomes its child before the callback scope closes. `Qml.attached` and
`Qml.extension` return the same typed objects from Bend. Different registrations
have separate attached caches. QML-created instances retain their registration
until they are destroyed.
Related types without a default constructor use these typed factories.
QQmlPropertyMap works as an ordinary, creatable or attached class; Qt/PySide
cannot expose its open metadata as QML extension metadata, so that combination
returns ENOTSUP. Singletons can have extensions, but Qt's singleton registration
ABI has no attached-type factory. These upstream boundaries have reproducible
controls in [property-map-extension-pyside.py](../examples/qt612/property-map-extension-pyside.py)
and the singleton fixture.

See the [creatable QML example](../examples/qt612/qml-creatable.bend) for the
declaration, initializer, factories and QML side together.

The [QML types example](../examples/qt612/qml-types.bend) uses named typed
members. Numeric `BendBridge.invoke` dispatch is an internal compatibility
mechanism under `Internal.Qml`, and is unnecessary for authoring these objects.
Runtime metadata and pointer metatypes use the Qt 6 moc/public-header ABI.
Immutable schemas live for the process lifetime because Qt/QML caches can
retain their addresses. Class/member counts follow Qt's native index range.
