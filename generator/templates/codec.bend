import Base

def Codec.optional_valid(~A: Data, value: Maybe<&2, A>) -> Bool:
  match value:
    case Some{value}: True{}
    case None{}: False{}

# The same pure transport combinators are imported by the proofs and inlined
# into the package. Native allocation, Qt conversion and scheduling are separate.
type Wire is Data:
  WireScalar{lo: U32, hi: U32}
  WireText{text: String}
  WireSequence{items: List<&2, Wire>}
  WireData{token: U32}

type PairValue<-A: Data, -B: Data> is Data:
  PairValue{first: A, second: B}

def Codec.word(value: U32) -> Wire:
  WireScalar{value, 0}

def Codec.wide(lo: U32, hi: U32) -> Wire:
  WireScalar{lo, hi}

def Codec.read_wide(value: Wire) -> Maybe<&2, PairValue<U32, U32>>:
  match value:
    case WireScalar{lo, hi}: Some{PairValue{lo, hi}}
    case _: None{}

def Codec.read_word(value: Wire) -> Maybe<&2, U32>:
  match value:
    case WireScalar{lo, hi}: Some{lo}
    case _: None{}

def Codec.text(value: String) -> Wire:
  WireText{value}

def Codec.read_text(value: Wire) -> Maybe<&2, String>:
  match value:
    case WireText{text}: Some{text}
    case _: None{}

def Codec.sequence(items: List<&2, Wire>) -> Wire:
  WireSequence{items}

def Codec.read_sequence(value: Wire) -> Maybe<&2, List<&2, Wire>>:
  match value:
    case WireSequence{items}: Some{items}
    case _: None{}

def Codec.pair(first: Wire, second: Wire) -> Wire:
  Codec.sequence(first <> second <> Nil{})

def Codec.read_pair(value: Wire) -> Maybe<&2, PairValue<Wire, Wire>>:
  match value:
    case WireSequence{first <> second <> Nil{}}: Some{PairValue{first, second}}
    case _: None{}

def Codec.cons(-A: Data, head: Maybe<&2, A>, tail: Maybe<&2, List<&2, A>>) -> Maybe<&2, List<&2, A>>:
  match head tail:
    case Some{head} Some{tail}: Some{head <> tail}
    case _ _: None{}

def Codec.encode_items(~A: Data, ~encode: A -> Wire, items: List<&2, A>) -> List<&2, Wire>:
  match items:
    case Nil{}: Nil{}
    case head <> tail: encode(head) <> Codec.encode_items(~A, ~encode, tail)

def Codec.decode_items(~A: Data, ~decode: Wire -> Maybe<&2, A>, items: List<&2, Wire>) -> Maybe<&2, List<&2, A>>:
  match items:
    case Nil{}: Some{Nil{}}
    case head <> tail: Codec.cons(A, decode(head), Codec.decode_items(~A, ~decode, tail))

def Codec.encode_list(~A: Data, ~encode: A -> Wire, items: List<&2, A>) -> Wire:
  Codec.sequence(Codec.encode_items(~A, ~encode, items))

def Codec.decode_list(~A: Data, ~decode: Wire -> Maybe<&2, A>, value: Wire) -> Maybe<&2, List<&2, A>>:
  match value:
    case WireSequence{items}: Codec.decode_items(~A, ~decode, items)
    case _: None{}

def Codec.array_items_count(items: List<&2, Wire>, count: U32) -> Bool:
  match items count:
    case Nil{} 0: True{}
    case _ 0: False{}
    case Nil{} _: False{}
    case head <> tail count: Codec.array_items_count(tail, U32.sub(count, 1))

def Codec.array_count(count: U32, items: List<&2, Wire>) -> Bool:
  Codec.array_items_count(items, count)

def Codec.decode_array_items(~A: Data, ~decode: Wire -> Maybe<&2, A>, valid: Bool, items: List<&2, Wire>) -> Maybe<&2, List<&2, A>>:
  match valid:
    case True{}: Codec.decode_items(~A, ~decode, items)
    case False{}: None{}

def Codec.decode_array_sequence(~A: Data, ~decode: Wire -> Maybe<&2, A>, count: U32, +items: List<&2, Wire>) -> Maybe<&2, List<&2, A>>:
  Codec.decode_array_items(~A, ~decode, Codec.array_count(count, items), items)

def Codec.decode_array(~A: Data, ~decode: Wire -> Maybe<&2, A>, count: U32, value: Wire) -> Maybe<&2, List<&2, A>>:
  match value:
    case WireSequence{items}: Codec.decode_array_sequence(~A, ~decode, count, items)
    case _: None{}

def Codec.encode_optional(~A: Data, ~encode: A -> Wire, value: Maybe<&2, A>) -> Wire:
  match value:
    case None{}: Codec.sequence(Nil{})
    case Some{item}: Codec.sequence(encode(item) <> Nil{})

def Codec.decode_optional(~A: Data, ~decode: Wire -> Maybe<&2, A>, value: Wire) -> Maybe<&2, Maybe<&2, A>>:
  match value:
    case WireSequence{Nil{}}: Some{None{}}
    case WireSequence{item <> Nil{}}:
      do Maybe<&2, Maybe<&2, A>>:
        decoded: A <- decode(item)
        return Some{decoded}
    case _: None{}
