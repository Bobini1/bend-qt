import Base

# Qt calls a Bend handler with the token of its pending call and the call's
# arguments. A handler runs on Qt's own stack and Qt waits for it, as it does
# for a C++ slot or override. Its arguments are valid during the call: copy a
# Qt value to keep it longer.
type HandlerRequest is Data:
  HandlerRequest{call: U32, arguments: Wire}

def HandlerRequest.decode(value: Wire) -> Maybe<&2, HandlerRequest>:
  match value:
    case WireSequence{WireScalar{call, 0} <> arguments <> Nil{}}:
      Some{HandlerRequest{call, arguments}}
    case _: None{}

def Handler.malformed(-A: Type) -> Action(A):
  Action.fail(A, 22, "Malformed Qt handler request")

# A virtual method handler that fails with this result asks Qt to run the C++
# base implementation instead, as an override calling its base class does.
def Virtual.base(-A: Type) -> Action(A):
  Action.fail(A, 38, "Use the C++ base implementation")
