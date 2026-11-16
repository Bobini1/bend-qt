#!/usr/bin/env python3
"""Check typed QObject authoring against the actual generated Bend module."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def check(package, output):
    output.mkdir(parents=True, exist_ok=True)
    module = (package / 'qt.bend').read_text()
    hashes = {}
    for name in ('runtime_enums.bend', 'qt_object_types.bend', 'qt_objects.bend', 'qt_object_qml.bend',
                 'object_type_access.bend', 'qml_registrations.bend', 'generic_variants.bend'):
        source = (ROOT / 'generator/templates' / name).read_text()
        if module.count(source) != 1:
            raise RuntimeError('Generated module differs from ' + name)
        hashes[name] = hashlib.sha256(source.encode()).hexdigest()
    imported = os.path.relpath(package / 'qt.bend', output).replace(os.sep, '/')
    prefix = '''import Base
import @IMPORT@ as Qt

def age() -> Qt.Property:
  Qt.Property.define("age", Qt.int32())
def Person() -> Qt.ObjectType:
  Qt.QObject.define("TypedPerson", [Qt.Property.withReset(age())])
def Other() -> Qt.ObjectType:
  Qt.QObject.define("OtherPerson", [])

def Child() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Person(), "ChildPerson", [])
def peer() -> Qt.Property:
  Qt.Property.define("peer", Qt.ObjectType.arg(~Person()))
def describe() -> Qt.Method:
  Qt.Method.define("describe", [Qt.int32()], Qt.string())
def handler(state: Unit, value: Qt.Int32) -> Qt.Action(String):
  Qt.Action.pure(String, "typed")

'''.replace('@IMPORT@', imported)
    valid = '''def install(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Method.handle(~describe(), ~Unit, ~handler, object, Unit{})
def call(object: Qt.QObject) -> Qt.Action(String):
  Qt.Method.call(~describe(), object, Qt.Int32{42})
def store(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Property.set(~age(), object, Qt.Int32{42})
'''
    cases = {
        'valid_members': (prefix + valid, True),
        'valid_derived_native_base': (prefix + valid + '''def base(value: Qt.ObjectType.Instance(Child())) -> Qt.QObject:
  Qt.ObjectType.asNativeBase(~Child(), value)
''', True),
        'wrong_derived_native_base': (prefix + valid + '''def base(value: Qt.ObjectType.Instance(Child())) -> Qt.QQuickItem:
  Qt.ObjectType.asNativeBase(~Child(), value)
''', False),
        'wrong_property_value': (prefix + valid.replace('Qt.Property.set(~age(), object, Qt.Int32{42})',
                                                       'Qt.Property.set(~age(), object, "wrong")'), False),
        'wrong_method_argument': (prefix + valid.replace('Qt.Method.call(~describe(), object, Qt.Int32{42})',
                                                        'Qt.Method.call(~describe(), object, "wrong")'), False),
        'wrong_handler_argument': (prefix.replace('value: Qt.Int32', 'value: String') + valid, False),
        'wrong_handler_result': (prefix.replace('-> Qt.Action(String):', '-> Qt.Action(Bool):')
                                .replace('Qt.Action.pure(String, "typed")', 'Qt.Action.pure(Bool, True{})') + valid, False),
        'valid_concrete_object': (prefix + '''def store_peer(object: Qt.QObject, value: Qt.ObjectType.Instance(Person())) -> Qt.Action(Unit):
  Qt.Property.set(~peer(), object, value)
''', True),
        'wrong_concrete_object': (prefix + '''def store_peer(object: Qt.QObject, value: Qt.ObjectType.Instance(Other())) -> Qt.Action(Unit):
  Qt.Property.set(~peer(), object, value)
''', False),
    }
    qml = prefix + '''def Provider() -> Qt.ObjectType:
  Qt.ObjectType.withAttached(Person(), Other())

def initialize(state: Unit, object: Qt.ObjectType.Instance(Provider())) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def attached(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Other())):
  Qt.ObjectType.new(~Other())

def install_qml(+registration: Qt.Qml.Registration(Provider())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Qml.handleCreate(~Provider(), ~Unit, ~initialize, registration, Unit{})
    Qt.Qml.handleAttached(~Provider(), ~Unit, ~attached, registration, Unit{})
'''
    cases['valid_qml_factories'] = (qml, True)
    cases['wrong_registration_schema'] = (qml.replace('Qt.Qml.Registration(Provider())', 'Qt.Qml.Registration(Other())'), False)
    cases['object_as_registration'] = (qml.replace('registration: Qt.Qml.Registration(Provider())', 'registration: Qt.QObject'), False)
    cases['registration_as_object'] = (prefix + '''def wrong(value: Qt.Qml.Registration(Person())) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(value, "not an instance")
''', False)
    cases['registration_as_instance'] = (prefix + '''def wrong(value: Qt.Qml.Registration(Person())) -> Qt.Action(Unit):
  Qt.ObjectType.set(~Person(), ~age(), value, Qt.Int32{42})
''', False)
    cases['script_registration_as_instance'] = (prefix + '''def wrong(value: Qt.Qml.RegistrationHandle) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(value, "not an instance")
''', False)
    typed = '''def access(+object: Qt.ObjectType.Instance(Person())) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    Qt.ObjectType.set(~Person(), ~age(), object, Qt.Int32{42})
    Qt.ObjectType.get(~Person(), ~age(), object)
'''
    cases['valid_typed_access'] = (prefix + typed, True)
    cases['wrong_typed_instance'] = (prefix + typed.replace('object: Qt.ObjectType.Instance(Person())', 'object: Qt.ObjectType.Instance(Other())'), False)
    cases['wrong_typed_value'] = (prefix + typed.replace('object, Qt.Int32{42}', 'object, "wrong"'), False)
    cases['wrong_qml_initializer'] = (qml.replace('object: Qt.ObjectType.Instance(Provider())', 'object: Qt.ObjectType.Instance(Other())'), False)
    cases['wrong_qml_attached_result'] = (qml.replace('-> Qt.Action(Qt.ObjectType.Instance(Other())):', '-> Qt.Action(Qt.ObjectType.Instance(Person())):').replace('Qt.ObjectType.new(~Other())', 'Qt.ObjectType.new(~Person())'), False)
    resetter = '''def reset_age(state: Unit) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def install_reset(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Property.handleResetter(~age(), ~Unit, ~reset_age, object, Unit{})
'''
    cases['valid_resetter'] = (prefix + valid + resetter, True)
    cases['wrong_resetter_argument'] = (prefix + valid + resetter.replace('reset_age(state: Unit)', 'reset_age(state: Unit, value: Qt.Int32)'), False)
    cases['wrong_resetter_result'] = (prefix + valid + resetter.replace('reset_age(state: Unit) -> Qt.Action(Unit)', 'reset_age(state: Unit) -> Qt.Action(String)').replace('Qt.Action.pure(Unit, Unit{})', 'Qt.Action.pure(String, "wrong")'), False)
    cases['wrong_stored_flag'] = (prefix + valid + '''def bad_property() -> Qt.Property:
  Qt.Property.withStored(age(), "false")
''', False)
    enum_values = '''
def State() -> Qt.Enum:
  Qt.Enum.define("TypedEnumSubject::State", [Qt.Enum.key("Ready", 1)])

def OtherState() -> Qt.Enum:
  Qt.Enum.define("TypedEnumSubject::OtherState", [Qt.Enum.key("Ready", 1)])

def value() -> Qt.Property:
  Qt.Property.define("value", Qt.Enum.arg(~State()))

def assign(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Property.set(~value(), object, Qt.Enum.fromU32(~State(), 1))
'''
    cases['valid_enum_value'] = (prefix + enum_values, True)
    cases['wrong_enum_value'] = (prefix + enum_values.replace('Qt.Enum.fromU32(~State(), 1)',
                                                             'Qt.Enum.fromU32(~OtherState(), 1)'), False)
    generic_variant = '''
def round_trip() -> Qt.Action(String):
  do Qt.Action<String>:
    value: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.string(), "typed")
    Qt.QVariant.toValue(~Qt.string(), value)
'''
    cases['valid_generic_variant'] = (prefix + generic_variant, True)
    cases['wrong_generic_variant_input'] = (prefix + generic_variant.replace('~Qt.string(), "typed"', '~Qt.string(), 42'), False)
    cases['wrong_generic_variant_result'] = (prefix + generic_variant.replace('Qt.QVariant.toValue(~Qt.string(), value)',
                                                                           'Qt.QVariant.toValue(~Qt.u32(), value)'), False)
    results = {}
    for name, (source, valid) in cases.items():
        path = output / (name + '.bend'); path.write_text(source)
        result = subprocess.run([str(Path.home() / '.bend/bin/bend'), str(path), '--check-only'],
                                text=True, capture_output=True, timeout=180, cwd=ROOT)
        diagnostic = (result.stdout + result.stderr).strip()
        (output / (name + '.log')).write_text(diagnostic + '\n')
        expected = bool(re.fullmatch(r'SOME PROOFS FAIL\nError: \d+ defs rely on unsafe or foreign code:\n'
                                    r'defs that depend on foreign effects: [A-Za-z0-9_./, \n]+', diagnostic)) if valid else (
                                        '- expected :' in diagnostic and '- observed :' in diagnostic)
        if result.returncode != 1 or not expected:
            raise RuntimeError(f'Unexpected QObject type check: {name}: {diagnostic[:2000]}')
        results[name] = 'typed' if valid else 'rejected'
    receipt = dict(cases=results, source_identity=hashes, native_runtime_proved=False)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    rejected = sum(not valid for _, valid in cases.values())
    print(f'PASS typed QObject/QML members: valid programs and {rejected} incompatible programs rejected')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    check(package, package / 'qt-object-types')
