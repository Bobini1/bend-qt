import Base

# Fallible Qt actions compose directly in do Action<T> blocks.
# Each computation receives its resource scope explicitly. The shared source
# contains only ordinary Bend functions; Qt.run supplies native scope effects.

def Action.Raw(-A: Type) -> Type:
  U32 -> IO(A)

def Action.Raw.pure(-A: Type, value: A) -> Action.Raw(A):
  scope => IO.pure(A, value)

def Action.Raw.bind(-A: Type, -B: Type, action: Action.Raw(A), next: A -> Action.Raw(B)) -> Action.Raw(B):
  +scope => IO.bind(A, B, action(scope), value => next(value, scope))
def Action(-A: Type) -> Type:
  Action.Raw(Result<&1, &1, U32 & String, A>)

def Action.result(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Action(A):
  Action.Raw.pure(Result<&1, &1, U32 & String, A>, result)

def Action.fromIO(-A: Type, action: IO(Result<&1, &1, U32 & String, A>)) -> Action(A):
  scope => action

def Action.pure(-A: Type, value: A) -> Action(A):
  Action.result(A, Done{value})

def Action.next(-A: Type, -B: Type, result: Result<&1, &1, U32 & String, A>, next: A -> Action(B)) -> Action(B):
  match result:
    case Fail{error}:
      Action.result(B, Fail{error})
    case Done{value}:
      next(value)

def Action.bind(-A: Type, -B: Type, action: Action(A), next: A -> Action(B)) -> Action(B):
  Action.Raw.bind(Result<&1, &1, U32 & String, A>, Result<&1, &1, U32 & String, B>, action,
    result => Action.next(A, B, result, next))

def Action.fail(-A: Type, code: U32, message: String) -> Action(A):
  Action.result(A, Fail{(code, message)})

def Action.lift(-A: Type, action: IO(A)) -> Action(A):
  scope => IO.bind(A, Result<&1, &1, U32 & String, A>, action,
    value => IO.pure(Result<&1, &1, U32 & String, A>, Done{value}))

# Observe a result without propagating its failure out of the current block.
def Action.attempt(-A: Type, action: Action(A)) -> Action(Result<&1, &1, U32 & String, A>):
  scope => IO.bind(Result<&1, &1, U32 & String, A>, Result<&1, &1, U32 & String, Result<&1, &1, U32 & String, A>>,
    action(scope), value => IO.pure(Result<&1, &1, U32 & String, Result<&1, &1, U32 & String, A>>, Done{value}))

# A body failure takes precedence over a cleanup failure. Cleanup still runs.
def Action.finish(-A: Type, result: Result<&1, &1, U32 & String, A>, cleanup: Result<&1, &1, U32 & String, Unit>) -> Result<&1, &1, U32 & String, A>:
  match result:
    case Fail{error}:
      Fail{error}
    case Done{value}:
      match cleanup:
        case Fail{error}:
          Fail{error}
        case Done{unit}:
          Done{value}

def Action.finally(-A: Type, action: Action(A), cleanup: Action(Unit)) -> Action(A):
  +scope => do IO<Result<&1, &1, U32 & String, A>>:
    result: Result<&1, &1, U32 & String, A> <- action(scope)
    released: Result<&1, &1, U32 & String, Unit> <- cleanup(scope)
    return Action.finish(A, result, released)

# Acquisition failure skips both the body and release. The resource is copied
# only to keep one handle for release while the body uses the other.
def Action.using(-R: Data, -A: Type, acquire: Action(R), release: R -> Action(Unit), body: R -> Action(A)) -> Action(A):
  Action.bind(R, A, acquire,
    +resource => Action.finally(A, body(resource), release(resource)))

# Generated scopes accept an already-destroyed/disconnected resource (ESTALE).
# Explicit destroy/disconnect operations retain their strict error behavior.
def Action.cleanup_result(result: Result<&1, &1, U32 & String, Unit>) -> Result<&1, &1, U32 & String, Unit>:
  match result:
    case Fail{(116, message)}:
      Done{Unit{}}
    case Fail{error}:
      Fail{error}
    case Done{unit}:
      Done{unit}

def Action.cleanup(action: Action(Unit)) -> Action(Unit):
  scope => do IO<Result<&1, &1, U32 & String, Unit>>:
    result: Result<&1, &1, U32 & String, Unit> <- action(scope)
    return Action.cleanup_result(result)
