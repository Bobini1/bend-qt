def HttpRange.closed(first: Int64, last: Int64) -> PairValue<Maybe<&2, Int64>, Maybe<&2, Int64>>:
  PairValue{Some{first}, Some{last}}

def HttpRange.from(first: Int64) -> PairValue<Maybe<&2, Int64>, Maybe<&2, Int64>>:
  PairValue{Some{first}, None{}}

def HttpRange.suffix(length: Int64) -> PairValue<Maybe<&2, Int64>, Maybe<&2, Int64>>:
  PairValue{None{}, Some{length}}
