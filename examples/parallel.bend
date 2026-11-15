import Base

# Each branch does the same amount of independent work on CPU workers.
def leaves(+depth: Nat) -> U32:
  match depth:
    case 0n:
      1
    case 1n+previous:
      left right = leaves(previous) leaves(previous)
      (left + right : U32)

def main() -> IO(Unit):
  IO.print(U32.show(leaves(16n)))
