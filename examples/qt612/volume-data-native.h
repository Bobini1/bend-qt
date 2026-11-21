#ifdef BQT_VOLUME_SET
static void volume_data_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    auto *value = new QCustom3DVolume;
    value->setTextureDimensions(2, 1, 2);
    const auto volume = own(&request, value, BQT_VOLUME_TYPE);
    auto release = [&](uint32_t id) {
        request = {}; request.self = id; destroy_object(&request); assert(!request.error);
    };
    auto bytes = [](size_t count, uint32_t byte) {
        auto result = sequence_value(count);
        for (size_t i = 0; i < count; ++i) result.items[i].word = byte;
        return result;
    };
    request = {}; request.self = volume; request.arguments[0] = bytes(15, 3);
    BQT_VOLUME_SET(&request);
    assert(request.error == ERANGE && !value->textureData());
    discard_value(request.arguments[0]);
    request = {}; request.self = volume; request.arguments[0] = bytes(16, 3);
    BQT_VOLUME_SET(&request);
    assert(!request.error && value->textureData()->size() == 16);
    discard_value(request.arguments[0]);
    request = {}; request.self = volume;
    BQT_VOLUME_GET(&request);
    assert(!request.error && request.result.count == 16 && request.result.items[0].word == 3);
    auto snapshot = request.result;
    request = {};
    const auto slice = own(&request, new QByteArray(8, char(9)), BQT_GL_BYTE_ARRAY_TYPE);
    request = {}; request.self = volume;
    request.arguments[0].word = Qt::ZAxis; request.arguments[1].word = 1; request.arguments[2].word = slice;
    BQT_VOLUME_SLICE(&request);
    assert(!request.error && value->textureData()->at(8) == 9 && snapshot.items[8].word == 3);
    request = {}; request.self = volume;
    request.arguments[0].word = Qt::ZAxis; request.arguments[1].word = 2; request.arguments[2].word = slice;
    BQT_VOLUME_SLICE(&request);
    assert(request.error == ERANGE);
    discard_value(snapshot); release(slice);
    request = {};
    auto *first = new QImage(2, 1, QImage::Format_ARGB32); first->fill(qRgb(1, 2, 3));
    auto *second = new QImage(2, 1, QImage::Format_ARGB32); second->fill(qRgb(4, 5, 6));
    const auto one = own(&request, first, BQT_VOLUME_IMAGE_TYPE);
    const auto two = own(&request, second, BQT_VOLUME_IMAGE_TYPE);
    request = {}; request.self = volume;
    request.arguments[0] = sequence_value(2);
    request.arguments[0].items[0].word = one; request.arguments[0].items[1].word = two;
    BQT_VOLUME_IMAGES(&request);
    assert(!request.error && request.result.count == 16 && request.result.items[0].word == 3 && request.result.items[8].word == 6);
    assert(value->textureWidth() == 2 && value->textureDepth() == 2);
    discard_value(request.arguments[0]); discard_value(request.result);
    *second = QImage(1, 1, QImage::Format_ARGB32);
    request = {}; request.self = volume;
    request.arguments[0] = sequence_value(2);
    request.arguments[0].items[0].word = one; request.arguments[0].items[1].word = two;
    BQT_VOLUME_IMAGES(&request);
    assert(request.error == EINVAL && value->textureWidth() == 2);
    discard_value(request.arguments[0]);
    release(one); release(two); release(volume);
    std::puts("QT612_NATIVE_VOLUME_DATA_OK owning_bytes=1 snapshots=1 slice_extent=1 image_planes=1 dimensions_rejected=1 cleanup=1");
}
#endif
