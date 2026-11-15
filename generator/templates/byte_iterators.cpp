static QByteArray *byte_iterator_source(BqtRequest *r, const QByteArrayIterator &value, bool writable)
{
    auto *source = get<QByteArray>(r, value.owner, @ARRAY@, false, writable);
    if (r->error) return nullptr;
    if (source->constData() != value.storage.constData() || source->size() != value.storage.size()) {
        fail(r, ESTALE, "QByteArray iterator was invalidated by storage mutation"); return nullptr;
    }
    if (value.offset < 0 || value.offset > source->size()) {
        fail(r, ERANGE, "QByteArray iterator is outside its array"); return nullptr;
    }
    return source;
}
static uint32_t new_byte_iterator(BqtRequest *r, uint32_t owner, qsizetype offset, bool writable)
{
    auto *source = get<QByteArray>(r, owner, @ARRAY@, false, false);
    if (r->error) return 0;
    // A shared storage reference prevents deallocation/address reuse; later Qt
    // mutations detach, so validation can reject the previous generation.
    const auto id = own(r, new QByteArrayIterator{owner, offset, *source, writable}, @ITERATOR@);
    if (!id) return 0;
    BqtRequest relationship{}; relationship.self = id;
    constexpr uint32_t iterator_slot = 0xffffffe4;
    const auto slot = prepare_retention(&relationship, iterator_slot, 0, owner);
    if (relationship.error) {
        auto *value = static_cast<QByteArrayIterator *>(entry(id)->value);
        invalidate(id); delete value;
        fail(r, relationship.error, relationship.message); return 0;
    }
    commit_retention(slot, id, iterator_slot, 0, owner, nullptr);
    return id;
}
