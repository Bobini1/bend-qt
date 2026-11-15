#ifdef BQT_STREAM_ALLOCATED_BYTES
static void allocated_byte_checks()
{
    using namespace bendqt;
    QByteArray encoded;
    {
        QDataStream writer(&encoded, QIODevice::WriteOnly);
        writer.writeBytes("A\0B", 3);
        writer << "C string";
        writer.writeBytes(nullptr, 0);
        writer << quint32(4);
        writer.writeRawData("xx", 2); // Truncated payload must preserve native status.
    }
    BqtRequest request{};
    auto *stream = new QDataStream(encoded);
    auto id = own(&request, stream, BQT_DATA_STREAM_TYPE);
    assert(id && !request.error);
    auto data = [](BqtRequest &r) -> QByteArray {
        assert(!r.error && r.result.items && r.result.count >= 2);
        auto *e = entry(r.result.items[1].word);
        assert(e && e->owned && r.result.items[1].owned_handle);
        return *static_cast<QByteArray *>(e->value);
    };
    request = {};
    request.self = id;
    BQT_STREAM_ALLOCATED_BYTES(&request);
    assert(data(request) == QByteArray("A\0B", 3));
    assert(wide_bits(request.result.items[2]) == 3 && stream->status() == QDataStream::Ok);
    assert(request.result.items[0].word == id && !request.result.items[0].owned_handle);
    discard_value(request.result);
    request = {};
    request.self = id;
    BQT_STREAM_ALLOCATED_STRING(&request);
    assert(data(request) == QByteArray("C string\0", 9));
    discard_value(request.result);
    request = {};
    request.self = id;
    BQT_STREAM_ALLOCATED_BYTES(&request);
    assert(data(request).isEmpty() && wide_bits(request.result.items[2]) == 0);
    discard_value(request.result);
    request = {};
    request.self = id;
    BQT_STREAM_ALLOCATED_BYTES(&request);
    assert(data(request).isEmpty() && stream->status() == QDataStream::ReadPastEnd);
    discard_value(request.result);
    request = {};
    request.self = id;
    destroy_object(&request);
    assert(!request.error);

    // Test the extended 64-bit length marker without requiring huge allocation.
    encoded.clear();
    { QDataStream writer(&encoded, QIODevice::WriteOnly); writer << quint32(0xfffffffe) << quint64(3); writer.writeRawData("X\0Y", 3); }
    request = {};
    stream = new QDataStream(encoded);
    id = own(&request, stream, BQT_DATA_STREAM_TYPE);
    request = {};
    request.self = id;
    BQT_STREAM_ALLOCATED_BYTES(&request);
    assert(data(request) == QByteArray("X\0Y", 3) && stream->status() == QDataStream::Ok);
    discard_value(request.result);
    request = {};
    request.self = id;
    destroy_object(&request);
    assert(!request.error);
    std::puts("QT612_NATIVE_ALLOCATED_BYTES_OK embedded_nul=1 stored_terminator=1 exact_length=1 empty=1 truncated_status=1 extended_length=1 owning_output=1");
}
#endif
