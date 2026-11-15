# Protected Qt API

The generated API includes protected members exposed by PySide's binding scope.
They use the same class namespaces, conversions, ownership rules and `Action`
results as public methods. The extractor's access flags remain in the coverage
inventory so unsupported protected signatures remain visible.

For example, a Bend list model can bracket a storage change with Qt's native
model notifications:

```python
Qt.QAbstractListModel.beginInsertRows(model, parent, Qt.Int32{0}, Qt.Int32{0})
# Update the storage used by the model's rowCount and data handlers here.
Qt.QAbstractListModel.endInsertRows(model)
```

The [native fixture](../scripts/fixtures/protected-members.bend) supplies the
virtual handlers, changes the row count and checks the resulting Qt signals.
It also exercises the reset hooks.

Protected constructors use ordinary generated overload names. For example,
`QStyleOptionButton.new__Int32(Int32{7})` selects its version constructor, and
`QCloseEvent.new__QCloseEvent(original)` creates an independent event copy.
Constructor visibility does not change whether Qt declares a class abstract.
An abstract native class still uses its generated `newOverride` constructor and
typed virtual handlers.

Protected native enums use their ordinary Bend namespace and descriptor:

```python
Qt.Property.define("viewState", Qt.QAbstractItemView.State.arg())
```

The native property retains `QAbstractItemView::State` as its metatype. Access
helpers used by the C++ compiler do not appear in metadata or the Bend API.

The C++ access bridge obtains a member pointer inside a derived access class,
then applies that pointer to the actual base object. Native and Qt-created
objects retain their real types. A protected constructor creates a genuine
derived allocation; its registry entry records the matching derived deleter,
including classes whose destructors are nonvirtual.

A private virtual override can still implement a callable public base contract.
Ordinary calls use that base contract and native virtual dispatch. Proxy
generation separately retains the actual override's access and final status.

Published overload names stay pinned. When a newly supported parameterless
overload finds its plain name already assigned to another published overload,
it receives the `__NoArgs` suffix. Existing names retain their signatures.

These native access and destruction rules are covered by integration tests.
The pure Action proofs cover returned results and composition.

Native engine getters return checked borrowed handles. For example,
`QImage.paintEngine`, `QPainter.paintEngine` and `QPrinter.printEngine` work
with engines that Qt creates internally. Their views expire when the owner
replaces that storage or is destroyed. Image detachment and printer engine
resets expire the old generation before native allocation can reuse its address.
An existing Bend-owned engine keeps its identity and ownership when a getter
returns it. `QPrinter.setEngines` retains both external engines until the
printer replaces or releases them.

The same observation rules cover painting devices, shared painters, printer
dialog printers and protected pointer-member views. A QWidget returned through
its QPaintDevice base still uses Qt's QObject destruction notification.

`QAbstractProxyModel.createSourceIndex` takes a checked `ModelData` identity
obtained from a source model index. It verifies that the identity belongs to
the proxy's current source model before forwarding the native pointer. A data
identity from another model is rejected before Qt receives it.
