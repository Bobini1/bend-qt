#ifdef BQT_READ_INT_ARRAY4
static void fixed_array_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    const std::array<int, 4> expected{-4, 7, 19, 23};
    auto wire = BQT_WRITE_INT_ARRAY4(&request, expected);
    assert(!request.error && wire.count == 4);
    const auto read = BQT_READ_INT_ARRAY4(&request, wire);
    assert(!request.error && read && *read == expected);
    wire.count = 3;
    assert(!BQT_READ_INT_ARRAY4(&request, wire) && request.error == EINVAL);
    wire.count = 4; discard_value(wire);
    request = {};
    auto excess = sequence_value(5);
    assert(!BQT_READ_INT_ARRAY4(&request, excess) && request.error == EINVAL);
    discard_value(excess);
    request = {};
    auto malformed = sequence_value(4);
    malformed.items[2] = string_value(QStringLiteral("wrong scalar"));
    assert(!BQT_READ_INT_ARRAY4(&request, malformed) && request.error == EINVAL);
    discard_value(malformed);
    std::puts("QT612_NATIVE_FIXED_ARRAYS_OK fixed_extent=1 scalar_values=1 short_rejected=1 excess_rejected=1 invalid_element=1");
}
#endif
