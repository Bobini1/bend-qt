"""Publish generated text without truncating existing or mapped artifacts."""
import os
from pathlib import Path
import uuid


def write_text(path, text):
    path = Path(path)
    data = text.encode('utf-8')
    try:
        if path.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        # Exclusive creation keeps the usual umask permissions. The old file
        # remains intact if writing or replacement fails.
        with temporary.open('xb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
