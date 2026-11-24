/*
 * ogc/gx.h - subset of the GameCube/Wii GX API used by GTS, emulated with SDL2
 * (see src/gx_sdl.c). Only immediate-mode 2D drawing is supported: the vertex
 * stream is recorded per primitive, sorted by depth at the end of the frame and
 * rasterised with SDL_RenderGeometry.
 */
#ifndef GTS_COMPAT_GX_H
#define GTS_COMPAT_GX_H

#include "ogc_compat.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct { u8 r, g, b, a; } GXColor;

typedef struct {
    void *sdl_texture;   /* SDL_Texture* */
    u16 width, height;
} GXTexObj;

typedef struct { u8 dummy; } GXFifoObj;

typedef struct _gx_rmodeobj {
    u32 viTVMode;
    u16 fbWidth, efbHeight, xfbHeight;
    u16 viXOrigin, viYOrigin, viWidth, viHeight;
    u32 xfbMode;
    u8 field_rendering, aa;
    u8 sample_pattern[12][2];
    u8 vfilter[7];
} GXRModeObj;

typedef f32 Mtx[3][4];
typedef f32 Mtx44[4][4];
typedef struct { f32 x, y, z; } guVector;

/* booleans / misc */
#define GX_FALSE 0
#define GX_TRUE 1
#define GX_DISABLE 0
#define GX_ENABLE 1
#define GX_NONE 0
#define GX_DIRECT 1
#define GX_INDEX8 2
#define GX_INDEX16 3

/* primitives (same values as libogc) */
#define GX_POINTS 0xB8
#define GX_LINES 0xA8
#define GX_LINESTRIP 0xB0
#define GX_TRIANGLES 0x90
#define GX_TRIANGLESTRIP 0x98
#define GX_TRIANGLEFAN 0xA0
#define GX_QUADS 0x80

/* vertex formats / attributes */
#define GX_VTXFMT0 0
#define GX_VTXFMT1 1
#define GX_VTXFMT2 2
#define GX_VA_POS 9
#define GX_VA_CLR0 11
#define GX_VA_TEX0 13
#define GX_POS_XY 0
#define GX_POS_XYZ 1
#define GX_CLR_RGBA 1
#define GX_TEX_ST 1
#define GX_S16 3
#define GX_F32 4
#define GX_RGBA8 5

/* TEV */
#define GX_TEVSTAGE0 0
#define GX_TEVSTAGE1 1
#define GX_MODULATE 0
#define GX_DECAL 1
#define GX_BLEND 2
#define GX_REPLACE 3
#define GX_PASSCLR 4
#define GX_TEXCOORD0 0
#define GX_TEXCOORDNULL 0xff
#define GX_TEXMAP0 0
#define GX_TEXMAP1 1
#define GX_TEXMAP2 2
#define GX_TEXMAP3 3
#define GX_TEXMAP4 4
#define GX_TEXMAP5 5
#define GX_TEXMAP6 6
#define GX_TEXMAP7 7
#define GX_MAX_TEXMAP 8
#define GX_TEXMAP_NULL 0xff
#define GX_COLOR0A0 4

/* misc state (accepted, mostly ignored) */
#define GX_PNMTX0 0
#define GX_ORTHOGRAPHIC 1
#define GX_PERSPECTIVE 0
#define GX_CULL_NONE 0
#define GX_BM_NONE 0
#define GX_BM_BLEND 1
#define GX_BL_SRCALPHA 4
#define GX_BL_INVSRCALPHA 5
#define GX_LO_CLEAR 0
#define GX_TO_ZERO 0
#define GX_PF_RGB8_Z24 0
#define GX_ZC_LINEAR 0
#define GX_MAX_Z24 0x00ffffff
#define GX_SRC_VTX 1
#define GX_DF_NONE 0
#define GX_AF_NONE 2
#define GX_FIFO_HIWATERMARK (16 * 1024)

GXFifoObj *GX_Init(void *base, u32 size);
void GX_InitFifoLimits(GXFifoObj *fifo, u32 hiwatermark, u32 lowatermark);
u8 GX_GetFifoWrap(GXFifoObj *fifo);
void GX_SetCopyClear(GXColor color, u32 zvalue);
f32 GX_GetYScaleFactor(u16 efbHeight, u16 xfbHeight);
u32 GX_SetDispCopyYScale(f32 yscale);
void GX_SetScissor(u32 xOrigin, u32 yOrigin, u32 wd, u32 ht);
void GX_SetScissorBoxOffset(s32 xoffset, s32 yoffset);
void GX_SetDispCopySrc(u16 left, u16 top, u16 wd, u16 ht);
void GX_SetDispCopyDst(u16 wd, u16 ht);
void GX_SetPixelFmt(u8 pix_fmt, u8 z_fmt);
void GX_SetCopyFilter(u8 aa, u8 sample_pattern[12][2], u8 vf, u8 *vfilter);
void GX_SetFieldMode(u8 field_mode, u8 half_aspect_ratio);
void GX_SetCullMode(u8 mode);
void GX_ClearVtxDesc(void);
void GX_SetVtxDesc(u8 attr, u8 type);
void GX_SetVtxAttrFmt(u8 vtxfmt, u32 vtxattr, u32 comptype, u32 compsize, u32 frac);
void GX_SetNumChans(u8 num);
void GX_SetChanCtrl(s32 channel, u8 enable, u8 ambsrc, u8 matsrc, u8 litmask, u8 diff_fn, u8 attn_fn);
void GX_SetNumTexGens(u32 nr);
void GX_SetTexCoordScaleManually(u8 texcoord, u8 enable, u16 ss, u16 ts);
void GX_SetNumTevStages(u8 num);
void GX_SetTevOrder(u8 tevstage, u8 texcoord, u32 texmap, u8 color);
void GX_SetTevOp(u8 tevstage, u8 mode);
void GX_SetTevDirect(u8 tevstage);
void GX_InvVtxCache(void);
void GX_InvalidateTexAll(void);
void GX_LoadTexObj(GXTexObj *obj, u8 mapid);
u16 GX_GetTexObjWidth(GXTexObj *obj);
u16 GX_GetTexObjHeight(GXTexObj *obj);
void GX_SetBlendMode(u8 type, u8 src_fact, u8 dst_fact, u8 op);
void GX_SetAlphaUpdate(u8 enable);
void GX_SetColorUpdate(u8 enable);
void GX_LoadProjectionMtx(Mtx44 mt, u8 type);
void GX_LoadPosMtxImm(Mtx mt, u32 pnidx);
void GX_SetLineWidth(u8 width, u8 fmt);
void GX_SetPointSize(u8 width, u8 fmt);
void GX_CopyDisp(void *dest, u8 clear);
void GX_DrawDone(void);
void GX_Flush(void);
u32 GX_GetGPStatus(u8 *overhi, u8 *underlow, u8 *readIdle, u8 *cmdIdle, u8 *brkpt);

void GX_Begin(u8 primitive, u8 vtxfmt, u16 vtxcnt);
void GX_Position3s16(s16 x, s16 y, s16 z);
void GX_Position3f32(f32 x, f32 y, f32 z);
void GX_Position2s16(s16 x, s16 y);
void GX_Color4u8(u8 r, u8 g, u8 b, u8 a);
void GX_TexCoord2s16(s16 s, s16 t);
void GX_TexCoord2f32(f32 s, f32 t);
void GX_End(void);

/* gu matrix helpers (fixed 640x480 orthographic view on PC) */
void guLookAt(Mtx mt, guVector *camPos, guVector *camUp, guVector *target);
void guOrtho(Mtx44 mt, f32 t, f32 b, f32 l, f32 r, f32 n, f32 f);
void guMtxIdentity(Mtx mt);
void guMtxTransApply(Mtx src, Mtx dst, f32 xT, f32 yT, f32 zT);
void guMtxConcat(Mtx a, Mtx b, Mtx ab);

#ifdef __cplusplus
}
#endif
#endif
