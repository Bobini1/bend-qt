# Each handle keeps the actual native specialization and a concrete mutex type.
def QMutexLocker.new(mutex: QMutex) -> Action(QMutexLocker):
  QMutexLocker.new__QMutex(mutex)

def QRecursiveMutexLocker.new(mutex: QRecursiveMutex) -> Action(QRecursiveMutexLocker):
  QMutexLocker.new__QRecursiveMutex(mutex)
