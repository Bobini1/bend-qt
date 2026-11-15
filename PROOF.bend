import Base
import ./LAWS.bend as Laws
import ./generator/templates/codec.bend as Transport

def Laws.add_zero(x):
  match x:
    case 0n:
      {==}
    case 1n+previous:
      %Laws.add_zero(previous) : {1n+Nat.add(previous, 0n) == 1n+_ : Nat}
      {==}

def Laws.qt_body_error_wins(A, error, released):
  {==}

def Laws.qt_cleanup_error_after_success(A, value, error):
  {==}

def Laws.qt_success_preserves_value(A, value):
  {==}

def Laws.qt_successful_cleanup_preserves_result(A, result):
  match result:
    case Fail{error}: {==}
    case Done{value}: {==}

def Laws.qt_finish_associative(A, result, inner, outer):
  match result:
    case Fail{error}: {==}
    case Done{value}:
      match inner:
        case Fail{error}: {==}
        case Done{unit}:
          match outer:
            case Fail{error}: {==}
            case Done{unit}: {==}

def Laws.qt_finally_sequences_cleanup(A, Out, body, cleanup, scope, next):
  {==}

def Laws.qt_failure_still_cleans_up(A, Out, code, message, cleanup, scope, next):
  {==}

def Laws.qt_success_still_cleans_up(A, Out, value, cleanup, scope, next):
  {==}

def Laws.qt_failed_acquisition_skips_scope(R, A, code, message, release, body):
  {==}

def Laws.qt_acquired_resource_is_scoped(R, A, resource, release, body):
  {==}

def Laws.qt_bind_short_circuits_failure(A, B, code, message, next):
  {==}

def Laws.qt_nested_cleanup_order(A, Out, body, inner, outer, scope, next):
  {==}

def Laws.qt_cleanup_accepts_stale(message):
  {==}

def Laws.qt_cleanup_preserves_success():
  {==}

def absurd(-A: Type, impossible: Empty) -> A:
  match impossible:

# Explicit differing bits let the kernel reduce the numeric-pattern matcher.
# Each case differs from 116 at its first differing bit; together with 116
# these cases cover all U32 values, without assuming the native errno mapping.
def Laws.qt_cleanup_preserves_other_errors(code, message, different):
  match code:
    case U32{WCon{True{}, tail}}: {==}
    case U32{WCon{False{}, WCon{True{}, tail}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{False{}, tail}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{True{}, tail}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{False{}, tail}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{False{}, tail}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{False{}, tail}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{True{}, tail}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}: {==}
    case 116:
      absurd({Done{Unit{}} == Fail{(116, message)} : Laws.Outcome(Unit)}, different({==}))

def Laws.qt_cleanup_normalization_idempotent(result):
  match result:
    case Done{unit}: {==}
    case Fail{(U32{WCon{True{}, tail}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{True{}, tail}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{False{}, tail}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{True{}, tail}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{False{}, tail}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{False{}, tail}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{False{}, tail}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{True{}, tail}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(U32{WCon{False{}, WCon{False{}, WCon{True{}, WCon{False{}, WCon{True{}, WCon{True{}, WCon{True{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{False{}, WCon{True{}, tail}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}, message)}: {==}
    case Fail{(116, message)}: {==}

def Laws.qt_body_halt_bypasses_cleanup(A, Out, code, message, cleanup, scope, next):
  {==}

def Laws.qt_cleanup_applies_policy(Out, cleanup, scope, next):
  {==}

def Laws.qt_body_exit_bypasses_cleanup(Out, code, cleanup, scope, next):
  {==}

def Laws.qt_cleanup_halt_prevents_return(A, Out, result, code, message, scope, next):
  {==}

# Pure container and signal transport contracts.
def Laws.qt_wire_word_roundtrip(word):
  {==}

def Laws.qt_wire_text_roundtrip(text):
  {==}

def Laws.qt_wire_sequence_roundtrip(items):
  {==}

def Laws.qt_wire_pair_preserves_order(first, second):
  {==}

def Laws.qt_wire_pair_rejects_empty():
  {==}

def Laws.qt_wire_pair_rejects_short(item):
  {==}

def Laws.qt_wire_pair_rejects_long(a, b, c, tail):
  {==}

def Laws.qt_codec_failed_head(A, tail):
  match tail:
    case None{}: {==}
    case Some{value}: {==}

def Laws.qt_codec_failed_tail(A, head):
  match head:
    case None{}: {==}
    case Some{value}: {==}

def Laws.qt_codec_word_items_roundtrip(items):
  match items:
    case Nil{}: {==}
    case head <> tail:
      %Laws.qt_codec_word_items_roundtrip(tail) : {Transport.Codec.cons(U32, Some{head}, Transport.Codec.decode_items(~U32, ~Transport.Codec.read_word, Transport.Codec.encode_items(~U32, ~Transport.Codec.word, tail))) == Transport.Codec.cons(U32, Some{head}, _) : Maybe<&2, List<&2, U32>>}
      {==}

def Laws.qt_codec_word_list_roundtrip(items):
  Laws.qt_codec_word_items_roundtrip(items)

def Laws.qt_codec_text_items_roundtrip(items):
  match items:
    case Nil{}: {==}
    case head <> tail:
      %Laws.qt_codec_text_items_roundtrip(tail) : {Transport.Codec.cons(String, Some{head}, Transport.Codec.decode_items(~String, ~Transport.Codec.read_text, Transport.Codec.encode_items(~String, ~Transport.Codec.text, tail))) == Transport.Codec.cons(String, Some{head}, _) : Maybe<&2, List<&2, String>>}
      {==}

def Laws.qt_codec_text_list_roundtrip(items):
  Laws.qt_codec_text_items_roundtrip(items)

def Laws.qt_wire_wide_preserves_all_bits(lo, hi):
  {==}

def Laws.qt_lifetime_owned_scope_deletes():
  {==}

def Laws.qt_lifetime_transferred_scope_keeps():
  {==}

def Laws.qt_lifetime_parent_acquires_ownership(owned, had_parent):
  match owned had_parent:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_detach_restores_ownership(owned):
  match owned:
    case False{}: {==}
    case True{}: {==}

def Laws.qt_lifetime_no_parent_preserves_ownership(owned):
  match owned:
    case False{}: {==}
    case True{}: {==}

def Laws.qt_lifetime_scope_after_parent_keeps(owned, had_parent):
  match owned had_parent:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_scope_after_detach_deletes(owned):
  match owned:
    case False{}: {==}
    case True{}: {==}

def Laws.qt_lifetime_parent_then_detach_restores(owned, had_parent):
  match owned had_parent:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_scoped_transferred_keeps(retained):
  match retained:
    case False{}: {==}
    case True{}: {==}

def Laws.qt_lifetime_scoped_owned_unretained_deletes():
  {==}

def Laws.qt_lifetime_scoped_owned_retained_defers():
  {==}

def Laws.qt_lifetime_unreleased_never_collects(owned, retained):
  match owned retained:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_transferred_never_collects(pending, retained):
  match pending retained:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_retained_never_collects(pending, owned):
  match pending owned:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_removed_dependency_collects():
  {==}

def Laws.qt_optional_word_roundtrip(value):
  match value:
    case None{}: {==}
    case Some{item}: {==}

def Laws.qt_optional_text_roundtrip(value):
  match value:
    case None{}: {==}
    case Some{item}: {==}

def Laws.qt_optional_rejects_multiple_elements(first, second, tail):
  {==}

def Laws.qt_optional_rejects_scalar_shape(lo, hi):
  {==}

def Laws.qt_optional_rejects_invalid_element(text):
  {==}

def Laws.qt_optional_nested_absence_is_present():
  {==}

def Laws.qt_lifetime_move_borrowed_rejects(retained, active, readonly):
  {==}

def Laws.qt_lifetime_move_retained_rejects(owned, active, readonly):
  match owned:
    case False{}: {==}
    case True{}: {==}

def Laws.qt_lifetime_move_active_rejects(owned, retained, readonly):
  match owned retained:
    case False{} _: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_move_readonly_rejects(owned, retained, active):
  match owned retained active:
    case False{} _ _: {==}
    case True{} True{} _: {==}
    case True{} False{} False{}: {==}
    case True{} False{} True{}: {==}

def Laws.qt_lifetime_move_exclusive_allows():
  {==}

def Laws.qt_reply_present_is_valid(value):
  {==}

def Laws.qt_reply_absent_is_invalid():
  {==}

def Laws.qt_incubation_stale_precedes_stop(flag, pending, expired):
  {==}

def Laws.qt_incubation_cancel_stops(pending, expired):
  {==}

def Laws.qt_incubation_empty_stops(expired):
  {==}

def Laws.qt_incubation_deadline_stops():
  {==}

def Laws.qt_incubation_live_work_continues():
  {==}

def Laws.qt_array_zero_accepts_empty():
  {==}

def Laws.qt_array_zero_rejects_elements(head, tail):
  {==}

def Laws.qt_array_four_word_roundtrip(a, b, c, d):
  {==}

def Laws.qt_array_rejects_short_input(a, b, c):
  {==}

def Laws.qt_array_rejects_excess_input(a, b, c, d, e, tail):
  {==}

def Laws.qt_array_rejects_scalar_shape(count, lo, hi):
  {==}

def Laws.qt_array_rejects_invalid_element(text):
  {==}

def Laws.qt_lifetime_future_take_invalid(finished, ready):
  {==}

def Laws.qt_lifetime_future_take_unfinished(ready):
  {==}

def Laws.qt_lifetime_future_take_empty():
  {==}

def Laws.qt_lifetime_future_take_ready():
  {==}

def Laws.qt_paired_array_negative(first_fits, second_fits):
  {==}

def Laws.qt_paired_array_first_short(second_fits):
  {==}

def Laws.qt_paired_array_second_short():
  {==}

def Laws.qt_paired_array_valid():
  {==}

def Laws.qt_lifetime_aggregate_preflight_preserves(succeeded):
  {==}

def Laws.qt_lifetime_aggregate_native_failure_invalidates():
  {==}

def Laws.qt_lifetime_aggregate_native_success_commits():
  {==}

def Laws.qt_lifetime_cleanup_dead(cleaning, causal):
  {==}

def Laws.qt_lifetime_cleanup_ordinary(causal):
  {==}

def Laws.qt_lifetime_cleanup_unrelated():
  {==}

def Laws.qt_lifetime_cleanup_causal():
  {==}

def Laws.qt_lifetime_sampled_extent(nonnull):
  {==}

def Laws.qt_lifetime_sampled_null():
  {==}

def Laws.qt_lifetime_sampled_valid():
  {==}

def Laws.qt_lifetime_video_local(active, owner_alive):
  {==}

def Laws.qt_lifetime_video_unmapped(owner_alive):
  {==}

def Laws.qt_lifetime_video_destroyed():
  {==}

def Laws.qt_lifetime_video_mapped():
  {==}

def Laws.qt_lifetime_cleanup_install_active(empty, ours, icu):
  match empty ours icu:
    case False{} False{} False{}: {==}
    case False{} False{} True{}: {==}
    case False{} True{} False{}: {==}
    case False{} True{} True{}: {==}
    case True{} False{} False{}: {==}
    case True{} False{} True{}: {==}
    case True{} True{} False{}: {==}
    case True{} True{} True{}: {==}

def Laws.qt_lifetime_cleanup_install_icu(empty, ours):
  match empty ours:
    case False{} False{}: {==}
    case False{} True{}: {==}
    case True{} False{}: {==}
    case True{} True{}: {==}

def Laws.qt_lifetime_cleanup_install_foreign():
  {==}

def Laws.qt_lifetime_cleanup_install_own(empty):
  match empty:
    case False{}: {==}
    case True{}: {==}

def Laws.qt_lifetime_cleanup_install_empty():
  {==}



def Laws.qt_action_bind_passes_scope(A, B, Out, action, next, scope, finish):
  {==}
