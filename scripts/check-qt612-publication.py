#!/usr/bin/env python3
"""Run Bend's real publication client against a disposable loopback registry.

No request is sent to the public Hub. This verifies client packaging, not the
public server's acceptance policy or package-size limit.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
BEND = Path.home() / '.bend/bin/bend'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'packages/qt612')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/check/publication')
    args = parser.parse_args()
    package = args.package.resolve()
    spec = importlib.util.spec_from_file_location('publication_package_files', ROOT / 'scripts/check-qt612.py')
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    expected_files = set(checker.package_file_names(package))
    maximum_request = sum((package / name).stat().st_size for name in expected_files) * 2 + 1024 * 1024
    received = []
    errors = []

    class Registry(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, status, body):
            data = body.encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/pow.json':
                self.answer(200, '{"pow":1}')
            else:
                errors.append('Unexpected GET ' + self.path)
                self.answer(404, 'not found')

        def do_POST(self):
            try:
                if self.path != '/':
                    raise ValueError('Unexpected publication route ' + self.path)
                length = int(self.headers['Content-Length'])
                if length <= 0 or length > maximum_request:
                    raise ValueError('Unexpected local test request size')
                data = json.loads(self.rfile.read(length))
                files = data['files']
                if set(files) != expected_files:
                    raise ValueError('Publication included unexpected files: ' + str(sorted(files)))
                for name, text in files.items():
                    if text.encode() != (package / name).read_bytes():
                        raise ValueError('Publication altered ' + name)
                manifest = ''.join(hashlib.sha256(files[name].encode()).hexdigest() + ' ' + name + '\n'
                                   for name in sorted(files))
                identifier = '0x' + hashlib.sha256(manifest.encode()).hexdigest()[:32]
                received.append(dict(package=identifier, request_bytes=length,
                    file_bytes={name: len(text.encode()) for name, text in files.items()}))
                self.answer(200, identifier)
            except Exception as error:
                errors.append(str(error))
                self.answer(400, str(error))

    with http.server.ThreadingHTTPServer(('127.0.0.1', 0), Registry) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='bend-qt-publication-') as directory:
                env = dict(os.environ, BEND_HUB=f'http://127.0.0.1:{server.server_port}',
                           BEND_LIB=str(Path(directory) / 'cache'))
                started = time.monotonic()
                result = subprocess.run([BEND, package / 'qt.bend', '--publish'], env=env,
                    cwd=directory, capture_output=True, text=True, timeout=600)
                elapsed = time.monotonic() - started
        finally:
            server.shutdown()
            thread.join()
    output = args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'client.log').write_text(result.stdout + result.stderr)
    if result.returncode or errors or len(received) != 1:
        raise RuntimeError(f'Local publication failed: {errors}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}')
    if received[0]['package'] not in result.stdout:
        raise RuntimeError('Bend did not report the expected content hash')
    receipt = dict(received[0], command='bend qt.bend --publish', registry='disposable loopback only',
                   elapsed_seconds=round(elapsed, 3),
                   public_hub_publication=False, public_hub_size_acceptance_verified=False)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS actual Bend publication client: local registry only, exact package files and content hash')


if __name__ == '__main__':
    main()
