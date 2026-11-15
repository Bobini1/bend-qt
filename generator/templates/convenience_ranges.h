struct ConvenienceRangeState;
struct ConvenienceCellOrigin;
struct ConvenienceHeaderRecord;
static std::shared_ptr<ConvenienceRangeState> convenience_make_range_state();
static std::shared_ptr<ConvenienceRangeState> convenience_current_range_state();
struct ConvenienceRangeCell {
    std::shared_ptr<ConvenienceRangeState> state;
    std::shared_ptr<ConvenienceCellOrigin> origin;
    // Reverse member destruction destroys the Qt payload before its lease.
    QVariant value;
    ConvenienceRangeCell() : state(convenience_current_range_state()) {}
    ConvenienceRangeCell(const ConvenienceRangeCell &) = default;
    ConvenienceRangeCell(ConvenienceRangeCell &&) noexcept = default;
    ConvenienceRangeCell &operator=(ConvenienceRangeCell other) noexcept {
        state.swap(other.state); origin.swap(other.origin); value.swap(other.value); return *this;
    }
    QVariant read(int) const;
    bool write(const QVariant &, int);
    friend bool operator==(const ConvenienceRangeCell &a, const ConvenienceRangeCell &b) { return a.read(Qt::DisplayRole) == b.read(Qt::DisplayRole); }
    friend bool operator<(const ConvenienceRangeCell &a, const ConvenienceRangeCell &b) { return QVariant::compare(a.read(Qt::DisplayRole), b.read(Qt::DisplayRole)) == QPartialOrdering::Less; }
};
class ConvenienceRangeModel : public QRangeModel {
public:
    using QRangeModel::QRangeModel;
    std::shared_ptr<ConvenienceRangeState> convenience_state;
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role = Qt::DisplayRole) const override;
    bool setData(const QModelIndex &index, const QVariant &value, int role = Qt::EditRole) override {
        return QRangeModel::setData(index, value, role == Qt::RangeModelDataRole || role == Qt::RangeModelAdapterRole ? int(Qt::EditRole) : role);
    }
};
static void convenience_rebind_cell(ConvenienceRangeCell &, const std::shared_ptr<ConvenienceRangeState> &);
template<class T> class ConvenienceTrackedRange : public QList<T> {
    using Base = QList<T>;
    void adopt(T &item) {
        if constexpr (std::is_same_v<T, ConvenienceRangeCell>) convenience_rebind_cell(item, state);
        else item.rebind(state);
    }
public:
    std::shared_ptr<ConvenienceRangeState> state;
    using typename Base::iterator;
    using typename Base::const_iterator;
    ConvenienceTrackedRange() : state(convenience_current_range_state()) {}
    explicit ConvenienceTrackedRange(std::shared_ptr<ConvenienceRangeState> owner) : state(std::move(owner)) {}
    ConvenienceTrackedRange(const ConvenienceTrackedRange &) = default;
    ConvenienceTrackedRange(ConvenienceTrackedRange &&) noexcept = default;
    ConvenienceTrackedRange &operator=(ConvenienceTrackedRange other) noexcept { swap(other); return *this; }
    void swap(ConvenienceTrackedRange &other) noexcept {
        if (!other.state) other.state = state;
        if (!state) state = other.state;
        state.swap(other.state); Base::swap(other);
    }
    friend void swap(ConvenienceTrackedRange &a, ConvenienceTrackedRange &b) noexcept { a.swap(b); }
    void rebind(const std::shared_ptr<ConvenienceRangeState> &owner) {
        state = owner; for (auto &item : *this) adopt(item);
    }
    void resize(qsizetype count) { Base::resize(count); for (auto &item : *this) adopt(item); }
    void resize(qsizetype count, const T &value) {
        T copy(value); adopt(copy);
        Base::resize(count, copy);
        for (auto &item : *this) adopt(item);
    }
    iterator insert(const_iterator position, qsizetype count, const T &value) {
        const auto offset = position - Base::cbegin();
        T copy(value); adopt(copy);
        return Base::insert(Base::cbegin() + offset, count, copy);
    }
    template<class It, std::enable_if_t<!std::is_integral_v<It>, int> = 0>
    iterator insert(const_iterator position, It first, It last) {
        const auto offset = position - Base::cbegin();
        QList<T> items;
        for (; first != last; ++first) { T item(*first); adopt(item); items.append(std::move(item)); }
        Base::reserve(Base::size() + items.size());
        qsizetype inserted = 0;
        for (auto &item : items) Base::insert(offset + inserted++, std::move(item));
        return Base::begin() + offset;
    }
};
static ConvenienceTrackedRange<ConvenienceRangeCell> convenience_flat_cells(BqtRequest *,
    const BqtValue &, const std::shared_ptr<ConvenienceRangeState> &);
static ConvenienceTrackedRange<ConvenienceTrackedRange<ConvenienceRangeCell>> convenience_row_cells(BqtRequest *,
    const BqtValue &, const std::shared_ptr<ConvenienceRangeState> &);
static bool convenience_bind_range(BqtRequest *, uint32_t, const std::shared_ptr<ConvenienceRangeState> &);
struct ConvenienceRangeAccess {
    BqtRequest *request;
    ConvenienceRangeAccess *previous;
    std::shared_ptr<ConvenienceRangeState> state;
    std::shared_ptr<ConvenienceCellOrigin> header;
    std::shared_ptr<ConvenienceCellOrigin> previous_header;
    ConvenienceHeaderRecord *header_slot = nullptr;
    std::tuple<int, int, int> header_key{};
    uint64_t header_revision = 0;
    bool inserted_header = false, header_finished = false;
    const BqtValue *data_input = nullptr;
    unsigned input_shape = 0;
    static inline thread_local ConvenienceRangeAccess *current = nullptr;
    explicit ConvenienceRangeAccess(BqtRequest *);
    ~ConvenienceRangeAccess();
    bool prepare_header(int, int, int, const BqtValue &);
    bool read_header(int, int, int);
    bool finish(BqtValue &);
};
} // namespace bendqt
template<> struct QRangeModel::ItemAccess<bendqt::ConvenienceRangeCell> {
    static QVariant readRole(const bendqt::ConvenienceRangeCell &cell, int role) { return cell.read(role); }
    static bool writeRole(bendqt::ConvenienceRangeCell &cell, const QVariant &value, int role) { return cell.write(value, role); }
    static Qt::ItemFlags flags(const bendqt::ConvenienceRangeCell &) {
        return Qt::ItemIsSelectable | Qt::ItemIsEnabled | Qt::ItemIsEditable;
    }
};
namespace bendqt {
