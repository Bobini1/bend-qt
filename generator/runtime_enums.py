"""Bend-authored Qt enumerations and flags with native metatype identity."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def emit(g):
    g.bend.append((HERE / 'templates/runtime_enums.bend').read_text())


def cpp(g):
    return (HERE / 'templates/runtime_enums.cpp').read_text()
