#!/usr/bin/env python3
"""Check unchanged, mapped and failed generated-file publication."""
import errno
import mmap
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from output_files import write_text


def main():
    with tempfile.TemporaryDirectory(prefix='bend-output-writes-') as directory:
        target = Path(directory) / 'coverage.json'
        first, second = '{"value":"初"}\n', '{"value":"next"}\n'
        assert write_text(target, first)
        before = target.stat()
        with target.open('rb') as reader, mmap.mmap(reader.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
            assert not write_text(target, first)
            assert target.stat().st_mtime_ns == before.st_mtime_ns
            assert write_text(target, second)
            assert mapping[:] == first.encode()
            assert target.read_text() == second
        with patch('output_files.os.replace', side_effect=OSError(errno.EACCES, 'Injected replacement failure')):
            try:
                write_text(target, first)
            except OSError as error:
                assert error.errno == errno.EACCES
            else:
                raise AssertionError('The replacement failure was ignored')
        assert target.read_text() == second
        assert sorted(path.name for path in target.parent.iterdir()) == ['coverage.json']
    print('PASS generated output writes: unchanged files, mapped readers, atomic replacement and failure rollback')


if __name__ == '__main__':
    main()
