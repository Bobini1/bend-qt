# Qt proof boundary

`LAWS.bend` states the Qt laws alongside the original arithmetic law.
`PROOF.bend` supplies their proofs, which Bend 2.0.40
checks with `--verdict`. The proof receipt records the current counts and
source hashes. The laws import `generator/templates/action.bend`,
`generator/templates/codec.bend` and `generator/templates/lifetime.bend`, which
contain the actual shared implementations used by the generated package. There
is no separate cleanup or transport model.
The current PySide coverage checkpoint requires a fresh source check and package
regeneration. The canonical source-identity gate must pass before the package
carries the verified definitions.

Proved: the returned-Result policy, resource-context propagation through bind,
and CPS composition of the shared Action
combinators, the pure Codec framing, and the Lifetime decision functions.
Not proved: native effects, handler invocation, scheduling and destruction.
Those rely on integration tests.

## What the laws establish

| Area | Proven property |
| --- | --- |
| Result precedence | A body failure preserves its complete error even if cleanup returns another failure. Cleanup failure is returned after a successful body. Successful cleanup preserves the body's value or error. Nested precedence is associative. |
| Scoped composition | Failed acquisition skips the body and release. Successful acquisition passes the same resource to the body and its cleanup action. `finally` sequences the body, cleanup and final continuation in that order. A returned body failure still passes through cleanup. Action bind stops on failure. |
| Nested cleanup | The actual continuation-passing expression sequences inner cleanup before outer cleanup, including when the inner cleanup returns `Fail`. |
| Scoped error normalization | Error code 116 becomes success. Every other U32 code and its message remain unchanged. Success remains success, and applying the normalization twice has the same result as applying it once. |
| Fatal termination | A body's `Halt` or `Exit` bypasses cleanup. A cleanup `Halt` prevents the final continuation from returning, even when the body already returned a Result. |
| Scalar transport | Encoding and decoding preserve arbitrary U32 words and Strings. Wide transport preserves both U32 fields, including every high bit. |
| Sequence and pair framing | Sequence framing preserves the complete wire list. Pair framing preserves both fields and their order. Empty, one-element and three-or-more-element sequences are rejected as pairs. |
| List conversion | Encoding and decoding arbitrary-length U32 and String lists preserves every element, its order and duplicates. Induction proves these shared recursive combinators, rather than testing a fixed sample list. |
| Failed elements | The shared list combiner returns failure if either the decoded head or tail fails. |
| Optional transport | None and Some preserve the value; scalar wire values and multi-element sequences are rejected as optional frames. |
| Reply presence | A typed DBus reply is valid exactly when its value is present. |
| Fixed arrays | The actual shared decoder enforces the declared cardinality, rejects malformed shapes and failed elements, and preserves the four-word round trip. |
| Ownership decisions | Release never deletes a Qt-owned handle. Adoption releases ownership, detachment restores it, and no parent transition preserves the prior ownership. |
| Retention decisions | Scoped release leaves Qt-owned objects, deletes unretained owned objects and defers retained owned objects. Collection deletes only when release is pending, ownership remains with Bend and no retention remains. |
| Exclusive moves | Borrowed, retained, active or read-only values cannot be moved; an exclusive owned mutable value can be moved. |
| Incubation control | Staleness takes precedence over cancellation and completion. Cancellation, no pending work or expiry stops incubation; live work continues. |
| Consuming future admission | Invalid futures report no data. Unfinished valid futures report not ready even when their first result is available. A finished valid future needs a ready first result before consumption is admitted. |
| Paired arrays | Admission requires a nonnegative count and enough storage in both arrays. |
| Aggregate-field commit | Preflight failure preserves the old value. Once a native write starts, failure disposes its uncertain result and success commits the reserved dependencies. |
| RHI cleanup access | A dead RHI reports ESTALE. Outside cleanup, access is permitted. During cleanup, only the causal cleanup handler may access its resources. |
| Sampled-image replies | A reply is admitted only when its extent matches and every texture is non-null. |
| Video mapping epochs | A value without a mapping is admitted. A mapped view is admitted only while its mapping is active and its owner is alive; otherwise access reports ESTALE. |
| Converter cleanup admission | Active state and opaque native or ICU storage reject replacement. Empty storage and an inactive binding-owned cleanup holder permit installation. |

The laws quantify over arbitrary result values, errors, resource types and,
where applicable, IO computations and continuations. They are not assertions
about a fixed set of sample values. The U32 normalization proofs explicitly
split the first differing bit from 116 so the kernel can reduce the numeric
pattern match. No axioms or unsafe definitions are added.

The IO laws are equalities between the actual continuation-passing expressions.
They establish that the helper sequences one supplied cleanup computation after
a body result and before its final continuation. They do not establish that an
arbitrary computation returns or that a foreign effect obeys this protocol.
The returned-Result guarantee applies when acquisition and body return normally;
cleanup must also return before the composed action can return its Result.

## Connection to the generated package

The three templates are standalone Bend modules with an `import Base` header.
The generator removes those headers when inlining the identical definitions
into `qt.bend`, which already imports Base.

`scripts/check-qt-action-proofs.py` checks that the generated package contains
the exact Action, Codec and Lifetime sources used by the laws. It also checks
for missing, duplicate or additional definitions. The script runs `--verdict`,
requires the output ALL PROOFS CHECK and exports the kernel translation to
`build/qt612/proofs/PROOF.bendtt` for inspection. Its receipt records source
hashes, the translation hash and the named laws.

With `--mutation-checks`, the script tries 64 disposable implementations that
still type-check. They corrupt cleanup sequencing and precedence, scalar and
container framing, optional and fixed-array validation, reply presence,
ownership, retention and move decisions, incubation, future consumption,
paired arrays, aggregate commits, RHI cleanup access, sampled-image replies,
video epochs and converter cleanup admission. The unchanged laws reject every
mutation. The receipt records each negative control. The script does not
modify the working implementation or weaken its laws.

The native integration harness runs this proof and source-identity gate before
building consumers. Importing the entire Qt module into the proof would bring
foreign effects into its dependency closure, so the shared Action, Codec and
Lifetime sources are the formal verification boundary. `templates/handlers.bend`
and the generated handler wrappers are inlined too, but no law covers them.

The maintainer generator evaluates the actual Lifetime definitions for every
Boolean input and emits the resulting native decision tables. Scoped release
has three results: leave, delete and defer. Collection requires pending release,
Bend ownership and no retention. The proof gate reevaluates the tables and
compares both coverage metadata and emitted C++ tables. Evaluation, translation
to C++ and correct native table use remain tested boundaries. Native code
observes QObject parents, retained pointers and other runtime state to supply
the policy inputs; those observations are not proved. Mapping proved policy
results to native error codes is part of the tested C++ implementation.

## What is still tested rather than proved

The proofs do not establish Qt object destruction, registry correctness, parent
ownership, inferred setter/getter relationships, observer side effects,
null-reset policies, retention graph traversal, cycle checks, capacity
reservation, getter observations or retargeting, handler invocation and
re-entry into the Bend interpreter, handler failure propagation, the handler
table, signal argument conversion, virtual dispatch, handler argument pinning,
QML registration, scene-graph rendering, shared-pointer control blocks, future
completion, exception translation, thread affinity, cross-thread delivery,
hosting Bend computations inside Qt event loops, native error numbers, dlopen
resolution or C++ ABI correctness. They also do not prove that generated
`Type.with` wrappers are emitted correctly. Those properties still rely on
native integration tests, compiler checks and the implementation of the C/C++
bridge.

The [retention](../examples/qt612/retention.bend) and
[parent and retention](../examples/qt612/retention-parent.bend) fixtures test
deferred cleanup, replacement, native ownership and strict destruction errors.
The [shutdown fixture](../examples/qt612/shutdown-retention.bend) tests
destruction ordering and pending collection after QApplication destruction. Its
native diagnostic fails if owned entries remain. These tests do not turn the
native dependency graph or Qt destructor behavior into proved properties.

The [object signal fixture](../examples/qt612/object-signals.bend) exercises
borrowed identity, nulls, generation reuse, disconnection, scope end, mixed
object/value arguments, argument cleanup and stale borrowed handles. The
[native signal probe](../scripts/check-qt612-signal-native.py) compiles the
shared runtime and drives native signal declarations through it: null and live
payloads, emission from another thread, `Signal.emit`, refused observed
signals, disconnection, QObject references, a borrowed QAuthenticator and
sender destruction. These are
runtime tests; they do not prove that an object remains alive after a handler
returns.

The Codec laws do not prove every generated per-type encoder/decoder, C heap
marshalling, Qt container conversion, integer range checks, metatype registration,
native default argument expressions or signal argument copying. In particular,
sets deduplicate, unique maps replace duplicate keys, and Qt controls map/hash
iteration order. There is no universal round-trip identity claim for those
native transformations. Generated argument cleanup uses the proven Action
combinators, but its generated traversal and native destructor calls are tested.
Native tests exercise nested containers, value copies, duplicate map keys,
conversion rollback and signal argument order.
The [binary fixture](../examples/qt612/bytes.bend) also checks all byte values,
embedded zeros, returned view copies and source mutation/destruction. Byte-list
transport uses the existing proved U32-list combinators; byte-range checks,
QByteArray storage and QByteArrayView deep copies remain native test boundaries.

In particular, the proof concerns the number 116. Its meaning as Linux ESTALE
comes from the native platform and the integration tests. The proofs establish
no cleanup guarantee for process termination, a non-returning effect, crashes
or a computation that never resumes its continuation. Code inside the cleanup
action can itself perform several operations; the helper does not prove that a
native destructor is invoked exactly once.

`--verdict` checks the translated definitions with Bend's Lean-proved kernel.
The parser, Bend-to-BendTT translation, code generator, native runtime and Base's
foreign implementations remain outside that kernel proof. See the
[Bend guide](https://github.com/bendlang/bend/blob/main/guide/GUIDE.md) and
[BendTT paper](https://github.com/bendlang/bend/blob/main/paper/BendTT.pdf).
The exported translation is an inspectable artifact, not a proof of the translator.

## Running the checks

From Ubuntu-24.04 in the workspace:

```bash
bend PROOF.bend --verdict
python3 scripts/check-qt-action-proofs.py --mutation-checks
python3 scripts/check-qt612.py --example actions --reject-system-qt
python3 scripts/check-qt612.py --example containers --example signals --example numbers
python3 scripts/check-qt612.py --example retention --example retention-parent --example shutdown-retention
python3 scripts/check-qt612.py --example object-signals --example bytes
python3 scripts/check-qt612-signal-native.py
python3 scripts/check-qt612-restoration.py
python3 scripts/check-qt-next-conversions-native.py
python3 scripts/check-qt-next-conversion-proofs.py
python3 scripts/check-qt-next-rhi-buffers.py
python3 scripts/check-qt612-state-cleanup.py
python3 scripts/check-qt-callbacks.py --only callbacks --only synchronous-signals --only callback-events
```

The `--reject-system-qt` flag tests this workspace's older system Qt. Omit it if system Qt
already meets the package's minimum version. Omitting `--example` runs all
native examples. The focused Action test records actual acquisition, body and
cleanup order through a Qt object and checks native scopes, failure paths,
error precedence, a failing handler that fails the Qt call during which it ran,
and empty registries after cleanup. These are maintainer checks; consumer
imports and build commands are unchanged.

The native conversion fault-injection fixture checks rollback after a C++
allocation exception during a partially copied container. Handler fixtures
check nested Qt calls, handler failures, waits rejected where Qt needs an
answer, mutable reference replies, and factory and retained pointer results.
These are runtime tests, not additional formal proofs.
Collection after native destruction is posted to the Qt event loop. If posting
fails, invalidation still completes and every later Qt call and the final
teardown retry collection. These native exception and event-delivery properties
are not established by the pure ownership laws.

The external Vulkan experiment and its proof and native test suites are
archived on `archive/vulkan-expansion`. They are outside the active PySide6
coverage target. Retained RHI tests cover Qt's resource, frame, readback and
cleanup contracts without claiming proofs of GPU execution or driver behavior.
Future tests check shared consumption and move-only native results.

The paired-array laws have four type-correct mutations: they test rejection of
negative counts, short first or second arrays, and erroneous rejection of valid
inputs. The checker compares the emitted C++ table with the evaluated Bend
policy. Measuring native lengths, converting UTF-8 to UTF-16, allocating storage,
and passing the correct pointers are tested in native code, not proved by these
laws.

Aggregate-field updates, RHI cleanup access, sampled-image replies and video
epochs prove admission and error precedence from supplied flags. The runtime
supplies these observations and follows the resulting tables; the proofs do
not establish their correspondence to Qt objects or events. Native tests cover
allocation rollback, copy lifetimes, handler order, texture retention, atomic
epoch revocation, plane arithmetic and registry cleanup. Icon-engine hook
payload casts and native dispatch are integration-tested; no law covers them.
