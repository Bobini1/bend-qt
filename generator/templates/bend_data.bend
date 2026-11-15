# A closed type witness keeps its lambda inside one specialization. The
# structural recursion prevents call-site lambda lifting from assigning a new
# identity to each use. This is part of the pinned Bend native effect boundary.
def Internal.Data.witness(~A: Data, count: Nat) -> A -> A:
  match count:
    case 0n: value => value
    case 1n+rest: Internal.Data.witness(~A, rest)

def Internal.Data.capture_raw(-A: Data, scope: U32, witness: A -> A, value: A) -> IO(Result<&1, &1, U32 & String, Wire>):
  import "./qt.c"

def Internal.Data.extract_raw(-A: Data, witness: A -> A, wire: Wire) -> IO(Result<&1, &1, U32 & String, A>):
  import "./qt.c"

def Internal.Data.encode(-A: Data, witness: A -> A, value: A) -> Action(Wire):
  scope => Internal.Data.capture_raw(A, scope, witness, value)

def Internal.Data.decode(-A: Data, witness: A -> A, wire: Wire) -> Action(A):
  Action.fromIO(A, Internal.Data.extract_raw(A, witness, wire))

def Wire.releaseData(value: Wire) -> Action(Unit):
  match value:
    case WireData{token}: Internal.Data.release_raw(token)
    case _: Action.pure(Unit, Unit{})

def Wire.withData(-A: Type, acquire: Action(Wire), body: Wire -> Action(A)) -> Action(A):
  Action.using(Wire, A, acquire, Wire.releaseData, body)

# Bracket each encoded argument, so a later encoding or native call failure
# immediately releases earlier temporary Bend payloads as well.
def EncodedArguments(-A: Type) -> Type:
  (List<&2, Wire> -> Action(A)) -> Action(A)

def EncodedArguments.empty(-A: Type) -> EncodedArguments(A):
  next => next(Nil{})

# @PUBLIC@

def arg(~A: Data) -> SignalArgument:
  BendArgument{A, Internal.Data.witness(~A, 0n)}

# @VARIANT@

def QVariant.fromData(~A: Data, value: A) -> Action(QVariant):
  Wire.withData(QVariant, SignalArgument.encode(arg(~A), value), Internal.Data.variant_raw)

def QVariant.toData(~A: Data, value: QVariant) -> Action(A):
  Wire.withData(A, Internal.Data.from_variant_raw(value), wire => SignalArgument.decode(arg(~A), wire))
