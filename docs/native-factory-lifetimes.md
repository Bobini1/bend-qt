# Native factories and lifetime

Factory calls follow Qt's ownership contract. A caller-owned result initially
belongs to its Bend resource scope. A borrowed result follows its native owner.
The generated coverage report records the adapter used for each family.

On the Qt/Bend thread, synchronous `destroyed` handlers finish before the
destroy call returns. Dependencies remain alive until native destructors and
their child teardown finish. Nested calls can clean up their own completed
objects while an outer destructor is still running.

For example, `QQuickWindow.createRectangleNode(window)` returns an owned
`QSGRectangleNode`. Inside an `updatePaintNode` handler, configure the node and
return its `QSGNode` base:

```python
do Qt.Action<Qt.QSGNode>:
  +node: Qt.QSGRectangleNode <- Qt.QQuickWindow.createRectangleNode(window)
  Qt.QSGRectangleNode.setRect__QRectF(node, rect)
  Qt.QSGRectangleNode.setColor(node, color)
  return Qt.QSGRectangleNode.as_QSGNode(node)
```

Qt adopts a successful handler result. The original factory handle then
expires. A later handler receives a fresh view of `oldNode`, valid for that
render callback. Existing Bend child objects retain their identities and
handlers. Each native allocation keeps its own dependency slots until native
deletion finishes. Detaching or reparenting a subtree moves those dependencies
with the subtree. A failed handler keeps normal Bend scope cleanup.

Use `Render.useGuiThread()` for this workflow. Qt Quick chooses its rendering
backend internally. Rendering resources still require their documented native
context and lifetime.

Canvas shared factories follow their `QRhi`. A manually created Canvas factory
retains its `QRhi` until `destroy()`. `painter()` and `paintDriver()` views expire
when the factory destroys or replaces them. Renderer framebuffer and Canvas
painter views belong to the current render callback.

`QQuickFramebufferObject.Renderer` has a protected destructor. A direct
`createRenderer()` call can reclaim an existing Bend override with its exact
generated deleter. An unknown private Qt renderer remains Qt-owned.

`QtCoreHelper.QIOPipe` provides the pinned PySide duplex pipe helper as native
Qt objects. Construct a pipe, open it with `Flags_QIODeviceBase__OpenModeFlag`,
and use `end1()` and `end2()` as ordinary `QIODevice` handles. Native
`readyRead` and `bytesWritten` signals run normal Bend handlers. The pipe owns
both parentless endpoints; keep the pipe alive while using them. Endpoint
handles become stale when the pipe is destroyed.

The focused controls in `scripts/check-qt-render-factories.py` and
`scripts/check-qt-io-pipe.py` compile the production implementations. The
`render-factory-results` and `io-pipe` fixtures exercise the complete Bend
consumer transport in the canonical native gate. A focused control pass alone
does not establish that the generated package passes that gate.
