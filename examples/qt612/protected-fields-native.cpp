#include <QtWidgets/QApplication>
#include <QtWidgets/QWidgetItem>
#include <QtWidgets/QWidget>
#include <QtGui/QImage>
#include <QtGui/QPainter>
#include <QtGui/QPaintEngine>
#include <QtCore/QStringDecoder>
#include <QtQuick/QSGSimpleTextureNode>
#include <QtQuick/QSGTextureMaterial>
#include <array>
#include <climits>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <cassert>
#include <cstdio>
#include "protected-fields-helpers.h"

int main(int argc,char **argv) {
    QApplication app(argc,argv);
    QImage image(8,8,QImage::Format_ARGB32);
    auto *engine=image.paintEngine();
    assert(engine);
    auto active=BqtProtectedFields_QPaintEngine::access_active(engine);
    assert(unsigned(active)==engine->isActive());
    active=1; assert(engine->isActive()); active=0;
    auto extended=BqtProtectedFields_QPaintEngine::access_extended(engine);
    const auto previousExtended=unsigned(extended);
    extended=0; assert(!engine->isExtended()); extended=1; assert(engine->isExtended()); extended=previousExtended;
    auto selfDestruct=BqtProtectedFields_QPaintEngine::access_selfDestruct(engine);
    const auto previousSelfDestruct=unsigned(selfDestruct);
    selfDestruct=1; assert(unsigned(selfDestruct)==1); selfDestruct=previousSelfDestruct;
    QPainter painter(&image);
    assert(BqtProtectedFields_QPaintDevice::access_painters(static_cast<QPaintDevice *>(&image))==1);
    auto *state=BqtProtectedFields_QPaintEngine::access_state(engine);
    assert(state);
    auto previousFlags=BqtProtectedFields_QPaintEngineState::access_dirtyFlags(state);
    BqtProtectedFields_QPaintEngineState::access_dirtyFlags(state)=QPaintEngine::DirtyPen;
    assert(state->state()==QPaintEngine::DirtyPen);
    BqtProtectedFields_QPaintEngineState::access_dirtyFlags(state)=previousFlags;
    painter.end();
    assert(BqtProtectedFields_QPaintEngine::access_state(engine)==nullptr);
    QSGSimpleTextureNode node;
    auto *material=dynamic_cast<QSGTextureMaterial *>(node.material());
    assert(material);
    BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_filtering(material)=2;
    assert(material->filtering()==QSGTexture::Linear);
    BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_mipmap_filtering(material)=2;
    assert(material->mipmapFiltering()==QSGTexture::Linear);
    BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_horizontal_wrap(material)=1;
    assert(material->horizontalWrapMode()==QSGTexture::ClampToEdge);
    BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_vertical_wrap(material)=1;
    assert(material->verticalWrapMode()==QSGTexture::ClampToEdge);
    BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_anisotropy_level(material)=3;
    assert(unsigned(BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_anisotropy_level(material))==3);
    assert(unsigned(material->anisotropyLevel())==3);
    BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_reserved(material)=7;
    assert(unsigned(BqtProtectedFields_QSGOpaqueTextureMaterial::access_m_reserved(material))==7);
    assert(material->filtering()==QSGTexture::Linear && material->verticalWrapMode()==QSGTexture::ClampToEdge);
    QStringDecoder decoder(QStringConverter::Utf8);
    auto &converterState=BqtProtectedFields_QStringConverter::access_state(&decoder);
    converterState.invalidChars=2; assert(decoder.hasError());
    converterState.invalidChars=0; assert(!decoder.hasError());
    QWidget first,second;
    QWidgetItem item(&first);
    assert(BqtProtectedFields_QWidgetItem::access_wid(&item)==&first);
    BqtProtectedFields_QWidgetItem::access_wid(&item)=&second;
    assert(item.widget()==&second);
    BqtProtectedFields_QWidgetItem::access_wid(&item)=&first;
    BqtProtectedFields_QLayoutItem::access_align(static_cast<QLayoutItem *>(&item))=Qt::AlignRight|Qt::AlignTop;
    assert(item.alignment()==(Qt::AlignRight|Qt::AlignTop));
    std::puts("PROTECTED_FIELDS_NATIVE_OK foreign=1 bitfields=9 addressable=1 member_view=1");
}
