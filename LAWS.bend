import Base
import ./generator/templates/action.bend as Qt
import ./generator/templates/codec.bend as Transport
import ./generator/templates/lifetime.bend as Ownership

# Original toolchain law remains in force.
law add_zero:
  for x: Nat
  {Nat.add(x, 0n) == x : Nat}

# This is only a type abbreviation, not an alternative Action implementation.
def Outcome(-A: Type) -> Type:
  Result<&1, &1, U32 & String, A>

# Returned Result precedence preserves the whole error, including its message.
law qt_body_error_wins:
  for -A: Type
  for error: U32 & String
  for released: Outcome(Unit)
  {Qt.Action.finish(A, Fail{error}, released) == Fail{error} : Outcome(A)}

law qt_cleanup_error_after_success:
  for -A: Type
  for value: A
  for error: U32 & String
  {Qt.Action.finish(A, Done{value}, Fail{error}) == Fail{error} : Outcome(A)}

law qt_success_preserves_value:
  for -A: Type
  for value: A
  {Qt.Action.finish(A, Done{value}, Done{Unit{}}) == Done{value} : Outcome(A)}

law qt_successful_cleanup_preserves_result:
  for -A: Type
  for result: Outcome(A)
  {Qt.Action.finish(A, result, Done{Unit{}}) == result : Outcome(A)}

# Nested Result precedence selects the first failure in body/inner/outer order.
law qt_finish_associative:
  for -A: Type
  for result: Outcome(A)
  for inner: Outcome(Unit)
  for outer: Outcome(Unit)
  {Qt.Action.finish(A, Qt.Action.finish(A, result, inner), outer) == Qt.Action.finish(A, result, Qt.Action.finish(Unit, inner, outer)) : Outcome(A)}

# These equations quantify over the actual IO computations and continuations.
# They describe the program structure, not a claim that native effects return.
law qt_finally_sequences_cleanup:
  for -A: Type
  for -Out: Type
  for body: Qt.Action(A)
  for cleanup: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(A) -> IO.OP<Out>
  {Qt.Action.finally(A, body, cleanup, scope, Out, next) == body(scope, Out, result => cleanup(scope, Out, released => next(Qt.Action.finish(A, result, released)))) : IO.OP<Out>}

# Even a returned body failure must pass through cleanup before the continuation.
law qt_failure_still_cleans_up:
  for -A: Type
  for -Out: Type
  for code: U32
  for message: String
  for cleanup: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(A) -> IO.OP<Out>
  {Qt.Action.finally(A, Qt.Action.fail(A, code, message), cleanup, scope, Out, next) == cleanup(scope, Out, released => next(Fail{(code, message)})) : IO.OP<Out>}

law qt_success_still_cleans_up:
  for -A: Type
  for -Out: Type
  for value: A
  for cleanup: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(A) -> IO.OP<Out>
  {Qt.Action.finally(A, Qt.Action.pure(A, value), cleanup, scope, Out, next) == cleanup(scope, Out, released => next(Qt.Action.finish(A, Done{value}, released))) : IO.OP<Out>}

# A failed acquisition evaluates neither body nor release in the CPS program.
law qt_failed_acquisition_skips_scope:
  for -R: Data
  for -A: Type
  for code: U32
  for message: String
  for release: R -> Qt.Action(Unit)
  for body: R -> Qt.Action(A)
  {Qt.Action.using(R, A, Qt.Action.fail(R, code, message), release, body) == Qt.Action.fail(A, code, message) : Qt.Action(A)}

# The same acquired resource is passed to the body and its one release action.
law qt_acquired_resource_is_scoped:
  for -R: Data
  for -A: Type
  for resource: R
  for release: R -> Qt.Action(Unit)
  for body: R -> Qt.Action(A)
  {Qt.Action.using(R, A, Qt.Action.pure(R, resource), release, body) == Qt.Action.finally(A, body(resource), release(resource)) : Qt.Action(A)}

law qt_bind_short_circuits_failure:
  for -A: Type
  for -B: Type
  for code: U32
  for message: String
  for next: A -> Qt.Action(B)
  {Qt.Action.bind(A, B, Qt.Action.fail(A, code, message), next) == Qt.Action.fail(B, code, message) : Qt.Action(B)}

law qt_nested_cleanup_order:
  for -A: Type
  for -Out: Type
  for body: Qt.Action(A)
  for inner: Qt.Action(Unit)
  for outer: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(A) -> IO.OP<Out>
  {Qt.Action.finally(A, Qt.Action.finally(A, body, inner), outer, scope, Out, next) == body(scope, Out, result => inner(scope, Out, inner_result => outer(scope, Out, outer_result => next(Qt.Action.finish(A, Qt.Action.finish(A, result, inner_result), outer_result))))) : IO.OP<Out>}

law qt_cleanup_accepts_stale:
  for message: String
  {Qt.Action.cleanup_result(Fail{(116, message)}) == Done{Unit{}} : Outcome(Unit)}

law qt_cleanup_preserves_success:
  {Qt.Action.cleanup_result(Done{Unit{}}) == Done{Unit{}} : Outcome(Unit)}

law qt_cleanup_preserves_other_errors:
  for code: U32
  for message: String
  for different: {code != 116 : U32}
  {Qt.Action.cleanup_result(Fail{(code, message)}) == Fail{(code, message)} : Outcome(Unit)}

law qt_cleanup_normalization_idempotent:
  for result: Outcome(Unit)
  {Qt.Action.cleanup_result(Qt.Action.cleanup_result(result)) == Qt.Action.cleanup_result(result) : Outcome(Unit)}

law qt_cleanup_applies_policy:
  for -Out: Type
  for cleanup: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(Unit) -> IO.OP<Out>
  {Qt.Action.cleanup(cleanup, scope, Out, next) == cleanup(scope, Out, result => next(Qt.Action.cleanup_result(result))) : IO.OP<Out>}

# Fatal termination is deliberately not stated to unwind a scope.
law qt_body_halt_bypasses_cleanup:
  for -A: Type
  for -Out: Type
  for code: U32
  for message: String
  for cleanup: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(A) -> IO.OP<Out>
  {Qt.Action.finally(A, Qt.Action.fromIO(A, IO.die(Outcome(A), code, message)), cleanup, scope, Out, next) == Halt{code, message} : IO.OP<Out>}

law qt_body_exit_bypasses_cleanup:
  for -Out: Type
  for code: U32
  for cleanup: Qt.Action(Unit)
  for scope: U32
  for next: Outcome(Unit) -> IO.OP<Out>
  {Qt.Action.finally(Unit, Qt.Action.lift(Unit, IO.exit(code)), cleanup, scope, Out, next) == Exit{code} : IO.OP<Out>}

law qt_cleanup_halt_prevents_return:
  for -A: Type
  for -Out: Type
  for result: Outcome(A)
  for code: U32
  for message: String
  for scope: U32
  for next: Outcome(A) -> IO.OP<Out>
  {Qt.Action.finally(A, Qt.Action.result(A, result), Qt.Action.fromIO(Unit, IO.die(Outcome(Unit), code, message)), scope, Out, next) == Halt{code, message} : IO.OP<Out>}

# Pure container and signal transport contracts.
# Signal declarations use Qt.int32() and the other native argument descriptors.
# A generated Qt.QPushButton.arg() descriptor preserves QPushButton in both
# the Bend handler/emitter types and the native QPushButton* signal signature.
# QObject arguments are borrowed, retain their identity, and must belong to
# the main thread. Queued delivery rejects arguments deleted before delivery,
# including QObject references nested in QVariantMap/List values. Callback
# frames own native value copies until the handler returns or first waits.
# Custom copyable Bend data uses Qt.arg(~Payload), with Payload required by
# both emission and the connected handler. Qt transports it opaquely; QML
# field exposure requires an explicit codec or Qt properties. Native retention,
# type-witness checks, queued delivery and destruction require integration
# tests; the pure laws below do not prove those runtime contracts.
law qt_wire_word_roundtrip:
  for word: U32
  {Transport.Codec.read_word(Transport.Codec.word(word)) == Some{word} : Maybe<&2, U32>}

law qt_wire_text_roundtrip:
  for text: String
  {Transport.Codec.read_text(Transport.Codec.text(text)) == Some{text} : Maybe<&2, String>}

law qt_wire_sequence_roundtrip:
  for items: List<&2, Transport.Wire>
  {Transport.Codec.read_sequence(Transport.Codec.sequence(items)) == Some{items} : Maybe<&2, List<&2, Transport.Wire>>}

law qt_wire_pair_preserves_order:
  for first: Transport.Wire
  for second: Transport.Wire
  {Transport.Codec.read_pair(Transport.Codec.pair(first, second)) == Some{Transport.PairValue{first, second}} : Maybe<&2, Transport.PairValue<Transport.Wire, Transport.Wire>>}

law qt_wire_pair_rejects_empty:
  {Transport.Codec.read_pair(Transport.Codec.sequence(Nil{})) == None{} : Maybe<&2, Transport.PairValue<Transport.Wire, Transport.Wire>>}

law qt_wire_pair_rejects_short:
  for item: Transport.Wire
  {Transport.Codec.read_pair(Transport.Codec.sequence(item <> Nil{})) == None{} : Maybe<&2, Transport.PairValue<Transport.Wire, Transport.Wire>>}

law qt_wire_pair_rejects_long:
  for a: Transport.Wire
  for b: Transport.Wire
  for c: Transport.Wire
  for tail: List<&2, Transport.Wire>
  {Transport.Codec.read_pair(Transport.Codec.sequence(a <> b <> c <> tail)) == None{} : Maybe<&2, Transport.PairValue<Transport.Wire, Transport.Wire>>}

law qt_codec_failed_head:
  for -A: Data
  for tail: Maybe<&2, List<&2, A>>
  {Transport.Codec.cons(A, None{}, tail) == None{} : Maybe<&2, List<&2, A>>}

law qt_codec_failed_tail:
  for -A: Data
  for head: Maybe<&2, A>
  {Transport.Codec.cons(A, head, None{}) == None{} : Maybe<&2, List<&2, A>>}

law qt_codec_word_items_roundtrip:
  for items: List<&2, U32>
  {Transport.Codec.decode_items(~U32, ~Transport.Codec.read_word, Transport.Codec.encode_items(~U32, ~Transport.Codec.word, items)) == Some{items} : Maybe<&2, List<&2, U32>>}

law qt_codec_word_list_roundtrip:
  for items: List<&2, U32>
  {Transport.Codec.decode_list(~U32, ~Transport.Codec.read_word, Transport.Codec.encode_list(~U32, ~Transport.Codec.word, items)) == Some{items} : Maybe<&2, List<&2, U32>>}

law qt_codec_text_items_roundtrip:
  for items: List<&2, String>
  {Transport.Codec.decode_items(~String, ~Transport.Codec.read_text, Transport.Codec.encode_items(~String, ~Transport.Codec.text, items)) == Some{items} : Maybe<&2, List<&2, String>>}

law qt_codec_text_list_roundtrip:
  for items: List<&2, String>
  {Transport.Codec.decode_list(~String, ~Transport.Codec.read_text, Transport.Codec.encode_list(~String, ~Transport.Codec.text, items)) == Some{items} : Maybe<&2, List<&2, String>>}

law qt_wire_wide_preserves_all_bits:
  for lo: U32
  for hi: U32
  {Transport.Codec.read_wide(Transport.Codec.wide(lo, hi)) == Some{Transport.PairValue{lo, hi}} : Maybe<&2, Transport.PairValue<U32, U32>>}

# Pure decisions used to generate the native ownership tables. Native pointer
# observation, ownership metadata and object destruction require native tests.
law qt_lifetime_owned_scope_deletes:
  {Ownership.Lifetime.release(True{}) == 1 : U32}

law qt_lifetime_transferred_scope_keeps:
  {Ownership.Lifetime.release(False{}) == 0 : U32}

law qt_lifetime_parent_acquires_ownership:
  for owned: Bool
  for had_parent: Bool
  {Ownership.Lifetime.reparent(owned, had_parent, True{}) == False{} : Bool}

law qt_lifetime_detach_restores_ownership:
  for owned: Bool
  {Ownership.Lifetime.reparent(owned, True{}, False{}) == True{} : Bool}

law qt_lifetime_no_parent_preserves_ownership:
  for owned: Bool
  {Ownership.Lifetime.reparent(owned, False{}, False{}) == owned : Bool}

law qt_lifetime_scope_after_parent_keeps:
  for owned: Bool
  for had_parent: Bool
  {Ownership.Lifetime.release(Ownership.Lifetime.reparent(owned, had_parent, True{})) == 0 : U32}

law qt_lifetime_scope_after_detach_deletes:
  for owned: Bool
  {Ownership.Lifetime.release(Ownership.Lifetime.reparent(owned, True{}, False{})) == 1 : U32}

law qt_lifetime_parent_then_detach_restores:
  for owned: Bool
  for had_parent: Bool
  {Ownership.Lifetime.reparent(Ownership.Lifetime.reparent(owned, had_parent, True{}), True{}, False{}) == True{} : Bool}

# Retention decisions use actual observed native dependency facts as inputs.
# Graph traversal, destruction order and dependency observation are not proved.
law qt_lifetime_scoped_transferred_keeps:
  for retained: Bool
  {Ownership.Lifetime.scoped(False{}, retained) == 0 : U32}

law qt_lifetime_scoped_owned_unretained_deletes:
  {Ownership.Lifetime.scoped(True{}, False{}) == 1 : U32}

law qt_lifetime_scoped_owned_retained_defers:
  {Ownership.Lifetime.scoped(True{}, True{}) == 2 : U32}

law qt_lifetime_unreleased_never_collects:
  for owned: Bool
  for retained: Bool
  {Ownership.Lifetime.collect(False{}, owned, retained) == False{} : Bool}

law qt_lifetime_transferred_never_collects:
  for pending: Bool
  for retained: Bool
  {Ownership.Lifetime.collect(pending, False{}, retained) == False{} : Bool}

law qt_lifetime_retained_never_collects:
  for pending: Bool
  for owned: Bool
  {Ownership.Lifetime.collect(pending, owned, True{}) == False{} : Bool}

law qt_lifetime_removed_dependency_collects:
  {Ownership.Lifetime.collect(True{}, True{}, False{}) == True{} : Bool}

# Absence is a valid optional value; malformed payloads are separate failures.
law qt_optional_word_roundtrip:
  for value: Maybe<&2, U32>
  {Transport.Codec.decode_optional(~U32, ~Transport.Codec.read_word, Transport.Codec.encode_optional(~U32, ~Transport.Codec.word, value)) == Some{value} : Maybe<&2, Maybe<&2, U32>>}

law qt_optional_text_roundtrip:
  for value: Maybe<&2, String>
  {Transport.Codec.decode_optional(~String, ~Transport.Codec.read_text, Transport.Codec.encode_optional(~String, ~Transport.Codec.text, value)) == Some{value} : Maybe<&2, Maybe<&2, String>>}

law qt_optional_rejects_multiple_elements:
  for first: Transport.Wire
  for second: Transport.Wire
  for tail: List<&2, Transport.Wire>
  {Transport.Codec.decode_optional(~U32, ~Transport.Codec.read_word, Transport.WireSequence{first <> second <> tail}) == None{} : Maybe<&2, Maybe<&2, U32>>}

law qt_optional_rejects_scalar_shape:
  for lo: U32
  for hi: U32
  {Transport.Codec.decode_optional(~U32, ~Transport.Codec.read_word, Transport.WireScalar{lo, hi}) == None{} : Maybe<&2, Maybe<&2, U32>>}

law qt_optional_rejects_invalid_element:
  for text: String
  {Transport.Codec.decode_optional(~U32, ~Transport.Codec.read_word, Transport.WireSequence{Transport.WireText{text} <> Nil{}}) == None{} : Maybe<&2, Maybe<&2, U32>>}

law qt_optional_nested_absence_is_present:
  {Transport.Codec.decode_optional(~Maybe<&2, U32>, ~(wire => Transport.Codec.decode_optional(~U32, ~Transport.Codec.read_word, wire)), Transport.Codec.encode_optional(~Maybe<&2, U32>, ~(value => Transport.Codec.encode_optional(~U32, ~Transport.Codec.word, value)), Some{None{}})) == Some{Some{None{}}} : Maybe<&2, Maybe<&2, Maybe<&2, U32>>>}

# These laws constrain the consuming-move decision, not native move constructors
# or the registry observations supplied to this decision.
law qt_lifetime_move_borrowed_rejects:
  for retained: Bool
  for active: Bool
  for readonly: Bool
  {Ownership.Lifetime.move(False{}, retained, active, readonly) == False{} : Bool}

law qt_lifetime_move_retained_rejects:
  for owned: Bool
  for active: Bool
  for readonly: Bool
  {Ownership.Lifetime.move(owned, True{}, active, readonly) == False{} : Bool}

law qt_lifetime_move_active_rejects:
  for owned: Bool
  for retained: Bool
  for readonly: Bool
  {Ownership.Lifetime.move(owned, retained, True{}, readonly) == False{} : Bool}

law qt_lifetime_move_readonly_rejects:
  for owned: Bool
  for retained: Bool
  for active: Bool
  {Ownership.Lifetime.move(owned, retained, active, True{}) == False{} : Bool}

law qt_lifetime_move_exclusive_allows:
  {Ownership.Lifetime.move(True{}, False{}, False{}, False{}) == True{} : Bool}

# Typed DBus replies use presence to distinguish success from a remote error.
# Native DBus transport and the native error-to-wire conversion are not proved.
law qt_reply_present_is_valid:
  for value: U32
  {Transport.Codec.optional_valid(~U32, Some{value}) == True{} : Bool}

law qt_reply_absent_is_invalid:
  {Transport.Codec.optional_valid(~U32, None{}) == False{} : Bool}

law qt_incubation_stale_precedes_stop:
  for flag: Bool
  for pending: Bool
  for expired: Bool
  {Ownership.Lifetime.incubation(False{}, flag, pending, expired) == 2 : U32}

law qt_incubation_cancel_stops:
  for pending: Bool
  for expired: Bool
  {Ownership.Lifetime.incubation(True{}, False{}, pending, expired) == 1 : U32}

law qt_incubation_empty_stops:
  for expired: Bool
  {Ownership.Lifetime.incubation(True{}, True{}, False{}, expired) == 1 : U32}

law qt_incubation_deadline_stops:
  {Ownership.Lifetime.incubation(True{}, True{}, True{}, True{}) == 1 : U32}

law qt_incubation_live_work_continues:
  {Ownership.Lifetime.incubation(True{}, True{}, True{}, False{}) == 0 : U32}

# Fixed-array wire cardinality and decoding use the actual shared codec source.
law qt_array_zero_accepts_empty:
  {Transport.Codec.decode_array(~U32, ~Transport.Codec.read_word, 0, Transport.WireSequence{Nil{}}) == Some{Nil{}} : Maybe<&2, List<&2, U32>>}

law qt_array_zero_rejects_elements:
  for head: Transport.Wire
  for tail: List<&2, Transport.Wire>
  {Transport.Codec.array_count(0, head <> tail) == False{} : Bool}

law qt_array_four_word_roundtrip:
  for a: U32
  for b: U32
  for c: U32
  for d: U32
  {Transport.Codec.decode_array(~U32, ~Transport.Codec.read_word, 4, Transport.Codec.encode_list(~U32, ~Transport.Codec.word, a <> b <> c <> d <> Nil{})) == Some{a <> b <> c <> d <> Nil{}} : Maybe<&2, List<&2, U32>>}

law qt_array_rejects_short_input:
  for a: Transport.Wire
  for b: Transport.Wire
  for c: Transport.Wire
  {Transport.Codec.decode_array(~U32, ~Transport.Codec.read_word, 4, Transport.WireSequence{a <> b <> c <> Nil{}}) == None{} : Maybe<&2, List<&2, U32>>}

law qt_array_rejects_excess_input:
  for a: Transport.Wire
  for b: Transport.Wire
  for c: Transport.Wire
  for d: Transport.Wire
  for e: Transport.Wire
  for tail: List<&2, Transport.Wire>
  {Transport.Codec.decode_array(~U32, ~Transport.Codec.read_word, 4, Transport.WireSequence{a <> b <> c <> d <> e <> tail}) == None{} : Maybe<&2, List<&2, U32>>}

law qt_array_rejects_scalar_shape:
  for count: U32
  for lo: U32
  for hi: U32
  {Transport.Codec.decode_array(~U32, ~Transport.Codec.read_word, count, Transport.WireScalar{lo, hi}) == None{} : Maybe<&2, List<&2, U32>>}

law qt_array_rejects_invalid_element:
  for text: String
  {Transport.Codec.decode_array(~U32, ~Transport.Codec.read_word, 1, Transport.WireSequence{Transport.WireText{text} <> Nil{}}) == None{} : Maybe<&2, List<&2, U32>>}

law qt_lifetime_future_take_invalid:
  for finished: Bool
  for ready: Bool
  {Ownership.Lifetime.future_take(False{}, finished, ready) == 61 : U32}

law qt_lifetime_future_take_unfinished:
  for ready: Bool
  {Ownership.Lifetime.future_take(True{}, False{}, ready) == 11 : U32}

law qt_lifetime_future_take_empty:
  {Ownership.Lifetime.future_take(True{}, True{}, False{}) == 61 : U32}

law qt_lifetime_future_take_ready:
  {Ownership.Lifetime.future_take(True{}, True{}, True{}) == 0 : U32}

law qt_paired_array_negative:
  for first_fits: Bool
  for second_fits: Bool
  {Ownership.Lifetime.paired_array(False{}, first_fits, second_fits) == False{} : Bool}

law qt_paired_array_first_short:
  for second_fits: Bool
  {Ownership.Lifetime.paired_array(True{}, False{}, second_fits) == False{} : Bool}

law qt_paired_array_second_short:
  {Ownership.Lifetime.paired_array(True{}, True{}, False{}) == False{} : Bool}

law qt_paired_array_valid:
  {Ownership.Lifetime.paired_array(True{}, True{}, True{}) == True{} : Bool}


law qt_lifetime_aggregate_preflight_preserves:
  for succeeded: Bool
  {Ownership.Lifetime.aggregate_commit(False{}, succeeded) == 0 : U32}

law qt_lifetime_aggregate_native_failure_invalidates:
  {Ownership.Lifetime.aggregate_commit(True{}, False{}) == 1 : U32}

law qt_lifetime_aggregate_native_success_commits:
  {Ownership.Lifetime.aggregate_commit(True{}, True{}) == 2 : U32}

law qt_lifetime_cleanup_dead:
  for cleaning: Bool
  for causal: Bool
  {Ownership.Lifetime.cleanup_access(False{}, cleaning, causal) == 116 : U32}

law qt_lifetime_cleanup_ordinary:
  for causal: Bool
  {Ownership.Lifetime.cleanup_access(True{}, False{}, causal) == 0 : U32}

law qt_lifetime_cleanup_unrelated:
  {Ownership.Lifetime.cleanup_access(True{}, True{}, False{}) == 16 : U32}

law qt_lifetime_cleanup_causal:
  {Ownership.Lifetime.cleanup_access(True{}, True{}, True{}) == 0 : U32}

law qt_lifetime_sampled_extent:
  for nonnull: Bool
  {Ownership.Lifetime.sampled_reply(False{}, nonnull) == 22 : U32}

law qt_lifetime_sampled_null:
  {Ownership.Lifetime.sampled_reply(True{}, False{}) == 22 : U32}

law qt_lifetime_sampled_valid:
  {Ownership.Lifetime.sampled_reply(True{}, True{}) == 0 : U32}

law qt_lifetime_video_local:
  for active: Bool
  for owner_alive: Bool
  {Ownership.Lifetime.video_epoch(False{}, active, owner_alive) == 0 : U32}

law qt_lifetime_video_unmapped:
  for owner_alive: Bool
  {Ownership.Lifetime.video_epoch(True{}, False{}, owner_alive) == 116 : U32}

law qt_lifetime_video_destroyed:
  {Ownership.Lifetime.video_epoch(True{}, True{}, False{}) == 116 : U32}

law qt_lifetime_video_mapped:
  {Ownership.Lifetime.video_epoch(True{}, True{}, True{}) == 0 : U32}

law qt_lifetime_cleanup_install_active:
  for empty: Bool
  for ours: Bool
  for icu: Bool
  {Ownership.Lifetime.cleanup_install(empty, ours, icu, True{}) == 16 : U32}

law qt_lifetime_cleanup_install_icu:
  for empty: Bool
  for ours: Bool
  {Ownership.Lifetime.cleanup_install(empty, ours, True{}, False{}) == 95 : U32}

law qt_lifetime_cleanup_install_foreign:
  {Ownership.Lifetime.cleanup_install(False{}, False{}, False{}, False{}) == 95 : U32}

law qt_lifetime_cleanup_install_own:
  for empty: Bool
  {Ownership.Lifetime.cleanup_install(empty, True{}, False{}, False{}) == 0 : U32}

law qt_lifetime_cleanup_install_empty:
  {Ownership.Lifetime.cleanup_install(True{}, False{}, False{}, False{}) == 0 : U32}


# The resource scope is passed to every continuation, including after IO waits.
law qt_action_bind_passes_scope:
  for -A: Type
  for -B: Type
  for -Out: Type
  for action: Qt.Action(A)
  for next: A -> Qt.Action(B)
  for scope: U32
  for finish: Outcome(B) -> IO.OP<Out>
  {Qt.Action.bind(A, B, action, next, scope, Out, finish) == action(scope, Out, result => Qt.Action.next(A, B, result, next, scope, Out, finish)) : IO.OP<Out>}
