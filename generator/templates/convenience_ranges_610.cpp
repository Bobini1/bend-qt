// Qt 6.10 has no ItemAccess customization. Its range still stores the same
// owning cells; only the virtual model access needs adapting.
bool ConvenienceRangeModel::convenience_commit(const QModelIndex &index,
        const ConvenienceRangeCell &cell, const QList<int> &roles) {
    bool accepted;
    {
        const QSignalBlocker blocker(this);
        accepted = QRangeModel::setData(index, QVariant::fromValue(cell), Qt::EditRole);
    }
    if (accepted) emit dataChanged(index, index, roles);
    return accepted;
}
bool ConvenienceRangeModel::setData(const QModelIndex &index, const QVariant &value, int role) {
    const auto current = QRangeModel::data(index, Qt::RangeModelDataRole);
    if (current.metaType() != QMetaType::fromType<ConvenienceRangeCell>()) return false;
    auto cell = current.value<ConvenienceRangeCell>();
    const int normalized = role == Qt::RangeModelDataRole ? int(Qt::EditRole) : role;
    if (!cell.write(value, normalized)) return false;
    return convenience_commit(index, cell,
        normalized == Qt::EditRole ? QList<int>{} : QList<int>{role});
}
bool ConvenienceRangeModel::setItemData(const QModelIndex &index, const QMap<int, QVariant> &values) {
    if (values.isEmpty()) return false;
    const auto current = QRangeModel::data(index, Qt::RangeModelDataRole);
    if (current.metaType() != QMetaType::fromType<ConvenienceRangeCell>()) return false;
    auto cell = current.value<ConvenienceRangeCell>();
    for (auto it = values.cbegin(); it != values.cend(); ++it) {
        const int role = it.key() == Qt::RangeModelDataRole ? int(Qt::EditRole) : it.key();
        if (!cell.write(it.value(), role)) return false;
    }
    return convenience_commit(index, cell, values.keys());
}
