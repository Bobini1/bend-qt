#!/usr/bin/env python3
"""Check the emitted range adapter against a real versioned Qt model.

Cell conversion is a test double here. The Bend fixture separately checks
the production origin leases, stale handles and failure propagation.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compiler_flags
from convenience_apis import range_declarations
from qt_targets import installed_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/range-model-versions')
    args = parser.parse_args()
    version = installed_version(args.qt_root)
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    current = (ROOT / 'generator/templates/convenience_ranges.h').read_text()
    assert range_declarations(SimpleNamespace(profile={'minimum_qt': '6.12.0'})) == current
    declarations = range_declarations(SimpleNamespace(profile={'minimum_qt': version}))
    common = (ROOT / 'generator/templates/convenience_ranges.cpp').read_text()
    data = common[common.index('QVariant ConvenienceRangeModel::data('):common.index('QVariant ConvenienceRangeModel::headerData(')]
    bridge = (ROOT / 'generator/templates/convenience_ranges_610.cpp').read_text() if version.startswith('6.10.') else ''
    source = '''#include <QtCore/QtCore>
#include <memory>
#include <tuple>
#include <cassert>
namespace bendqt {
struct BqtRequest; struct BqtValue;
@DECLARATIONS@
struct ConvenienceRangeState {};
struct ConvenienceCellOrigin {};
static std::shared_ptr<ConvenienceRangeState> convenience_make_range_state() { return {}; }
static std::shared_ptr<ConvenienceRangeState> convenience_current_range_state() { return {}; }
static void convenience_rebind_cell(ConvenienceRangeCell &, const std::shared_ptr<ConvenienceRangeState> &) {}
QVariant ConvenienceRangeCell::read(int role) const {
    return role == Qt::DisplayRole || role == Qt::EditRole ? value : QVariant();
}
bool ConvenienceRangeCell::write(const QVariant &replacement, int role) {
    if (role != Qt::DisplayRole && role != Qt::EditRole) return !replacement.isValid();
    if (replacement.metaType() == QMetaType::fromType<QString>()) return false;
    value = replacement;
    origin = replacement.isValid() ? std::make_shared<ConvenienceCellOrigin>() : nullptr;
    return true;
}
@DATA@
QVariant ConvenienceRangeModel::headerData(int section, Qt::Orientation orientation, int role) const {
    return QRangeModel::headerData(section, orientation, role);
}
@BRIDGE@
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    using namespace bendqt;
    ConvenienceRangeCell cell; cell.value = 7; cell.origin = std::make_shared<ConvenienceCellOrigin>();
    std::weak_ptr<ConvenienceCellOrigin> original = cell.origin;
    ConvenienceTrackedRange<ConvenienceRangeCell> rows; rows.append(cell);
    ConvenienceRangeModel model(std::move(rows)); cell = {};
    auto index = model.index(0, 0);
    assert(model.data(index).toInt() == 7);
    assert(model.flags(index).testFlag(Qt::ItemIsEditable));
    assert(model.itemData(index).value(Qt::DisplayRole).toInt() == 7);
    QModelRoleData roles[] = {QModelRoleData(Qt::DisplayRole), QModelRoleData(Qt::EditRole), QModelRoleData(Qt::UserRole)};
    roles[2].setData(999);
    model.multiData(index, roles);
    assert(roles[0].data().toInt() == 7 && roles[1].data().toInt() == 7 && !roles[2].data().isValid());
    int changes = 0;
    QObject::connect(&model, &QAbstractItemModel::dataChanged, [&] { ++changes; });
    assert(!model.setData(index, QStringLiteral("reject")));
    assert(changes == 0 && model.data(index).toInt() == 7 && !original.expired());
    assert(model.setData(index, 8));
    assert(changes == 1 && model.data(index).toInt() == 8 && original.expired());
    assert(model.setData(index, 9, Qt::RangeModelDataRole));
    assert(changes == 2 && model.data(index, Qt::RangeModelDataRole).toInt() == 9);
    const bool rejectedMap = model.setItemData(index, {{Qt::DisplayRole, 10}, {Qt::EditRole, QStringLiteral("reject")}});
    // Qt 6.12's implementation preserves the cell and suppresses the signal,
    // but returns true after writeAt fails for an ItemAccess specialization.
    // Check that upstream behavior explicitly, as well as the transaction.
    assert(rejectedMap == @FAILED_MAP_RESULT@);
    assert(changes == 2 && model.data(index).toInt() == 9);
    assert(model.setItemData(index, {{Qt::DisplayRole, 12}, {Qt::EditRole, 12}}));
    assert(changes == 3 && model.data(index).toInt() == 12);
    model.blockSignals(true);
    assert(model.setData(index, 13));
    assert(changes == 3 && model.signalsBlocked());
    model.blockSignals(false);
    assert(model.clearItemData(index));
    assert(!model.data(index).isValid() && changes == 4);
    assert(model.insertRows(1, 1));
    assert(model.setData(model.index(1, 0), 14));
    assert(model.moveRows({}, 1, 1, {}, 0));
    assert(model.data(model.index(0, 0)).toInt() == 14);
    assert(model.removeRows(0, 1));
    ConvenienceTrackedRange<ConvenienceRangeCell> row; row.resize(2);
    ConvenienceTrackedRange<ConvenienceTrackedRange<ConvenienceRangeCell>> table; table.append(row);
    ConvenienceRangeModel matrix(std::move(table));
    assert(matrix.insertColumns(1, 1));
    assert(matrix.setData(matrix.index(0, 1), 15));
    assert(matrix.data(matrix.index(0, 1)).toInt() == 15);
    assert(matrix.removeColumns(1, 1));
}
'''.replace('@DECLARATIONS@', declarations).replace('@DATA@', data).replace('@BRIDGE@', bridge).replace(
        '@FAILED_MAP_RESULT@', 'true' if version == '6.12.0' else 'false')
    path = work / 'main.cpp'
    path.write_text(source)
    flags = [flag for flag in compiler_flags(args.qt_root, 'clang++-19', ['QtCore']) if flag != '-DNDEBUG']
    subprocess.run([*flags, str(path), '-L' + str(args.qt_root / 'lib'), '-lQt6Core', '-o', str(work / 'main')], check=True)
    subprocess.run([str(work / 'main')], env=dict(os.environ, LD_LIBRARY_PATH=str(args.qt_root / 'lib')), check=True)
    (work / 'receipt.json').write_text(json.dumps(dict(qt=version, passed=True,
        actual_qt_range_model=True, emitted_adapter=True, cell_conversion='test_double',
        transactional_edits=True, signals=True, role_reads=True, structural_edits=True,
        upstream_failed_item_data_returns_true=version == '6.12.0'), indent=2) + '\n')
    print('QT_RANGE_MODEL_VERSION_OK qt=' + version)


if __name__ == '__main__':
    main()
