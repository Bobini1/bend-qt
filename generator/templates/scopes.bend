# Root evaluation creates one native resource context. These definitions are
# deliberately separate from the pure Action source used by the law checker.
def Scope.evaluate(-A: Type, action: Action(A), created: Result<&1, &1, U32 & String, U32>) -> IO(Result<&1, &1, U32 & String, A>):
  match created:
    case Fail{error}: IO.pure(Result<&1, &1, U32 & String, A>, Fail{error})
    case Done{+scope}:
      do IO<Result<&1, &1, U32 & String, A>>:
        result: Result<&1, &1, U32 & String, A> <- action(scope)
        cleanup: Result<&1, &1, U32 & String, Unit> <- Scope.close(scope, 0)
        return Action.finish(A, result, cleanup)

def run(-A: Type, action: Action(A)) -> IO(Result<&1, &1, U32 & String, A>):
  do IO<Result<&1, &1, U32 & String, A>>:
    scope: Result<&1, &1, U32 & String, U32> <- Scope.open(0, 0)
    Scope.evaluate(A, action, scope)

def scoped(-A: Type, action: Action(A)) -> Action(A):
  +parent => do IO<Result<&1, &1, U32 & String, A>>:
    scope: Result<&1, &1, U32 & String, U32> <- Scope.open(parent, parent)
    Scope.evaluate(A, action, scope)
