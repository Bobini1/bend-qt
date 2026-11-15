"""Native plugin inputs for maintainer tests, never consumer build steps."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compiler_flags


def prepare_image_plugin(qt, work):
    plugin = work / 'image-plugin'
    output = plugin / 'imageformats'
    output.mkdir(parents=True, exist_ok=True)
    for name in ('native-image-plugin.cpp', 'native-image-plugin.json'):
        (plugin / name).write_bytes((ROOT / 'scripts/fixtures' / name).read_bytes())
    source = plugin / 'native-image-plugin.cpp'
    includes = ['-I' + str(qt / 'include' / name) for name in ('', 'QtCore', 'QtGui')]
    subprocess.run([str(qt / 'libexec/moc'), *includes, str(source), '-o', str(plugin / 'native-image-plugin.moc')], check=True)
    subprocess.run([*compiler_flags(qt, 'clang++-19', ['QtCore', 'QtGui']), '-shared', str(source),
        '-L' + str(qt / 'lib'), '-lQt6Gui', '-lQt6Core', '-o', str(output / 'libbendrgimage.so')], check=True)
    return plugin
