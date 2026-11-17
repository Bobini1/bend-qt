#!/usr/bin/env python3
"""Check failed and waiting cleanup callbacks after Bend main returns."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''import Base
import @PACKAGE@ as Qt

def continued(state: Unit) -> Qt.Action(Unit):
  Qt.Action.lift(Unit, IO.print("QT612_POST_ROUTINE_CONTINUED"))

def refused(state: Unit) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 82, "Expected cleanup failure")

def waited(state: Unit) -> Qt.Action(Unit):
  Qt.Action.lift(Unit, IO.sleep(50))

def failure(mode: Bool) -> Qt.Action(Qt.PostRoutine):
  match mode:
    case True{}: Qt.PostRoutine.add(~Unit, ~refused, Unit{})
    case False{}: Qt.PostRoutine.add(~Unit, ~waited, Unit{})

def install(mode: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: Qt.PostRoutine <- Qt.PostRoutine.add(~Unit, ~continued, Unit{})
    second: Qt.PostRoutine <- failure(mode)
    return Unit{}

def select(arguments: List<String>) -> IO(Unit):
  match arguments:
    case program <> mode <> Nil{}: IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => install(String.eq(mode, "fail")))))
    case _: IO.die(Unit, 64, "Expected a cleanup control selector")

def main() -> IO(Unit):
  do IO<Unit>:
    arguments: List<String> <- IO.args()
    select(arguments)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    package, work = args.package.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    receipt_path = work / 'receipt.json'
    receipt_path.write_text(json.dumps(dict(verification_complete=False)) + '\n')
    source, executable = work / 'main.bend', work / 'app'
    source.write_text(SOURCE.replace('@PACKAGE@', (package / 'qt.bend').as_posix()))
    env = dict(os.environ, CXX='/no-consumer-cxx', CPLUS_INCLUDE_PATH='/no-consumer-qt-headers',
               PKG_CONFIG_LIBDIR='/no-consumer-pc')
    command = [str(Path.home() / '.bend/bin/bend'), str(source), '-o', str(executable)]
    compiled = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=600)
    (work / 'build.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode or compiled.stderr:
        raise RuntimeError('Post routine control compilation failed; see ' + str(work / 'build.log'))
    spec = importlib.util.spec_from_file_location('qt612_checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    runtime_env = checks.qt_environment(env, args.qt_root.resolve())
    runs = []
    for mode, expected, diagnostic in [('fail', 82, 'Expected cleanup failure'),
                                       ('wait', 11, 'A Bend handler waited before answering Qt')]:
        result = subprocess.run([str(executable), mode, '+RTS', '--threads', '2'],
            cwd=work, env=runtime_env, text=True, capture_output=True, timeout=30)
        (work / (mode + '.log')).write_text(result.stdout + result.stderr)
        if (result.returncode != expected or 'QT612_POST_ROUTINE_CONTINUED' not in result.stdout
                or diagnostic not in result.stderr or 'QT612_SHUTDOWN_OK' not in result.stdout):
            raise RuntimeError('Post routine ' + mode + ' control failed; see ' + str(work / (mode + '.log')))
        runs.append(dict(mode=mode, exit_code=result.returncode, subsequent_callback_ran=True,
                         shutdown_cleanup=True))
    receipt = dict(verification_complete=True, native_runtime=True, runs=runs,
        package_sha256={name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                        for name in ('qt.bend', 'qt.c')},
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(), command=command)
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS cleanup failure and wait controls: continued callbacks, exit status and native teardown')


if __name__ == '__main__':
    main()
