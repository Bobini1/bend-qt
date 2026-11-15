#ifdef BQT_INTEROP_LIBRARY_RESOLVE
static void native_interop_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    const auto library = own(&request, new QLibrary(QStringLiteral("libc.so.6")), BQT_INTEROP_QLIBRARY_TYPE);
    assert(library && !request.error);
    request = {};
    request.self = library;
    request.arguments[0] = string_value(QStringLiteral("abs"));
    BQT_INTEROP_LIBRARY_RESOLVE(&request);
    assert(!request.error);
    discard_value(request.arguments[0]);
    auto function = request.result.word;
    request = {};
    request.arguments[0].word = function;
    BQT_INTEROP_FUNCTION_ADDRESS(&request);
    assert(!request.error);
    const auto address = wide_bits(request.result);
    discard_value(request.result);
    assert(address && reinterpret_cast<int (*)(int)>(uintptr_t(address))(-42) == 42);
    request = {};
    request.self = library;
    BQT_INTEROP_LIBRARY_UNLOAD(&request);
    assert(request.error == EBUSY);
    assert(static_cast<QLibrary *>(entry(library)->value)->isLoaded());
    assert(reinterpret_cast<int (*)(int)>(uintptr_t(address))(-42) == 42);
    request = {};
    request.self = library;
    destroy_object(&request);
    assert(request.error == EBUSY);
    request = {};
    request.self = function;
    destroy_object(&request);
    assert(!request.error);
    request = {};
    request.self = library;
    BQT_INTEROP_LIBRARY_UNLOAD(&request);
    assert(!request.error);
    request = {};
    request.self = library;
    request.arguments[0] = string_value(QStringLiteral("bendqt_no_such_symbol"));
    BQT_INTEROP_LIBRARY_RESOLVE(&request);
    assert(!request.error);
    discard_value(request.arguments[0]);
    function = request.result.word;
    request = {};
    request.arguments[0].word = function;
    BQT_INTEROP_FUNCTION_NULL(&request);
    assert(!request.error && request.result.word);
    request = {};
    request.self = function;
    destroy_object(&request);
    request = {};
    request.self = library;
    destroy_object(&request);
    assert(!request.error);

    // Public, disposable test key. No trust or TLS operation uses this fixture.
    const QByteArray key_pem = R"PEM(-----BEGIN EC PRIVATE KEY-----
MHcCAQEEICy9pNJaBtEks1M4e4ZMztjTqGwKhqXk5rwKchrKxjWgoAoGCCqGSM49
AwEHoUQDQgAEmqmk76diJLWN/A5g0Rt4PPFm0Gr9QR+EjlJ1zqvny+hmRTNzIGZV
e0wnNap3ig+wAWI26Z8P6Ww04gcrA63Ikw==
-----END EC PRIVATE KEY-----
)PEM";
    QSslKey original(key_pem, QSsl::Ec, QSsl::Pem, QSsl::PrivateKey);
    assert(!original.isNull());
    const auto original_handle = original.handle();
    request = {};
    const auto key = own(&request, new QSslKey(original), BQT_INTEROP_QSSLKEY_TYPE);
    request = {};
    request.self = key;
    BQT_INTEROP_KEY_HANDLE(&request);
    assert(!request.error);
    const auto capability = request.result.word;
    original.clear();
    static_cast<QSslKey *>(entry(key)->value)->clear();
    request = {};
    request.self = key;
    destroy_object(&request);
    assert(!request.error);
    request = {};
    request.arguments[0].word = capability;
    BQT_INTEROP_KEY_ADDRESS(&request);
    assert(!request.error && wide_bits(request.result) == reinterpret_cast<uintptr_t>(original_handle));
    discard_value(request.result);
    request = {};
    request.arguments[0].word = capability;
    request.arguments[1].word = QSsl::PublicKey;
    BQT_INTEROP_KEY_COPY(&request);
    assert(request.error == EINVAL);
    request = {};
    request.arguments[0].word = capability;
    request.arguments[1].word = QSsl::PrivateKey;
    BQT_INTEROP_KEY_COPY(&request);
    assert(!request.error);
    const auto copied = request.result.word;
    request = {};
    request.self = capability;
    destroy_object(&request);
    assert(!request.error);
    auto *copy = static_cast<QSslKey *>(entry(copied)->value);
    assert(!copy->isNull() && copy->handle() == original_handle && !copy->toPem().isEmpty());
    request = {};
    request.self = copied;
    destroy_object(&request);
    assert(!request.error);
    const QByteArray certificate_pem = R"PEM(-----BEGIN CERTIFICATE-----
MIIBkTCCATegAwIBAgIUcB7hcrKuJ7oo3H3+5Yk7wCmx4BowCgYIKoZIzj0EAwIw
HjEcMBoGA1UEAwwTQmVuZFF0TmF0aXZlRml4dHVyZTAeFw0yNjExMDkxMjI0MDda
Fw0zNjExMDYxMjI0MDdaMB4xHDAaBgNVBAMME0JlbmRRdE5hdGl2ZUZpeHR1cmUw
WTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAASaqaTvp2IktY38DmDRG3g88WbQav1B
H4SOUnXOq+fL6GZFM3MgZlV7TCc1qneKD7ABYjbpnw/pbDTiBysDrciTo1MwUTAd
BgNVHQ4EFgQUWu+1kt21ZPSKeAzRz79nBZV7AWkwHwYDVR0jBBgwFoAUWu+1kt21
ZPSKeAzRz79nBZV7AWkwDwYDVR0TAQH/BAUwAwEB/zAKBggqhkjOPQQDAgNIADBF
AiEAhSa6L1ga/0qj1v330MKUD7V7Ms7zAJU6bcENa6E9nOYCIF64isbdLV5o/tT/
MNEp5Ic1ADaVlHiOMFi70UMYb+XZ
-----END CERTIFICATE-----
)PEM";
    auto *certificate = new QSslCertificate(certificate_pem, QSsl::Pem);
    assert(!certificate->isNull());
    const auto certificate_handle = certificate->handle();
    request = {};
    const auto certificate_id = own(&request, certificate, BQT_INTEROP_QSSLCERTIFICATE_TYPE);
    request = {};
    request.self = certificate_id;
    BQT_INTEROP_CERT_HANDLE(&request);
    assert(!request.error);
    const auto certificate_capability = request.result.word;
    certificate->clear();
    request = {};
    request.self = certificate_id;
    destroy_object(&request);
    assert(!request.error);
    request = {};
    request.arguments[0].word = certificate_capability;
    BQT_INTEROP_CERT_ADDRESS(&request);
    assert(!request.error && wide_bits(request.result) == reinterpret_cast<uintptr_t>(certificate_handle));
    discard_value(request.result);
    request = {};
    request.self = certificate_capability;
    destroy_object(&request);
    assert(!request.error);
    std::puts("QT612_NATIVE_INTEROP_OK function_call=1 library_pin=1 null_function=1 key_snapshot=1 certificate_snapshot=1 keytype_rejected=1 key_copy=1 release_order=1");
}
#endif
