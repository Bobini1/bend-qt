import Base

# Evaluated by the maintainer generator for the native decision tables.
# This policy does not prove that native parent observations are correct.
def Lifetime.release(owned: Bool) -> U32:
  match owned:
    case False{}: 0
    case True{}: 1

# Called only when the native QObject parent identity has changed.
def Lifetime.reparent(owned: Bool, had_parent: Bool, has_parent: Bool) -> Bool:
  match owned had_parent has_parent:
    case _ _ True{}: False{}
    case _ True{} False{}: True{}
    case previous False{} False{}: previous

# 0 leaves native ownership alone, 1 deletes, and 2 defers scoped deletion.
def Lifetime.scoped(owned: Bool, retained: Bool) -> U32:
  match owned retained:
    case False{} _: 0
    case True{} False{}: 1
    case True{} True{}: 2

# A disappearing dependency can collect only a previously released resource.
def Lifetime.collect(pending: Bool, owned: Bool, retained: Bool) -> Bool:
  match pending owned retained:
    case True{} True{} False{}: True{}
    case _ _ _: False{}

# Native code supplies these ownership, retention, activity and constness facts.
def Lifetime.move(owned: Bool, retained: Bool, active: Bool, readonly: Bool) -> Bool:
  match owned retained active readonly:
    case True{} False{} False{} False{}: True{}
    case _ _ _ _: False{}

# Incubation: 0 runs another bounded native slice, 1 stops, 2 reports stale.
# Native code supplies association liveness and actual timer state.
def Lifetime.incubation(alive: Bool, flag: Bool, pending: Bool, expired: Bool) -> U32:
  match alive flag pending expired:
    case False{} _ _ _: 2
    case True{} False{} _ _: 1
    case True{} True{} False{} _: 1
    case True{} True{} True{} True{}: 1
    case True{} True{} True{} False{}: 0

# Native takeResult may wait for all results, so even a ready first result is
# insufficient until the future finishes. Native stored failures are rethrown
# before observing ready; these numbers govern only ordinary admission.
def Lifetime.future_take(valid: Bool, finished: Bool, ready: Bool) -> U32:
  match valid finished ready:
    case False{} _ _: 61
    case True{} False{} _: 11
    case True{} True{} False{}: 61
    case True{} True{} True{}: 0

# Native code measures counts and capacities without multiplying extents.
def Lifetime.paired_array(nonnegative: Bool, first_fits: Bool, second_fits: Bool) -> Bool:
  match nonnegative first_fits second_fits:
    case True{} True{} True{}: True{}
    case _ _ _: False{}
# Aggregate updates: preflight failure preserves the old value (0). Once a
# native write starts, failure disposes its uncertain result (1), success
# commits the reserved dependency set (2).
def Lifetime.aggregate_commit(prepared: Bool, native_succeeded: Bool) -> U32:
  match prepared native_succeeded:
    case False{} _: 0
    case True{} False{}: 1
    case True{} True{}: 2

def Lifetime.cleanup_access(alive: Bool, cleaning: Bool, causal: Bool) -> U32:
  match alive cleaning causal:
    case False{} _ _: 116
    case True{} False{} _: 0
    case True{} True{} False{}: 16
    case True{} True{} True{}: 0

# Native reflection and pointer validity supply the two observations. Only the
# admission decision is proved; native array reads and writeback are tested.
def Lifetime.sampled_reply(extent_matches: Bool, nonnull: Bool) -> U32:
  match extent_matches nonnull:
    case False{} _: 22
    case True{} False{}: 22
    case True{} True{}: 0

# Native code supplies enabled core-version and symbol-resolution facts.
def Lifetime.video_epoch(mapped: Bool, active: Bool, owner_alive: Bool) -> U32:
  match mapped active owner_alive:
    case False{} _ _: 0
    case True{} False{} _: 116
    case True{} True{} False{}: 116
    case True{} True{} True{}: 0

# Driver execution and the truth of native observations are integration-tested.
def Lifetime.cleanup_install(empty: Bool, ours: Bool, icu: Bool, active: Bool) -> U32:
  match empty ours icu active:
    case _ _ _ True{}: 16
    case _ _ True{} False{}: 95
    case False{} False{} False{} False{}: 95
    case _ True{} False{} False{}: 0
    case True{} False{} False{} False{}: 0

