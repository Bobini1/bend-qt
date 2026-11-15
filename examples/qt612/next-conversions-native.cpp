#include <cassert>
#include <cstdio>
#include <cmath>
#include BQT_GENERATED_WRAPPERS
#include "test-host-native.h"

using namespace bendqt;
using Operation = bool (*)(BqtRequest *);
static void checked(const BqtRequest &r) {
    if (r.error) std::fprintf(stderr,"CHECK %d %s\n",r.error,r.message?r.message:"");
    assert(!r.error);
}
static BqtValue word(uint32_t n) { BqtValue v{};v.word=n;return v; }
static BqtValue list(std::initializer_list<BqtValue> values) {
    auto result=sequence_value(values.size());size_t i=0;
    for (auto value:values) result.items[i++]=value;
    return result;
}
static BqtValue zeroes(size_t n) { return sequence_value(n); }
static BqtValue text(const char *value) { return string_value(QString::fromUtf8(value)); }
static BqtRequest call(Operation fn,uint32_t self,std::initializer_list<BqtValue> inputs={}) {
    BqtRequest r{};r.self=self;size_t n=0;
    for(auto value:inputs)r.arguments[n++]=value;
    fn(&r);for(size_t i=0;i<n;++i)discard_value(r.arguments[i]);return r;
}
template<class T> static uint32_t put(T *value,uint16_t type) {
    BqtRequest r{};auto id=own(&r,value,type);checked(r);return id;
}
template<class T> static T *value(uint32_t id) { assert(entry(id));return static_cast<T *>(entry(id)->value); }
static void release(uint32_t id) {
    BqtRequest r{};r.self=id;release_object(&r);checked(r);collect_pending();
}
static void strings_and_bytes() {
    auto bytes=put(new QByteArray("x\0y",3),TYPE_QByteArray);
    auto buffer=put(new QBuffer,TYPE_QBuffer);
    auto r=call(OP_BUFFER_SET,buffer,{word(bytes),wide_value(3)});checked(r);
    assert(value<QBuffer>(buffer)->data()==QByteArray("x\0y",3));
    r=call(OP_BUFFER_SET,buffer,{word(bytes),wide_value(4)});assert(r.error==ERANGE);
    auto target=put(new QByteArray,TYPE_QByteArray);
    for(auto op:{OP_APPEND,OP_PREPEND,OP_PUSH_BACK,OP_PUSH_FRONT}) {
        r=call(op,target,{text("a")});checked(r);discard_value(r.result);
    }
    assert(*value<QByteArray>(target)=="aaaa");
    auto bad=string_value(QString(QChar('x'))+QChar(0)+QChar('y'));
    r=call(OP_APPEND,target,{bad});assert(r.error==EINVAL);assert(value<QByteArray>(target)->size()==4);
    auto reader=put(new QCborStreamReader(QByteArray::fromHex("43004142")),TYPE_QCborStreamReader);
    value<QByteArray>(bytes)->resize(3);
    r=call(OP_CBOR_CHUNK,reader,{word(bytes),wide_value(3)});checked(r);
    assert(r.result.count==2 && wide_bits(r.result.items[0])==3);
    assert(*value<QByteArray>(bytes)==QByteArray("\0AB",3));discard_value(r.result);
    QUdpSocket receiver;assert(receiver.bind(QHostAddress::LocalHost,0));
    auto sender=put(new QUdpSocket,TYPE_QUdpSocket);
    auto address=put(new QHostAddress(QHostAddress::LocalHost),TYPE_QHostAddress);
    r=call(OP_UDP_SEND,sender,{word(bytes),wide_value(3),word(address),word(receiver.localPort())});checked(r);
    assert(wide_bits(r.result)==3);assert(receiver.waitForReadyRead(1000));
    assert(receiver.readDatagram(nullptr,0)==0); // The datagram is consumed without reading outside storage.
    r=call(OP_UDP_SEND,sender,{word(bytes),wide_value(4),word(address),word(receiver.localPort())});assert(r.error==ERANGE);
    for(auto id:{sender,address,reader,target,buffer,bytes})release(id);
}
static void scalar_outputs() {
    auto locale=put(new QLocale(QLocale::c()),TYPE_QLocale);
    for(auto op:{OP_TOINT,OP_TOLONG,OP_TOLONGLONG,OP_TOSHORT,OP_TOUINT,OP_TOULONGLONG,OP_TOUSHORT}) {
        auto r=call(op,locale,{text("42")});checked(r);assert(r.result.count==2 && r.result.items[0].word==42 && r.result.items[1].word);discard_value(r.result);
        r=call(op,locale,{text("bad")});checked(r);assert(!r.result.items[1].word);discard_value(r.result);
    }
    for(auto op:{OP_TODOUBLE,OP_TOFLOAT}) {
        auto r=call(op,locale,{text("1.5")});checked(r);assert(real_value(r.result.items[0])==1.5 && r.result.items[1].word);discard_value(r.result);
    }
    auto rotation=put(new QQuaternion(QQuaternion::fromAxisAndAngle(0,0,1,90)),TYPE_QQuaternion);
    auto r=call(OP_QUATERNION_OUTPUTS,rotation);checked(r);assert(r.result.count==4);
    assert(std::abs(real_value(r.result.items[2])-1)<1e-5 && std::abs(real_value(r.result.items[3])-90)<1e-4);discard_value(r.result);
    auto transform=put(new QTransform(QTransform::fromTranslate(7,11)),TYPE_QTransform);
    r=call(OP_TRANSFORM,transform,{word(2),word(3)});checked(r);assert(r.result.items[0].word==9 && r.result.items[1].word==14);discard_value(r.result);
    auto layout=put(new QTextLayout("abc"),TYPE_QTextLayout);value<QTextLayout>(layout)->beginLayout();
    auto line=put(new QTextLine(value<QTextLayout>(layout)->createLine()),TYPE_QTextLine);value<QTextLine>(line)->setLineWidth(200);
    value<QTextLayout>(layout)->endLayout();
    r=call(OP_LINE_CURSOR,line,{word(100),word(QTextLine::Leading)});checked(r);
    assert(r.result.count==2 && r.result.items[1].word==3);discard_value(r.result);
    r=call(OP_THREAD_ID,0);checked(r);assert(wide_bits(r.result)==reinterpret_cast<quintptr>(QThread::currentThreadId()));
    for(auto id:{line,layout,transform,rotation,locale})release(id);
}
static void arrays_and_views() {
    auto ipv6=zeroes(16);ipv6.items[15].word=1;
    auto r=call(OP_IPV6_NEW,0,{ipv6});checked(r);auto address=r.result.word;
    assert(value<QHostAddress>(address)->toString()=="::1");
    r=call(OP_IPV6_SET,address,{zeroes(15)});assert(r.error==EINVAL);
    ipv6=zeroes(16);ipv6.items[0].word=256;r=call(OP_IPV6_SET,address,{ipv6});assert(r.error==ERANGE);
    r=call(OP_POLYGON,0,{word(2),list({word(1),word(2),word(3),word(4)})});checked(r);
    assert(value<QPolygon>(r.result.word)->at(1)==QPoint(3,4));discard_value(r.result);
    r=call(OP_POLYGON,0,{word(3),list({word(1),word(2)})});assert(r.error==ERANGE);
    auto random=put(new QRandomGenerator(123),TYPE_QRandomGenerator);
    r=call(OP_RANDOM_RANGE,random,{zeroes(3),wide_value(3)});checked(r);assert(r.result.count==1 && r.result.items[0].count==3);discard_value(r.result);
    r=call(OP_RANDOM_RANGE,random,{zeroes(0),wide_value(0)});checked(r);assert(r.result.items[0].count==0);discard_value(r.result);
    r=call(OP_RANDOM_RANGE,random,{zeroes(1),wide_value(2)});assert(r.error==ERANGE);
    auto bits=put(new QBitArray(9,true),TYPE_QBitArray);
    r=call(OP_BITS,bits);checked(r);auto view=r.result.word;
    auto *memory=value<MemoryView>(view);assert(memory->readonly && memory->size==2 && memory->observe(&r,*memory,false));
    value<QBitArray>(bits)->resize(200);r={};assert(!memory->observe(&r,*memory,false) && r.error==ESTALE);release(view);
    auto matrix=put(new QMatrix4x4,TYPE_QMatrix4x4);
    for(auto op:{OP_MATRIX_CONST}) {
        r=call(op,matrix);checked(r);auto *span=value<MemoryView>(r.result.word);
        assert(span->readonly && span->size==16 && span->observe(&r,*span,false));
        assert(static_cast<const float *>(span->address)[0]==1);discard_value(r.result);
    }
    auto small=put(new QMatrix3x3,TYPE_QMatrix3x3);
    r=call(OP_MATRIX_SMALL_CONST,small);checked(r);
    assert(value<MemoryView>(r.result.word)->size==9 && value<MemoryView>(r.result.word)->readonly);discard_value(r.result);release(small);
    for(auto id:{matrix,bits,random,address})release(id);
}
static void directory_and_image() {
    QTemporaryDir temp;assert(temp.isValid());auto dir=put(new QDir(temp.path()),TYPE_QDir);
    const uint32_t mode=QFileDevice::ReadOwner|QFileDevice::WriteOwner|QFileDevice::ExeOwner;
    auto r=call(OP_MKDIR,dir,{text("private"),list({word(mode)})});checked(r);assert(r.result.word);
    assert(!(QFileInfo(temp.path()+"/private").permissions() & (QFileDevice::ReadOther|QFileDevice::WriteOther|QFileDevice::ExeOther)));
    r=call(OP_MKPATH,dir,{text("a/b/c"),zeroes(0)});checked(r);assert(r.result.word && QDir(temp.path()+"/a/b/c").exists());
    QImage image(3,2,QImage::Format_ARGB32);image.fill(Qt::red);QByteArray png;QBuffer buffer(&png);assert(buffer.open(QIODevice::WriteOnly));assert(image.save(&buffer,"PNG"));buffer.close();assert(buffer.open(QIODevice::ReadOnly));
    auto reader=put(new QImageReader(&buffer,"PNG"),TYPE_QImageReader);
    r=call(OP_IMAGE_READ,reader);checked(r);assert(r.result.items[0].word);
    auto *decoded=value<QImage>(r.result.items[1].word);assert(decoded->size()==QSize(3,2) && decoded->pixelColor(0,0)==Qt::red);discard_value(r.result);
    release(reader);release(dir);
}
static void font_and_snapshot() {
    auto native=QRawFont::fromFont(QFont("DejaVu Sans",12));assert(native.isValid());auto font=put(new QRawFont(native),TYPE_QRawFont);
    auto r=call(OP_FONT_GLYPHS,font,{list({word('A'),word('B')}),word(2),zeroes(2),word(2)});checked(r);
    assert(r.result.count==3 && r.result.items[0].word && r.result.items[1].count==2 && r.result.items[2].word==2);
    uint32_t a=r.result.items[1].items[0].word,b=r.result.items[1].items[1].word;assert(a && b);discard_value(r.result);
    r=call(OP_FONT_GLYPHS,font,{list({word('A'),word('B')}),word(2),zeroes(0),word(0)});checked(r);
    assert(!r.result.items[0].word && r.result.items[2].word==2);discard_value(r.result);
    auto point=put(new QPointF,TYPE_QPointF);
    r=call(OP_FONT_ADVANCES,font,{list({word(a),word(b)}),list({word(point),word(point)}),word(2)});checked(r);
    assert(r.result.items[0].word && value<QPointF>(r.result.items[1].items[0].word)->x()>0);discard_value(r.result);
    r=call(OP_FONT_ADVANCES_FLAGS,font,{list({word(a)}),list({word(point)}),word(1),word(QRawFont::KernedAdvances)});checked(r);assert(r.result.items[0].word);discard_value(r.result);
    r=call(OP_FONT_ADVANCES,font,{list({word(a)}),list({word(point)}),word(2)});assert(r.error==ERANGE);
    auto run=put(new QGlyphRun,TYPE_QGlyphRun);value<QPointF>(point)->setX(12);
    r=call(OP_GLYPHS_SNAPSHOT,run,{list({word(a),word(b)}),list({word(point),word(point)}),word(2)});checked(r);
    QGlyphRun copy(*value<QGlyphRun>(run));value<QPointF>(point)->setX(100);release(run);release(point);
    assert(copy.glyphIndexes()==QList<quint32>({a,b}) && copy.positions().first().x()==12);
    run=put(new QGlyphRun(copy),TYPE_QGlyphRun);
    r=call(OP_GLYPHS_SNAPSHOT,run,{zeroes(0),zeroes(0),word(uint32_t(-1))});assert(r.error==ERANGE);
    assert(value<QGlyphRun>(run)->glyphIndexes()==copy.glyphIndexes());release(run);release(font);
}
static void boundary_storage() {
    auto r=call(OP_BOUNDARY_RAW,0,{word(QTextBoundaryFinder::Grapheme),text("a\xF0\x9F\x98\x80z"),wide_value(3),wide_value(16)});
    checked(r);auto finder=r.result.word;
    auto *native=value<QTextBoundaryFinder>(finder);
    assert(native->isValid() && native->toNextBoundary()==1 && native->toNextBoundary()==3 && native->toNextBoundary()==-1);
    r=call(OP_BOUNDARY_COPY,0,{word(finder)});checked(r);auto copy=r.result.word;
    release(finder); // Both input wire text and the original finder are gone.
    native=value<QTextBoundaryFinder>(copy);native->toStart();assert(native->toNextBoundary()==1 && native->toNextBoundary()==3);
    auto other=put(new QTextBoundaryFinder(QTextBoundaryFinder::Word,QStringLiteral("other")),TYPE_QTextBoundaryFinder);
    r=call(OP_BOUNDARY_ASSIGN,other,{word(copy)});checked(r);discard_value(r.result);release(copy);
    native=value<QTextBoundaryFinder>(other);native->toStart();assert(native->toNextBoundary()==1 && native->toNextBoundary()==3);
    auto swapped=put(new QTextBoundaryFinder,TYPE_QTextBoundaryFinder);
    r=call(OP_BOUNDARY_SWAP,other,{word(swapped)});checked(r);release(other);
    native=value<QTextBoundaryFinder>(swapped);native->toStart();assert(native->toNextBoundary()==1 && native->toNextBoundary()==3);release(swapped);
    for(auto length:{uint64_t(-1),uint64_t(2)}) {
        r=call(OP_BOUNDARY_RAW,0,{word(QTextBoundaryFinder::Word),text("a"),wide_value(length),wide_value(0)});assert(r.error==ERANGE);
    }
    r=call(OP_BOUNDARY_RAW,0,{word(QTextBoundaryFinder::Word),text(""),wide_value(0),wide_value(0)});checked(r);discard_value(r.result);
    r=call(OP_BOUNDARY_RAW,0,{word(QTextBoundaryFinder::Word),text("a"),wide_value(1),wide_value(UINT64_MAX)});assert(r.error==EOVERFLOW);
}
static void gl_outputs() {
    QSurfaceFormat format;format.setVersion(3,3);format.setProfile(QSurfaceFormat::CoreProfile);
    QOpenGLContext context;context.setFormat(format);assert(context.create());
    QOffscreenSurface surface;surface.setFormat(context.format());surface.create();assert(surface.isValid());assert(context.makeCurrent(&surface));
    auto texture=put(new QOpenGLTexture(QOpenGLTexture::Target2D),TYPE_QOpenGLTexture);assert(value<QOpenGLTexture>(texture)->create());
    value<QOpenGLTexture>(texture)->setBorderColor(0.25f,0.5f,0.75f,1.0f);
    auto r=call(OP_BORDER_FLOAT,texture,{list({real_bits(0),real_bits(0),real_bits(0),real_bits(0)})});checked(r);
    assert(r.result.count==1 && std::abs(real_value(r.result.items[0].items[1])-0.5)<1e-5);discard_value(r.result);
    value<QOpenGLTexture>(texture)->setBorderColor(1,2,3,4);
    r=call(OP_BORDER_INT,texture,{zeroes(4)});checked(r);assert(r.result.items[0].items[2].word==3);discard_value(r.result);
    value<QOpenGLTexture>(texture)->setBorderColor(5u,6u,7u,8u);
    r=call(OP_BORDER_UINT,texture,{zeroes(4)});checked(r);assert(r.result.items[0].items[3].word==8);discard_value(r.result);
    r=call(OP_BORDER_INT,texture,{zeroes(3)});assert(r.error==EINVAL);release(texture);context.doneCurrent();
}
int main(int argc,char **argv) {
    test_host_start(argc,argv);
    strings_and_bytes();scalar_outputs();arrays_and_views();directory_and_image();font_and_snapshot();boundary_storage();gl_outputs();
    collect_pending();size_t live=0,edges=0;for(const auto &e:entries)live+=e.value!=nullptr;for(const auto &e:retentions)edges+=e.owner!=0;
    std::printf("REMAINING objects=%zu retentions=%zu\n",live,edges);assert(!live && !edges);
    assert(bqt_abi_stop()==0);
    std::puts("QT612_NEXT_CONVERSIONS_NATIVE_OK");
}
