# Qt property coverage

The property API follows [Qt 6.12's property system](https://doc.qt.io/qt-6/properties.html).
Property declarations are ordinary Bend values, and operations on an instance
return `Action`. The declarations follow the installed Qt 6.12 headers and the
pinned PySide `Property` implementation. Every Qt property attribute has an
implementation below. The canonical validation receipt in
`build/qt612/check/receipt.json` records the full package's verification status.
See [Bend types in QML](bend-qml-types.md) for schemas, typed member access and
registration examples.

| Qt feature | Bend API | Behavior exercised by the fixtures |
| --- | --- | --- |
| `READ` | `Property.get`, `Property.handleGetter` | A getter returns the declared value type. |
| `WRITE` | `Property.set`, `Property.handleSetter` | A setter receives the declared value type. |
| `MEMBER` | Default property storage, `readStorage`, `writeStorage` | Storage works without custom accessors. Internal access bypasses accessor handlers. |
| `RESET` | `Property.withReset`, `handleResetter`, `reset` | Bend, `QMetaProperty.reset` and QML `undefined` invoke the reset handler. |
| `NOTIFY` | Default `<name>Changed()`, `withNotify`, `withoutNotify`, `notify` | Notifications can have no arguments or carry the property's new value. |
| `REVISION` | `Property.withRevision`, `withVersionRevision` | Qt reports the encoded revision, and QML imports control access. |
| `DESIGNABLE` | `Property.withDesignable` | The metadata defaults to true and accepts false. |
| `SCRIPTABLE` | `Property.withScriptable` | The metadata defaults to true and accepts false. |
| `STORED` | `Property.withStored` | The metadata defaults to true. False preserves access, storage and notifications. |
| `USER` | `Property.withUser` | `QMetaObject.userProperty` finds the selected property. |
| `BINDABLE` | `Property.withBindable`, `bind`, `handleBinding`, `unbind`, `hasBinding` | Qt's binding engine tracks dependencies and preserves the declared metatype. |
| `CONSTANT` | `Property.constant` | A constant has no setter or notification. Initialize its storage before exposing its value. |
| `FINAL` | `Property.withFinal` | Derived Bend declarations cannot override a final property. |
| `VIRTUAL` | `Property.withVirtual` | The property advertises that it can be overridden. |
| `OVERRIDE` | `Property.withOverride` | The base must have a virtual property with the same name. Derived access resolves the derived declaration. |
| `REQUIRED` | `Property.withRequired` | QML rejects construction when a required property is missing. |

Boolean metadata modifiers take the property followed by a `Bool`. For example,
`Property.withDesignable(property, False{})` disables the DESIGNABLE flag.
`withRevision(property, minor)` supplies a minor revision, while
`withVersionRevision(property, major, minor)` supplies both segments. Each
version segment must be between 0 and 254.

The default declaration supplies backing storage and a change signal. A custom
setter that calls `Property.writeStorage` gets a notification when the value changes.
A setter that updates external storage calls `Property.notify` explicitly after
checking that the value changed. An explicit NOTIFY signal can be shared with
other properties or declared through `ObjectType.withSignals`.

Internal backing operations can update a read-only property. In particular,
`Property.writeStorage` and an internal binding can supply its value, while QML and
`QMetaProperty` still see a read-only property. Constant properties cannot receive
a binding that changes their value.

Backing storage with `BINDABLE` supplies the behavior of Qt's `READ default`
and `WRITE default`. A custom native bindable needs a copy-constructible and
copy-assignable value type, as required by the typed `QPropertyData<T>` storage
and `QBindable<T>` value operations. The property declaration itself only needs
an owning copy: a copyable type without copy assignment can still be read through
Qt's redirected-reference read protocol, without declaring `BINDABLE`. A missing
binding implementation fails explicitly when constructing the QObject; setting
the metadata bit alone does not create binding support.

## Value types and metadata

Properties use the same descriptors as signals and named methods. Native
descriptors cover numeric types, accessible native enums and flags, QObject pointers,
non-QObject pointers, copyable Qt metatypes and supported container instantiations. `Enum.arg` supplies
a Bend-declared Qt enum. `Qt.arg(~Payload)` transports an arbitrary Bend Data
value with a checked type witness. QML can retain and forward opaque Data values;
use an exported QObject or QVariant map when QML needs to inspect fields.

For a non-QObject class that PySide exposes as an object type, `Class.arg()`
preserves its pointer identity. A public copyable class also has
`Class.valueArg()` for a true native value copy. For example,
`QCommandLineOption.valueArg()` declares `QCommandLineOption`, while its default
`arg()` declares `QCommandLineOption*`. Both use the same Bend handle type.
Classes already exposed as values keep their owning `arg()` descriptor.

The container constructors select native instantiations from the generated
conversion inventory. They do not replace an unavailable native container with
a QVariant container. `list` also covers element types that have no compiled
`QList`, such as Bend-declared classes and values or nested lists: their
`QList` type is created at run time, and Qt and QML iterate it through the
ordinary sequence conversion. Unsupported signatures and descriptor types stay
visible in `coverage.json`.

This inventory is the boundary for native C++ metatypes. It does not claim codecs
for arbitrary plugin-defined C++ classes. Arbitrary Bend Data values use
`Qt.arg(~Payload)` instead. Borrowed string and byte view descriptors are not
silently registered as owning native property types: the pinned PySide runtime
also reports invalid property metatypes and unusable reads for `QStringView`,
`QLatin1StringView`, `QAnyStringView` and `QByteArrayView`. Native methods that take
those views still have their ordinary string or byte conversions.

Copyable native values do not need a default constructor. Such a property starts
uninitialized and returns ENODATA until its storage or getter supplies a value.
Native reflection uses Qt's reference-return protocol when the value cannot be
assigned to a default result. The binding engine also accepts initialized values
without a default constructor. QML JavaScript exposure still follows Qt's value
type registration; QVariant properties can carry opaque native values.

Enum and flag metadata is derived from the declared metatype, including
Bend-authored enums. QObject descriptors preserve their concrete native or Bend
schema type. List, map, hash, optional and pair descriptors select exact native
instantiations; a QVariantMap is not substituted for a different declared type.

Dynamic QObject properties use the ordinary `QObject.setProperty`, `property`
and `dynamicPropertyNames` APIs and QVariant values. Qt returns false from
`setProperty` when it adds a dynamic property; that successful native operation
is `Action` returning `False`, not an Action failure. Dynamic properties are
outside the static QMetaProperty declaration table and use
`QDynamicPropertyChangeEvent`, rather than an automatically declared NOTIFY
signal. Stored values retain their dependent metadata and external-data
snapshots. QObject pointers remain borrowed; reading a stored value after its
pointer target or metadata epoch expires fails with ESTALE. Replacing or
removing that stale value remains allowed. Returned QVariant copies carry
their own origins, so later property replacement cannot invalidate those copies.

The application observes native dynamic-property events before user event
filters and handlers. This also covers native code replacing a property that
Bend has already observed. It does not add helper objects to QObject.children.
Python-only descriptor documentation and deletion hooks have no extra Qt
property flag to implement.

The pinned PySide `Property(type, None, setter)` form advertises a write-only
Python descriptor, but its QMetaProperty and QObject native writes do not call
the setter. Bend declarations provide native READ/backing storage as required by
the documented Q_PROPERTY contract. A setter-only Python descriptor is not
counted as an additional working native Qt property mode.

`ObjectType.withClassInfo(schema, key, value)` adds `Q_CLASSINFO` metadata.
`withDefaultProperty(schema, name)` supplies QML's `DefaultProperty` entry.
`ObjectType.withEnums` exports Q_ENUM and Q_FLAG declarations through `QMetaEnum`
and QML. Qualified QObject and enum names follow C++ namespace spelling.

Register a type with `Qml.registerTypeRevision` or
`registerTypeVersionRevision` to select its visible metadata revision. A schema
can be registered at several module versions without changing its class identity.
Singleton registrations provide corresponding revision functions.
Qt 6.12 does not apply member revision filtering to JavaScript singleton property
lookup, even when the registration and member metadata carry revisions. The
[native singleton control](../examples/qt612/singleton-revision-native.cpp)
checks this behavior separately from ordinary QML element revision filtering.

## Verification checkpoint

The fixtures exercise native Qt reflection and QML. Their presence in this list
does not assert that the latest combined package has passed them:

* [Property examples](../examples/qt612/properties.bend) cover notifications,
  constants, reset handlers and STORED false.
* [Property attributes](../scripts/fixtures/property-attributes.bend) cover
  metadata, inheritance, class info, QML revisions and required properties.
* [Property bindings](../scripts/fixtures/property-bindings.bend) cover direct
  bindings, computed Bend bindings, read-only backing values and QML updates.
* [Runtime enums](../scripts/fixtures/runtime-enums.bend) and
  [native argument types](../scripts/fixtures/native-argument-types.bend) cover
  typed enum values, flags, numeric representations and containers.
* [Nondefault properties](../scripts/fixtures/nondefault-properties.bend) cover
  uninitialized values, getters, native reference reads and computed binding
  initialization without a native default constructor.
* [Explicit-copy values](../scripts/fixtures/explicit-copy-values.bend) cover
  native values whose copy constructor is explicit, including properties,
  bindings, QVariant and signals.
* [Dynamic properties](../scripts/fixtures/dynamic-properties.bend) cover native
  return values, raw native changes, metadata origins, independent returned
  copies, borrowed pointers, reentrant writes, callback failure and removal.

The standalone [binding engine test](../examples/qt612/property-bindings-native.cpp)
also checks interoperability with native `QProperty`, grouped updates, destruction
and distinct runtime pointer and enum metatypes. Pure Action proofs cover returned
results and composition. Native metadata, binding evaluation and object destruction
remain integration test responsibilities.

At this checkpoint, the source audit and strict Bend checks passed. Standalone
native binding tests passed, including native `QProperty` dependencies and
explicit-copy values. The dynamic-property adapter also passed its tracked
native control with normal execution and ASan/UBSan. That control uses real
Qt metadata and a minimal origin registry; the full generic codecs and Bend
effect transport are covered by the consumer fixture in the pending combined
run. These are narrower results than the pending fresh
generation and canonical
`python3 scripts/check-qt612.py --bundle --generator-checks --reject-system-qt`
run. Validation receipts must match the generated source before they establish
package readiness.

## QML list properties

`Property.qmlList(name, elementDescriptor)` declares a real
`QQmlListProperty` with typed QObject elements. For example:

```bend
def guests() -> Qt.Property:
  Qt.Property.qmlList("guests", Qt.ObjectType.arg(~Guest()))

def Party() -> Qt.ObjectType:
  Qt.ObjectType.withDefaultProperty(
    Qt.QObject.define("Party", [guests()]), "guests")
```

The property starts with native storage. Inside an Action block,
`ListProperty.append(~guests(), party, guest)` adds a typed element;
`count`, `at`, `replace`, `removeLast` and `clear` operate on the same list.
Indices and counts use `Int64`, matching Qt's `qsizetype`. QML can read,
append and replace elements, use array operations, and populate a declared
default list property. `QQmlListReference.listElementType` preserves the
native or Bend-authored element class.

`ListProperty.handleAppend`, `handleCount`, `handleAt`, `handleClear`,
`handleReplace` and `handleRemoveLast` install optional Bend handlers with
the usual state and typed arguments. Each corresponding `Storage` operation,
such as `appendStorage` or `countStorage`, accesses the native backing without
calling that handler again. `withAppend`, `withCount`, `withAt`, `withClear`,
`withReplace` and `withRemoveLast` control callback availability. Qt can
synthesize replacement or removal from the other available operations.

`Property.get` returns a typed `QmlListView`; it does not materialize a copied
list. `QmlListView.reference(~elementDescriptor, view)` creates an ordinary
`QQmlListReference`. `qmlList(elementDescriptor)` also supplies a descriptor
for signals, methods and QVariant boxing. `Property.writeStorage` and accessor
handlers can return a different view while keeping the declared element type.
The property itself is read-only by default, while its list contents remain
mutable. Other property attributes apply through the existing Property API.

Native storage retains current elements until removal or replacement. Views
retain their owner through copied values and queued delivery, including a
signal emitted on another thread; expired native owners are rejected before
accessing their storage. Self and native-ancestor
references stay internal to their ownership tree. Contexts use generation
checks and do not appear in `QObject.children()`. `QmlListView.with` and
`release` provide the same cleanup policy as the other value handles.

The [authored list fixture](../scripts/fixtures/qml-list-properties.bend)
checks native and Bend-authored element types, callbacks, copied views,
QVariant storage, default QML lists and scoped cleanup.
