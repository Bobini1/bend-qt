#ifdef BQT_TEXT_DECODER_APPEND
class NativeInstanceFixture final : public QQuick3DInstancing
{
protected:
    QByteArray getInstanceBuffer(int *count) override { *count = 2; return QByteArray("instances"); }
};

static void text_output_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    const auto decoder = own(&request, new QStringDecoder(QStringConverter::Utf8), BQT_TEXT_DECODER_TYPE);
    auto *first = new QByteArray("\xF0\x9F", 2);
    const auto input = own(&request, first, BQT_GL_BYTE_ARRAY_TYPE);
    request = {}; request.self = decoder; request.arguments[0].word = input;
    BQT_TEXT_DECODER_APPEND(&request);
    assert(!request.error && request.result.size == 0); discard_value(request.result);
    *first = QByteArray("\x98\x80", 2);
    request = {}; request.self = decoder; request.arguments[0].word = input;
    BQT_TEXT_DECODER_APPEND(&request);
    assert(!request.error && request.result.size == 4 && std::memcmp(request.result.text, "\xF0\x9F\x98\x80", 4) == 0);
    discard_value(request.result);
    assert(!get<QStringDecoder>(&request, decoder, BQT_TEXT_DECODER_TYPE)->hasError());
    const auto encoder = own(&request, new QStringEncoder(QStringConverter::Utf8), BQT_TEXT_ENCODER_TYPE);
    const QByteArray word("Gr\xC3\xBC\xC3\x9F" "e");
    request = {}; request.self = encoder;
    request.arguments[0].text = const_cast<char *>(word.constData()); request.arguments[0].size = word.size();
    BQT_TEXT_ENCODER_APPEND(&request);
    assert(!request.error);
    auto *encoded = get<QByteArray>(&request, request.result.word, BQT_GL_BYTE_ARRAY_TYPE);
    assert(encoded && *encoded == word); discard_value(request.result);
    QByteArray stream_source = word + " remaining";
    const auto stream = own(&request, new QTextStream(&stream_source), BQT_TEXT_STREAM_TYPE);
    request = {}; request.self = stream; BQT_TEXT_STREAM_WORD(&request);
    assert(!request.error && request.result.count == 2 && request.result.items[0].word == stream);
    assert(*get<QByteArray>(&request, request.result.items[1].word, BQT_GL_BYTE_ARRAY_TYPE) == word);
    discard_value(request.result);
    request = {}; request.self = stream; BQT_TEXT_STREAM_WORD(&request);
    assert(!request.error && *get<QByteArray>(&request, request.result.items[1].word, BQT_GL_BYTE_ARRAY_TYPE) == "remaining");
    discard_value(request.result);
    request = {}; request.self = stream; BQT_TEXT_STREAM_WORD(&request);
    assert(!request.error && get<QByteArray>(&request, request.result.items[1].word, BQT_GL_BYTE_ARRAY_TYPE)->isEmpty());
    discard_value(request.result);
    assert(get<QTextStream>(&request, stream, BQT_TEXT_STREAM_TYPE)->status() == QTextStream::ReadPastEnd);
    const auto instancer = own(&request, new NativeInstanceFixture, BQT_TEXT_INSTANCER_TYPE);
    request = {}; request.self = instancer; BQT_TEXT_INSTANCE_BUFFER(&request);
    assert(!request.error && request.result.count == 2 && request.result.items[1].word == 2);
    assert(*get<QByteArray>(&request, request.result.items[0].word, BQT_GL_BYTE_ARRAY_TYPE) == "instances");
    discard_value(request.result);
    for (auto id : {decoder, input, encoder, stream, instancer}) {
        request = {}; request.self = id; destroy_object(&request); assert(!request.error);
    }
    std::puts("QT612_NATIVE_TEXT_OUTPUTS_OK split_utf8=1 decoder_extent=1 encoder_extent=1 utf8_word=1 eof_status=1 instance_count=1 cleanup=1");
}
#endif
