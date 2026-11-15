# Qt application feature tests

These fixtures exercise Qt features through native Bend consumers. An inventory
of generated names alone does not establish runtime support. The table records
focused evidence; the full release validation remains a separate gate.

| Application feature | Bend support and evidence | Current verification |
| --- | --- | --- |
| QObject data holders, properties, notifications and QML registration | `QtObject`, `Property`, authored signals, methods and QML registration; property, singleton, value-type and registration fixtures | Implemented; complete release suite pending |
| Native and authored typed signals, including objects and QVariant containers | Direct and queued connection adapters; mixed-family native fixture | Focused native consumers passed |
| Mutable item models and value ownership | `QRangeModel.fromValues` and `fromRows`, overrides and model scopes | Native Bend/Qt 6.10 consumer passed edits, QML calls, retained objects, stale metadata and cleanup |
| Qt Quick scene-graph nodes | `QQuickItem.updatePaintNode`, geometry, material and node ownership adapters | Custom material rendering below passed; the complete scene-graph suite remains a separate gate |
| Custom material shader creation | Bend `QSGMaterial.createShader` handler returns a Bend override shader configured from QSB files | Actual OpenGL frames passed |
| Matrix, opacity and custom uniform buffers | Checked `MemoryView` writes, matrix float views and `QDataStream` float serialization | Rendered pixels passed using 80, 96, 112 and 116 byte uniform offsets |
| Custom graphics pipeline state | Mutable pipeline-state callback reply and generated blend-factor fields | Additive blending passed pixel checks on two frames |
| Per-material Bend data with a shared shader | QObject-backed QVariant data and stable native material handles | Two materials shared one shader on the first frame and rendered distinct red/green pixels; a second frame and zero live handles/data also passed |
| Sampled textures and renderer resources | Typed sampled-image arrays, reflection-based extents, texture retention and renderer resource views | Dedicated fixtures exist; included in the final suite |
| Asynchronous QML image providers | Bend-authored `QQuickAsyncImageProvider` and `QQuickImageResponse` | Real QML loading, early completion, pixels, cancellation, response deletion and zero live handles/data passed |
| Native image-format plugins | `QCoreApplication.addLibraryPath` and `QImageReader` use a matching prebuilt plugin | Fresh Bend consumer discovered a custom format and decoded its pixels |
| QML module imports | Complete release consumer imports all 14 modules in `QML_MODULES` | Fresh full Qt 6.12 Hub consumer passed with the bundled runtime and a matching replacement runtime |

The material fixtures author their materials, geometry, shaders and uniform
writes in Bend. Their shaders use an explicit uniform layout and test
additive blend state. The second fixture reads each draw's own typed Bend
payload through its `newMaterial` argument, including when Qt reuses a shader.
The fixtures cover the documented cases rather than every possible shader or material combination.
Texture sampling has its own ownership and reflection fixture.

The asynchronous image-provider fixture uses a prepared image. Qt's worker
requests are dispatched to Bend handlers on the Qt main thread. It verifies
the provider protocol and ownership, without demonstrating background
archive reading or image-decoding workload in Bend.

`QImageIOPlugin` authoring is outside the pinned PySide binding scope. A native
plugin can still be built by its maintainer and loaded by a Bend application,
as Qt's existing plugin mechanism allows. The image-plugin test checks that
route. It does not claim that third-party image decoder implementations
have been ported to Bend or tested unchanged.

The focused native receipts are under `build/scenegraph-material-render`, `build/scenegraph-material-instances`,
`build/async-image-provider`, `build/native-image-plugin` and
`build/range-model-bend-610`. They do not replace fresh full-package consumers
and `python3 scripts/check-qt612.py --bundle --generator-checks --reject-system-qt`.

The Action proofs cover returned-Result policy and CPS composition. Native
effects, callback scheduling, rendering, plugin loading and destruction rely
on integration tests.
