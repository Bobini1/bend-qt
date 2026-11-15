#ifdef BQT_BYTE_ITERATOR_BEGIN
static void byte_iterator_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    const auto bytes = own(&request, new QByteArray("abcd"), BQT_GL_BYTE_ARRAY_TYPE);
    auto call = [&](auto operation, uint32_t self) {
        request = {}; request.self = self; operation(&request);
    };
    auto release = [&](uint32_t id) { call(destroy_object, id); assert(!request.error); };
    call(BQT_BYTE_ITERATOR_BEGIN, bytes);
    assert(!request.error);
    const auto begin = request.result.word;
    call(BQT_BYTE_ITERATOR_CONST_BEGIN, bytes);
    assert(!request.error);
    const auto constant = request.result.word;
    request = {}; request.self = constant; request.arguments[0].word = 'X';
    BQT_BYTE_ITERATOR_WRITE(&request);
    assert(request.error == EPERM);
    call(BQT_BYTE_ITERATOR_READ, begin);
    assert(!request.error && request.result.word == 'a');
    request = {}; request.self = begin; request.arguments[0] = wide_value(2);
    BQT_BYTE_ITERATOR_ADVANCE(&request);
    assert(!request.error);
    const auto middle = request.result.word;
    discard_value(request.arguments[0]);
    request = {}; request.self = bytes;
    request.arguments[0].word = begin; request.arguments[1].word = middle;
    BQT_BYTE_ITERATOR_ERASE(&request);
    assert(!request.error);
    const auto after = request.result.word;
    assert(*static_cast<QByteArray *>(entry(bytes)->value) == "cd");
    call(BQT_BYTE_ITERATOR_READ, begin);
    assert(request.error == ESTALE);
    call(BQT_BYTE_ITERATOR_READ, after);
    assert(!request.error && request.result.word == 'c');
    request = {}; request.self = after; request.arguments[0].word = 'X';
    BQT_BYTE_ITERATOR_WRITE(&request);
    assert(!request.error && *static_cast<QByteArray *>(entry(bytes)->value) == "Xd");
    call(BQT_BYTE_ITERATOR_READ, after);
    assert(!request.error && request.result.word == 'X');
    request = {}; request.self = after; request.arguments[0] = wide_value(3);
    BQT_BYTE_ITERATOR_ADVANCE(&request);
    assert(request.error == ERANGE);
    discard_value(request.arguments[0]);
    call(destroy_object, bytes);
    assert(request.error == EBUSY);
    release(after); release(middle); release(constant); release(begin); release(bytes);
    std::puts("QT612_NATIVE_BYTE_ITERATORS_OK origin=1 bounds=1 erase=1 mutation_stale=1 mutable_write=1 const_rejected=1 owner_retained=1");
}
#endif
