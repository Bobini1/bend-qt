static constexpr uint32_t convenience_model_slot = 0xffffff9du;
struct ConvenienceHeaderRecord {
    std::shared_ptr<ConvenienceCellOrigin> origin;
    uint64_t revision = 0;
};
struct ConvenienceRangeState {
    uint32_t owner = 0, next_key = 0;
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>>(true);
    std::vector<uint32_t> free_keys;
    std::vector<std::weak_ptr<ConvenienceCellOrigin>> cells;
    uint64_t header_revision = 0;
    std::map<std::tuple<int, int, int>, ConvenienceHeaderRecord> headers;
};
struct ConvenienceCellOrigin {
    uint32_t id = 0, owner = 0, key = 0;
    std::weak_ptr<ConvenienceRangeState> state;
    ~ConvenienceCellOrigin() {
        if (!id) return;
        auto release = [id=id, owner=owner, key=key, state=state] {
            for (auto &edge : retentions)
                if (edge.owner == owner && edge.slot == convenience_model_slot && edge.key == key && edge.target == id) edge = {};
            if (owner && key) if (auto range = state.lock(); range && range->owner == owner) {
                try { range->free_keys.push_back(key); } catch (...) { /* Losing a free key preserves safety. */ }
            }
            callback_unpin(id); schedule_collection();
        };
        if (QThread::currentThread() == main_thread) release();
        else if (auto *context = main_context.load(std::memory_order_acquire))
            QMetaObject::invokeMethod(context, std::move(release), Qt::QueuedConnection);
    }
};
struct ConvenienceRangeRecord { uint32_t id = 0; std::shared_ptr<ConvenienceRangeState> state; };
static SlotTable<ConvenienceRangeRecord> convenience_range_states;
QVariant ConvenienceRangeModel::data(const QModelIndex &index, int role) const {
    auto result = QRangeModel::data(index, role);
    if (result.metaType() == QMetaType::fromType<ConvenienceRangeCell>())
        return static_cast<const ConvenienceRangeCell *>(result.constData())->read(Qt::DisplayRole);
    return result;
}
QVariant ConvenienceRangeModel::headerData(int section, Qt::Orientation orientation, int role) const {
    auto state = convenience_state;
    if (state) {
        const int normalized = role == Qt::EditRole ? int(Qt::DisplayRole) : role;
        const auto found = state->headers.find(std::tuple{int(orientation), section, normalized});
        if (found != state->headers.end() && found->second.origin) {
            if (QThread::currentThread() != main_thread)
                return callback_from_thread<QVariant>(state->alive, [this, section, orientation, role] { return headerData(section, orientation, role); }, [] { return QVariant(); });
            BqtRequest local{};
            auto *request = ConvenienceRangeAccess::current ? ConvenienceRangeAccess::current->request : &local;
            if (!generic_variant_validate(request, found->second.origin->id)) {
                if (request == &local) callback_report_error(request->error, request->message);
                return {};
            }
            if (native_call_scope) { native_call_scope->pin(request, found->second.origin->id); native_call_scope->value_origin = found->second.origin->id; }
        }
    }
    return QRangeModel::headerData(section, orientation, role);
}
static std::shared_ptr<ConvenienceRangeState> convenience_make_range_state() {
    return std::make_shared<ConvenienceRangeState>();
}
static std::shared_ptr<ConvenienceRangeState> convenience_current_range_state() {
    return ConvenienceRangeAccess::current ? ConvenienceRangeAccess::current->state : nullptr;
}
static bool convenience_bind_cell(BqtRequest *r, const std::shared_ptr<ConvenienceCellOrigin> &origin,
                                  const std::shared_ptr<ConvenienceRangeState> &state) {
    if (!origin || !state || !state->owner || origin->owner) return true;
    if (state->free_keys.empty() && state->next_key == UINT32_MAX) { fail(r, ENOSPC, "Range model origin key range exhausted"); return false; }
    const uint32_t key = state->free_keys.empty() ? ++state->next_key : state->free_keys.back();
    if (!state->free_keys.empty()) state->free_keys.pop_back();
    if (!convenience_retain_origin(r, state->owner, origin->id, convenience_model_slot, key)) return false;
    origin->owner = state->owner; origin->key = key; origin->state = state;
    return true;
}
static std::shared_ptr<ConvenienceCellOrigin> convenience_cell_origin(BqtRequest *r, uint32_t id,
        const std::shared_ptr<ConvenienceRangeState> &state) {
    if (!id) return {};
    BqtValue held{}; held.word = id; held.owned_handle = id;
    ConversionValueGuard lease(held);
    auto origin = std::make_shared<ConvenienceCellOrigin>();
    if (!callback_pin(r, id)) return {};
    origin->id = id;
    auto *value = entry(id);
    value->scope_owner = 0; value->pending_release = true;
    lease.release();
    if (state) {
        if (!convenience_bind_cell(r, origin, state)) return {};
        if (!state->owner) {
            if (state->cells.size() >= 32)
                state->cells.erase(std::remove_if(state->cells.begin(), state->cells.end(), [](const auto &cell) { return cell.expired(); }), state->cells.end());
            state->cells.push_back(origin);
        }
    }
    return origin;
}
static bool convenience_bind_range(BqtRequest *r, uint32_t owner, const std::shared_ptr<ConvenienceRangeState> &state) {
    state->owner = owner;
    for (const auto &cell : state->cells)
        if (!convenience_bind_cell(r, cell.lock(), state)) return false;
    state->cells.clear();
    if (auto *root = entry(owner); root && root->alive) state->alive = *root->alive;
    auto &record = convenience_range_states[owner & 65535u];
    auto *object = entry(owner)->object;
    QObject::connect(object, &QObject::destroyed, application, [owner] {
        auto &record = convenience_range_states[owner & 65535u];
        if (record.id == owner) record = {};
    });
    record = {owner, state};
    if (auto *model = dynamic_cast<ConvenienceRangeModel *>(object)) model->convenience_state = state;
    return true;
}
static void convenience_rebind_cell(ConvenienceRangeCell &cell, const std::shared_ptr<ConvenienceRangeState> &state) {
    if (!state) return;
    const bool changed = cell.state != state;
    if (!changed && (!cell.origin || cell.origin->owner || !state->owner)) return;
    auto bind = [&] {
        BqtRequest local{};
        auto *request = ConvenienceRangeAccess::current ? ConvenienceRangeAccess::current->request : &local;
        if (changed) {
            NativeCallScope scope;
            if (cell.origin) scope.pin(request, cell.origin->id);
            const auto id = request->error ? 0 : generic_variant_snapshot(request, cell.value, state->owner, true);
            auto origin = convenience_cell_origin(request, id, state);
            if (request->error) {
                if (request == &local) callback_report_error(request->error, request->message);
                return false;
            }
            cell.state = state;
            cell.origin = std::move(origin);
        }
        const bool accepted = convenience_bind_cell(request, cell.origin, state);
        if (!accepted && request == &local) callback_report_error(request->error, request->message);
        return accepted;
    };
    if (QThread::currentThread() == main_thread) bind();
    else callback_from_thread<bool>(state->alive, bind, [] { return false; });
}
static ConvenienceTrackedRange<ConvenienceRangeCell> convenience_flat_cells(BqtRequest *r,
        const BqtValue &wire, const std::shared_ptr<ConvenienceRangeState> &state) {
    ConvenienceTrackedRange<ConvenienceRangeCell> result(state);
    if (!wire_shape(r, wire, 2)) return result;
    result.reserve(qsizetype(wire.count));
    for (size_t i=0; i<wire.count; ++i) {
        ConvenienceRangeCell cell;
        cell.state = state;
        auto *value = get<QVariant>(r, wire.items[i].word, @VARIANT_ID@, false, false);
        if (r->error) return {};
        cell.origin = convenience_cell_origin(r, convenience_capture_inputs(r, wire.items[i], 0, 0), state);
        if (r->error) return {};
        cell.value = native_owned_snapshot(*value);
        result.append(std::move(cell));
    }
    return result;
}
static ConvenienceTrackedRange<ConvenienceTrackedRange<ConvenienceRangeCell>> convenience_row_cells(BqtRequest *r,
        const BqtValue &wire, const std::shared_ptr<ConvenienceRangeState> &state) {
    ConvenienceTrackedRange<ConvenienceTrackedRange<ConvenienceRangeCell>> result(state);
    if (!wire_shape(r, wire, 2)) return result;
    result.reserve(qsizetype(wire.count));
    for (size_t i=0; i<wire.count; ++i) {
        result.append(convenience_flat_cells(r, wire.items[i], state));
        if (r->error) return {};
    }
    return result;
}
ConvenienceRangeAccess::ConvenienceRangeAccess(BqtRequest *r) : request(r), previous(current) {
    const auto record = convenience_range_states[r->self & 65535u];
    if (record.id == r->self) state = record.state;
    current = this;
}
ConvenienceRangeAccess::~ConvenienceRangeAccess() {
    if (header_slot && !header_finished && header_slot->revision == header_revision) {
        header_slot->origin = std::move(previous_header);
        if (inserted_header && !header_slot->origin) state->headers.erase(header_key);
    }
    current = previous;
}
static int convenience_header_role(int role) { return role == Qt::EditRole ? int(Qt::DisplayRole) : role; }
bool ConvenienceRangeAccess::prepare_header(int section, int orientation, int role, const BqtValue &wire) {
    if (!state) return true;
    header_key = std::tuple{orientation, section, convenience_header_role(role)};
    const auto inserted = state->headers.try_emplace(header_key);
    header_slot = &inserted.first->second;
    inserted_header = inserted.second;
    previous_header = header_slot->origin;
    header_revision = ++state->header_revision;
    header_slot->revision = header_revision;
    const uint32_t id = convenience_capture_inputs(request, wire, 0, state->owner);
    if (request->error) return false;
    header = convenience_cell_origin(request, id, state);
    if (!request->error) { header_slot->origin = header; header_slot->revision = header_revision; }
    return !request->error;
}
bool ConvenienceRangeAccess::read_header(int section, int orientation, int role) {
    if (!state) return true;
    auto found = state->headers.find(std::tuple{orientation, section, convenience_header_role(role)});
    if (found == state->headers.end() || !found->second.origin) return true;
    header = found->second.origin;
    if (!generic_variant_validate(request, header->id)) return false;
    if (native_call_scope) { native_call_scope->pin(request, header->id); native_call_scope->value_origin = header->id; }
    return !request->error;
}
bool ConvenienceRangeAccess::finish(BqtValue &value) {
    if (header_slot) {
        if (!value.word && header_slot->revision == header_revision) {
            header_slot->origin = std::move(previous_header);
            if (inserted_header && !header_slot->origin) state->headers.erase(header_key);
        }
        header_finished = true;
    }
    return !request->error && generic_variant_finish(request, value, native_call_scope ? native_call_scope->value_origin : 0);
}
QVariant ConvenienceRangeCell::read(int role) const {
    if (QThread::currentThread() != main_thread) {
        if (!origin) return role == Qt::DisplayRole || role == Qt::EditRole ? native_owned_snapshot(value) : QVariant();
        auto keep = state;
        if (!keep) return {};
        return callback_from_thread<QVariant>(keep->alive, [this, role] { return read(role); }, [] { return QVariant(); });
    }
    if (role != Qt::DisplayRole && role != Qt::EditRole) return {};
    BqtRequest local{};
    auto *request = ConvenienceRangeAccess::current ? ConvenienceRangeAccess::current->request : &local;
    if (auto actual = convenience_current_range_state(); actual && actual->owner && (!state || !state->owner)) {
        auto *cell = const_cast<ConvenienceRangeCell *>(this);
        cell->state = actual;
        if (!convenience_bind_cell(request, origin, actual)) return {};
    }
    if (origin) {
        if (!generic_variant_validate(request, origin->id)) {
            if (request == &local) callback_report_error(request->error, request->message);
            return {};
        }
        if (native_call_scope) { native_call_scope->pin(request, origin->id); native_call_scope->value_origin = origin->id; }
    }
    return native_owned_snapshot(value);
}
bool ConvenienceRangeCell::write(const QVariant &replacement, int role) {
    if (QThread::currentThread() != main_thread) {
        if (!origin && GenericVariants::independent(replacement.metaType())) {
            if (role != Qt::DisplayRole && role != Qt::EditRole) return false;
            value = native_owned_snapshot(replacement);
            return true;
        }
        auto keep = state;
        if (!keep) return false;
        return callback_from_thread<bool>(keep->alive, [this, &replacement, role] { return write(replacement, role); }, [] { return false; });
    }
    BqtRequest local{};
    auto *request = ConvenienceRangeAccess::current ? ConvenienceRangeAccess::current->request : &local;
    auto owner = state ? state : convenience_current_range_state();
    if (!owner) owner = convenience_make_range_state();
    if (auto actual = convenience_current_range_state(); actual && actual->owner && (!owner || !owner->owner)) owner = actual;
    NativeCallScope scope;
    // The native caller's value handle is the only conversion source. The
    // QModelIndex used to locate this cell is not a value dependency.
    const QVariant *input = &replacement;
    auto *access = ConvenienceRangeAccess::current;
    if (access && access->data_input) {
        const auto &wire = *access->data_input;
        if (!access->input_shape) {
            auto *source = entry(wire.word);
            if (source && source->type == @VARIANT_ID@) get<QVariant>(request, wire.word, @VARIANT_ID@, false, false);
        } else {
            const BqtValue *selected = nullptr;
            for (size_t i=0; i<wire.count; ++i) {
                const auto &pair = wire.items[i];
                const int key = int32_t(pair.items[0].word);
                if (role == Qt::DisplayRole || role == Qt::EditRole) {
                    if (key == Qt::EditRole || (key == Qt::DisplayRole && !selected)) selected = &pair.items[1];
                } else if (key == role) selected = &pair.items[1];
            }
            // QRangeModel's custom access protocol visits every known role.
            // Missing map roles are not requests to clear existing data.
            if (!selected) return true;
            input = get<QVariant>(request, selected->word, @VARIANT_ID@, false, false);
        }
    }
    if (request->error) return false;
    if (role != Qt::DisplayRole && role != Qt::EditRole) return !input->isValid();
    const uint32_t id = request->error ? 0 : generic_variant_snapshot(request, *input, owner ? owner->owner : 0, true);
    if (request->error) return false;
    ConvenienceRangeCell next;
    next.state = std::move(owner);
    next.origin = convenience_cell_origin(request, id, next.state);
    if (request->error) return false;
    next.value = native_owned_snapshot(*input);
    *this = std::move(next);
    return true;
}
