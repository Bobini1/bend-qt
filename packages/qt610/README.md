# Qt 6.10.3 bindings for native Bend

This distribution targets exactly Qt 6.10.3, Bend 2.0.40 and Linux x86-64.
Its release version is `qt@6.10.3.1`. It bundles matching Qt libraries,
plugins and QML assets. System libraries and platform/graphics drivers remain
required. This workspace has not published a public Hub release.

Consumers use an ordinary Hub import and native Bend compilation:

```bash
bend main.bend -o app
./app
```

No Qt SDK, generator, companion binding library or separate C++ build is
required. Bare `bend main.bend` selects Bend's JavaScript backend, which this
package does not implement. Use the published Hub name or content hash after
publication. For a local copy, this complete program goes beside `qt.bend`:

```python
import Base
import ./qt.bend as Qt

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QObject.with(Unit, Qt.QObject.new(), object => Qt.QObject.setObjectName(object, "Bend"))))
```

Public Qt calls return `Action(A)`. Compose them with Action blocks and handle
failure at the outer IO boundary. `Type.with` and `Qt.scoped` clean up on both
success and failure. Qt and Bend share the process main thread; the first Qt
effect creates the package-owned QApplication. Qt event loops run through
ordinary calls such as `QCoreApplication.exec()`. Call `Render.useGuiThread()`
before a Quick window when using Bend rendering callbacks.

The package contains separately retained native groups. Core-only consumers
omit optional GPL groups. The shared LGPL group currently contains 50
modules, so its footprint is larger than a minimal Qt Core installation.
Referencing an optional native type or API retains its group and dependencies.
QML-only dependencies use actions such as `Modules.Graphs.load()`. Graphs,
Charts and DataVisualization can be used together; the legacy families have
the public prefixes `Charts` and `DataVisualization`.

The bundled runtime is extracted into a private content-addressed cache and
checked by SHA-256. Library, plugin, QML and WebEngine paths use that runtime.
System Qt updates do not replace it. `BEND_QT_RUNTIME` selects an explicit
complete replacement with the matching native ABI; there is no automatic
system-Qt fallback. RHI and private helper APIs require this exact Qt build.

The API inventory comes from the matching pinned PySide type systems and
unmodified Shiboken ApiExtractor. APIs absent from this Qt release are absent
from this package. The maintainer release artifacts include `coverage.json`
with generated APIs and unsupported contracts. Native effects, scheduling and
destruction rely on integration tests. The Action proofs separately cover
returned-Result policy and CPS composition.

The original generator and Bend glue use MIT. Qt and third-party components
retain their own terms. See `LICENSE` and the bundled component notices and
corresponding-source information. Availability of a GPL module does not cause
its native code or assets to be retained by a Core-only consumer.
