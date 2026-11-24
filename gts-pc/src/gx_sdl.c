/*
 * gx_sdl.c - GameCube GX / VIDEO / TPL subset for GTS, on top of SDL2.
 *
 * GTS draws in GX immediate mode: GX_Begin(prim, fmt, n), then per vertex
 * Position / Color / TexCoord, then GX_End. Every primitive is recorded with
 * the state it would be rasterised with on the console (texture, TEV op, line
 * width, scissor box and scissor offset). When the frame is copied out
 * (GX_DrawDone), primitives are sorted by depth - GTS relies on the console's
 * Z buffer (LEQUAL) to layer its UI - and drawn with SDL_RenderGeometry.
 *
 * Copyright (C) 2026 Shido971 - GPL-3.0-or-later (linked with GTS, GPL-3.0).
 */
#include <SDL.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ogc/gx.h"
#include "ogc/tpl.h"
#include "ogc/video.h"
#include "vct_platform.h"

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_NO_STDIO
#include "stb_image.h"

#define SCREEN_W 640
#define SCREEN_H 480

/* ----------------------------------------------------------------------- */
/* Recorded frame                                                           */
/* ----------------------------------------------------------------------- */
typedef struct {
    float x, y, z;
    SDL_Color c;
    float s, t;
} Vtx;

typedef struct {
    u8 prim;
    float z;
    int first, count;
    SDL_Texture *tex;
    int tw, th;
    u8 tevop;
    float line_w, point_s;
    SDL_Rect clip;
    float off_x, off_y;
    int seq;
} Prim;

typedef struct {
    Vtx *v;
    int nv, cap_v;
    Prim *p;
    int np, cap_p;
} DrawList;

static DrawList g_build, g_frame;

static void list_reset(DrawList *l) { l->nv = 0; l->np = 0; }

static Vtx *list_add_vtx(DrawList *l)
{
    if (l->nv == l->cap_v) {
        l->cap_v = l->cap_v ? l->cap_v * 2 : 4096;
        l->v = (Vtx *)realloc(l->v, sizeof(Vtx) * (size_t)l->cap_v);
    }
    return &l->v[l->nv++];
}

static Prim *list_add_prim(DrawList *l)
{
    if (l->np == l->cap_p) {
        l->cap_p = l->cap_p ? l->cap_p * 2 : 1024;
        l->p = (Prim *)realloc(l->p, sizeof(Prim) * (size_t)l->cap_p);
    }
    return &l->p[l->np++];
}

/* ----------------------------------------------------------------------- */
/* GX state                                                                 */
/* ----------------------------------------------------------------------- */
static GXTexObj g_texmaps[GX_MAX_TEXMAP];
static u32 g_tev_texmap = GX_TEXMAP_NULL;
static u8 g_tev_op = GX_PASSCLR;
static float g_line_w = 2.0f, g_point_s = 2.0f;
static SDL_Rect g_scissor = { 0, 0, SCREEN_W, SCREEN_H };
static int g_off_x = 0, g_off_y = 0;
static SDL_Color g_clear = { 0, 0, 0, 255 };

static int g_in_begin = 0;
static u8 g_cur_prim = 0;
static int g_cur_first = 0;
static int g_seq = 0;

static SDL_Window *g_window;
static SDL_Renderer *g_renderer;

GXFifoObj *GX_Init(void *base, u32 size)
{
    (void)base; (void)size;
    static GXFifoObj fifo;
    return &fifo;
}
void GX_InitFifoLimits(GXFifoObj *f, u32 h, u32 l) { (void)f; (void)h; (void)l; }
u8 GX_GetFifoWrap(GXFifoObj *f) { (void)f; return 0; }
void GX_SetCopyClear(GXColor c, u32 z) { (void)z; g_clear = (SDL_Color){ c.r, c.g, c.b, 255 }; }
f32 GX_GetYScaleFactor(u16 e, u16 x) { (void)e; (void)x; return 1.0f; }
u32 GX_SetDispCopyYScale(f32 s) { (void)s; return SCREEN_H; }
void GX_SetScissor(u32 x, u32 y, u32 w, u32 h) { g_scissor = (SDL_Rect){ (int)x, (int)y, (int)w, (int)h }; }
void GX_SetScissorBoxOffset(s32 x, s32 y) { g_off_x = x; g_off_y = y; }
void GX_SetDispCopySrc(u16 l, u16 t, u16 w, u16 h) { (void)l; (void)t; (void)w; (void)h; }
void GX_SetDispCopyDst(u16 w, u16 h) { (void)w; (void)h; }
void GX_SetPixelFmt(u8 p, u8 z) { (void)p; (void)z; }
void GX_SetCopyFilter(u8 aa, u8 sp[12][2], u8 vf, u8 *vfilter) { (void)aa; (void)sp; (void)vf; (void)vfilter; }
void GX_SetFieldMode(u8 f, u8 h) { (void)f; (void)h; }
void GX_SetCullMode(u8 m) { (void)m; }
void GX_ClearVtxDesc(void) {}
void GX_SetVtxDesc(u8 a, u8 t) { (void)a; (void)t; }
void GX_SetVtxAttrFmt(u8 f, u32 a, u32 c, u32 s, u32 fr) { (void)f; (void)a; (void)c; (void)s; (void)fr; }
void GX_SetNumChans(u8 n) { (void)n; }
void GX_SetChanCtrl(s32 c, u8 e, u8 a, u8 m, u8 l, u8 d, u8 at) { (void)c; (void)e; (void)a; (void)m; (void)l; (void)d; (void)at; }
void GX_SetNumTexGens(u32 n) { (void)n; }
void GX_SetTexCoordScaleManually(u8 c, u8 e, u16 s, u16 t) { (void)c; (void)e; (void)s; (void)t; }
void GX_SetNumTevStages(u8 n) { (void)n; }
void GX_SetTevOrder(u8 stage, u8 texcoord, u32 texmap, u8 color)
{
    (void)texcoord; (void)color;
    if (stage == GX_TEVSTAGE0)
        g_tev_texmap = texmap;
}
void GX_SetTevOp(u8 stage, u8 mode) { if (stage == GX_TEVSTAGE0) g_tev_op = mode; }
void GX_SetTevDirect(u8 s) { (void)s; }
void GX_InvVtxCache(void) {}
void GX_InvalidateTexAll(void) {}
void GX_LoadTexObj(GXTexObj *obj, u8 mapid)
{
    if (obj && mapid < GX_MAX_TEXMAP)
        g_texmaps[mapid] = *obj;
}
u16 GX_GetTexObjWidth(GXTexObj *o) { return o ? o->width : 0; }
u16 GX_GetTexObjHeight(GXTexObj *o) { return o ? o->height : 0; }
void GX_SetBlendMode(u8 t, u8 s, u8 d, u8 o) { (void)t; (void)s; (void)d; (void)o; }
void GX_SetAlphaUpdate(u8 e) { (void)e; }
void GX_SetColorUpdate(u8 e) { (void)e; }
void GX_LoadProjectionMtx(Mtx44 m, u8 t) { (void)m; (void)t; }
void GX_LoadPosMtxImm(Mtx m, u32 i) { (void)m; (void)i; }
/* widths are in 1/6 pixel on the console */
void GX_SetLineWidth(u8 w, u8 f) { (void)f; g_line_w = w / 6.0f; }
void GX_SetPointSize(u8 w, u8 f) { (void)f; g_point_s = w / 6.0f; }
u32 GX_GetGPStatus(u8 *a, u8 *b, u8 *c, u8 *d, u8 *e)
{
    if (a) *a = 0;
    if (b) *b = 0;
    if (c) *c = 1;
    if (d) *d = 1;
    if (e) *e = 0;
    return 0;
}

void GX_Begin(u8 primitive, u8 vtxfmt, u16 vtxcnt)
{
    (void)vtxfmt; (void)vtxcnt;
    g_in_begin = 1;
    g_cur_prim = primitive;
    g_cur_first = g_build.nv;
}

static void push_pos(float x, float y, float z)
{
    Vtx *v = list_add_vtx(&g_build);
    v->x = x; v->y = y; v->z = z;
    v->c = (SDL_Color){ 255, 255, 255, 255 };
    v->s = v->t = 0;
}
void GX_Position3s16(s16 x, s16 y, s16 z) { push_pos(x, y, z); }
void GX_Position3f32(f32 x, f32 y, f32 z) { push_pos(x, y, z); }
void GX_Position2s16(s16 x, s16 y) { push_pos(x, y, 0); }
void GX_Color4u8(u8 r, u8 g, u8 b, u8 a)
{
    if (g_build.nv > g_cur_first)
        g_build.v[g_build.nv - 1].c = (SDL_Color){ r, g, b, a };
}
void GX_TexCoord2s16(s16 s, s16 t)
{
    if (g_build.nv > g_cur_first) {
        g_build.v[g_build.nv - 1].s = s;
        g_build.v[g_build.nv - 1].t = t;
    }
}
void GX_TexCoord2f32(f32 s, f32 t) { GX_TexCoord2s16((s16)s, (s16)t); }

void GX_End(void)
{
    if (!g_in_begin)
        return;
    g_in_begin = 0;
    int count = g_build.nv - g_cur_first;
    if (count <= 0)
        return;
    Prim *p = list_add_prim(&g_build);
    p->prim = g_cur_prim;
    p->first = g_cur_first;
    p->count = count;
    p->z = g_build.v[g_cur_first].z;
    p->tevop = g_tev_op;
    p->tex = NULL;
    p->tw = p->th = 1;
    if (g_tev_op != GX_PASSCLR && g_tev_texmap < GX_MAX_TEXMAP && g_texmaps[g_tev_texmap].sdl_texture) {
        p->tex = (SDL_Texture *)g_texmaps[g_tev_texmap].sdl_texture;
        p->tw = g_texmaps[g_tev_texmap].width;
        p->th = g_texmaps[g_tev_texmap].height;
    }
    p->line_w = g_line_w;
    p->point_s = g_point_s;
    /* screen = vertex - offset ; the scissor box moves with the offset */
    p->off_x = (float)g_off_x;
    p->off_y = (float)g_off_y;
    p->clip = (SDL_Rect){ g_scissor.x - g_off_x, g_scissor.y - g_off_y, g_scissor.w, g_scissor.h };
    p->seq = g_seq++;
}

void GX_CopyDisp(void *dest, u8 clear) { (void)dest; (void)clear; }
void GX_Flush(void) {}

/* end of frame: the recorded list becomes the displayed frame */
void GX_DrawDone(void)
{
    DrawList t = g_frame;
    g_frame = g_build;
    g_build = t;
    list_reset(&g_build);
    g_seq = 0;
}

/* ----------------------------------------------------------------------- */
/* Rasterisation                                                            */
/* ----------------------------------------------------------------------- */
static int cmp_prim(const void *a, const void *b)
{
    const Prim *pa = (const Prim *)a, *pb = (const Prim *)b;
    if (pa->z < pb->z) return -1;   /* farther first: larger z is closer to the camera */
    if (pa->z > pb->z) return 1;
    return pa->seq - pb->seq;       /* LEQUAL: equal depth, later draw wins */
}

static SDL_Vertex mkv(const Prim *p, const Vtx *v, float dx, float dy)
{
    SDL_Vertex o;
    o.position.x = v->x - p->off_x + dx;
    o.position.y = v->y - p->off_y + dy;
    o.color = v->c;
    if (p->tevop == GX_REPLACE)
        o.color = (SDL_Color){ 255, 255, 255, v->c.a };
    o.tex_coord.x = p->tex ? v->s / (float)p->tw : 0;
    o.tex_coord.y = p->tex ? v->t / (float)p->th : 0;
    return o;
}

static SDL_Vertex *g_tri;
static int g_ntri, g_cap_tri;

static void tri_push(SDL_Vertex v)
{
    if (g_ntri == g_cap_tri) {
        g_cap_tri = g_cap_tri ? g_cap_tri * 2 : 4096;
        g_tri = (SDL_Vertex *)realloc(g_tri, sizeof(SDL_Vertex) * (size_t)g_cap_tri);
    }
    g_tri[g_ntri++] = v;
}

static void thick_segment(const Prim *p, const Vtx *a, const Vtx *b)
{
    float dx = b->x - a->x, dy = b->y - a->y;
    float len = sqrtf(dx * dx + dy * dy);
    float hw = p->line_w * 0.5f;
    if (hw < 0.5f)
        hw = 0.5f;
    float nx, ny, ex, ey;
    if (len < 1e-4f) {
        nx = 0; ny = hw; ex = hw; ey = 0;
    } else {
        nx = -dy / len * hw; ny = dx / len * hw;
        ex = dx / len * hw * 0.5f; ey = dy / len * hw * 0.5f;   /* small end caps */
    }
    SDL_Vertex a1 = mkv(p, a, nx - ex, ny - ey), a2 = mkv(p, a, -nx - ex, -ny - ey);
    SDL_Vertex b1 = mkv(p, b, nx + ex, ny + ey), b2 = mkv(p, b, -nx + ex, -ny + ey);
    tri_push(a1); tri_push(b1); tri_push(b2);
    tri_push(a1); tri_push(b2); tri_push(a2);
}

static void draw_prim(const Prim *p, const Vtx *v)
{
    g_ntri = 0;
    switch (p->prim) {
    case GX_QUADS:
        for (int i = 0; i + 3 < p->count; i += 4) {
            SDL_Vertex q0 = mkv(p, &v[i], 0, 0), q1 = mkv(p, &v[i + 1], 0, 0);
            SDL_Vertex q2 = mkv(p, &v[i + 2], 0, 0), q3 = mkv(p, &v[i + 3], 0, 0);
            tri_push(q0); tri_push(q1); tri_push(q2);
            tri_push(q0); tri_push(q2); tri_push(q3);
        }
        break;
    case GX_TRIANGLES:
        for (int i = 0; i + 2 < p->count; i += 3) {
            tri_push(mkv(p, &v[i], 0, 0)); tri_push(mkv(p, &v[i + 1], 0, 0)); tri_push(mkv(p, &v[i + 2], 0, 0));
        }
        break;
    case GX_TRIANGLESTRIP:
        for (int i = 0; i + 2 < p->count; i++) {
            tri_push(mkv(p, &v[i], 0, 0)); tri_push(mkv(p, &v[i + 1], 0, 0)); tri_push(mkv(p, &v[i + 2], 0, 0));
        }
        break;
    case GX_TRIANGLEFAN:
        for (int i = 1; i + 1 < p->count; i++) {
            tri_push(mkv(p, &v[0], 0, 0)); tri_push(mkv(p, &v[i], 0, 0)); tri_push(mkv(p, &v[i + 1], 0, 0));
        }
        break;
    case GX_LINES:
        for (int i = 0; i + 1 < p->count; i += 2)
            thick_segment(p, &v[i], &v[i + 1]);
        break;
    case GX_LINESTRIP:
        for (int i = 0; i + 1 < p->count; i++)
            thick_segment(p, &v[i], &v[i + 1]);
        break;
    case GX_POINTS: {
        float h = p->point_s * 0.5f;
        if (h < 0.5f)
            h = 0.5f;
        for (int i = 0; i < p->count; i++) {
            SDL_Vertex c0 = mkv(p, &v[i], -h, -h), c1 = mkv(p, &v[i], h, -h);
            SDL_Vertex c2 = mkv(p, &v[i], h, h), c3 = mkv(p, &v[i], -h, h);
            tri_push(c0); tri_push(c1); tri_push(c2);
            tri_push(c0); tri_push(c2); tri_push(c3);
        }
        break;
    }
    default:
        return;
    }
    if (g_ntri == 0)
        return;
    SDL_RenderSetClipRect(g_renderer, &p->clip);
    SDL_RenderGeometry(g_renderer, p->tex, g_tri, g_ntri, NULL, 0);
}

static void render_frame(void)
{
    SDL_RenderSetClipRect(g_renderer, NULL);
    SDL_SetRenderDrawColor(g_renderer, g_clear.r, g_clear.g, g_clear.b, 255);
    SDL_RenderClear(g_renderer);
    if (g_frame.np > 1)
        qsort(g_frame.p, (size_t)g_frame.np, sizeof(Prim), cmp_prim);
    for (int i = 0; i < g_frame.np; i++)
        draw_prim(&g_frame.p[i], &g_frame.v[g_frame.p[i].first]);
    SDL_RenderSetClipRect(g_renderer, NULL);
}

/* ----------------------------------------------------------------------- */
/* gu matrices: the PC view is a fixed 640x480 orthographic projection       */
/* ----------------------------------------------------------------------- */
void guLookAt(Mtx mt, guVector *a, guVector *b, guVector *c) { (void)a; (void)b; (void)c; memset(mt, 0, sizeof(Mtx)); }
void guOrtho(Mtx44 mt, f32 t, f32 b, f32 l, f32 r, f32 n, f32 f)
{
    (void)t; (void)b; (void)l; (void)r; (void)n; (void)f;
    memset(mt, 0, sizeof(Mtx44));
}
void guMtxIdentity(Mtx mt)
{
    memset(mt, 0, sizeof(Mtx));
    mt[0][0] = mt[1][1] = mt[2][2] = 1;
}
void guMtxTransApply(Mtx src, Mtx dst, f32 x, f32 y, f32 z)
{
    if (src != dst)
        memcpy(dst, src, sizeof(Mtx));
    dst[0][3] += x; dst[1][3] += y; dst[2][3] += z;
}
void guMtxConcat(Mtx a, Mtx b, Mtx ab) { (void)a; memcpy(ab, b, sizeof(Mtx)); }

/* ----------------------------------------------------------------------- */
/* Textures (TPL replaced by the PNGs listed in textures.scf)               */
/* ----------------------------------------------------------------------- */
extern const unsigned char *const gts_tex_png[];
extern const unsigned int gts_tex_png_size[];
extern const int gts_tex_count;

s32 TPL_OpenTPLFromMemory(TPLFile *t, void *mem, u32 len) { (void)len; t->pack = mem; return 1; }
void TPL_CloseTPLFile(TPLFile *t) { (void)t; }

s32 TPL_GetTexture(TPLFile *tdf, s32 id, GXTexObj *obj)
{
    (void)tdf;
    memset(obj, 0, sizeof *obj);
    if (id < 0 || id >= gts_tex_count || !g_renderer)
        return 0;
    int w, h, n;
    unsigned char *px = stbi_load_from_memory(gts_tex_png[id], (int)gts_tex_png_size[id], &w, &h, &n, 4);
    if (!px) {
        fprintf(stderr, "texture %d: %s\n", (int)id, stbi_failure_reason());
        return 0;
    }
    SDL_Texture *t = SDL_CreateTexture(g_renderer, SDL_PIXELFORMAT_ABGR8888, SDL_TEXTUREACCESS_STATIC, w, h);
    if (t) {
        SDL_UpdateTexture(t, NULL, px, w * 4);
        SDL_SetTextureBlendMode(t, SDL_BLENDMODE_BLEND);
        SDL_SetTextureScaleMode(t, SDL_ScaleModeNearest);
    }
    stbi_image_free(px);
    obj->sdl_texture = t;
    obj->width = (u16)w;
    obj->height = (u16)h;
    return t ? 1 : 0;
}

/* ----------------------------------------------------------------------- */
/* VIDEO                                                                    */
/* ----------------------------------------------------------------------- */
static GXRModeObj g_mode = {
    .viTVMode = VI_NTSC, .fbWidth = SCREEN_W, .efbHeight = SCREEN_H, .xfbHeight = SCREEN_H,
    .viXOrigin = 40, .viYOrigin = 0, .viWidth = 640, .viHeight = SCREEN_H,
};
static u32 g_retrace = 0;
static VIRetraceCallback g_post_retrace = NULL;
static volatile int g_quit = 0;
static Uint64 g_last_frame = 0;
static unsigned long g_frames = 0;

void vct_pad_frame_tick(void);

u32 SYS_ResetButtonDown(void) { return g_quit ? 1 : 0; }

void VIDEO_Init(void)
{
    if (g_window)
        return;
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");
    Uint32 sub = SDL_INIT_VIDEO | SDL_INIT_EVENTS;
    if (g_vct_opts.use_sdl_gamepads)
        sub |= SDL_INIT_GAMECONTROLLER;
    if (SDL_Init(sub) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        exit(1);
    }
    Uint32 flags = SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI;
    if (g_vct_opts.fullscreen)
        flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
    if (g_vct_opts.hidden)
        flags |= SDL_WINDOW_HIDDEN;
    g_window = SDL_CreateWindow("GCC Test Suite (GTS) - PC", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                (int)(SCREEN_W * g_vct_opts.scale), (int)(SCREEN_H * g_vct_opts.scale), flags);
    if (!g_window) {
        fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
        exit(1);
    }
    g_renderer = SDL_CreateRenderer(g_window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!g_renderer)
        g_renderer = SDL_CreateRenderer(g_window, -1, SDL_RENDERER_SOFTWARE);
    if (!g_renderer) {
        fprintf(stderr, "SDL_CreateRenderer: %s\n", SDL_GetError());
        exit(1);
    }
    SDL_RenderSetLogicalSize(g_renderer, SCREEN_W, SCREEN_H);
    SDL_SetRenderDrawBlendMode(g_renderer, SDL_BLENDMODE_BLEND);
    g_last_frame = SDL_GetPerformanceCounter();
}

GXRModeObj *VIDEO_GetPreferredMode(GXRModeObj *mode) { (void)mode; return &g_mode; }
void VIDEO_Configure(GXRModeObj *r) { (void)r; }
void VIDEO_ClearFrameBuffer(GXRModeObj *r, void *fb, u32 c) { (void)r; (void)fb; (void)c; }
void VIDEO_SetNextFramebuffer(void *fb) { (void)fb; }
void VIDEO_SetBlack(bool b) { (void)b; }
void VIDEO_Flush(void) {}
u32 VIDEO_GetRetraceCount(void) { return g_retrace; }
u32 VIDEO_GetScanMode(void) { return VI_PROGRESSIVE; }
u32 VIDEO_GetCurrentTvMode(void) { return VI_NTSC; }
VIRetraceCallback VIDEO_SetPostRetraceCallback(VIRetraceCallback cb)
{
    VIRetraceCallback old = g_post_retrace;
    g_post_retrace = cb;
    return old;
}
/* GTS frees its framebuffers on exit: hand out real (tiny) heap blocks */
void *SYS_AllocateFramebuffer(GXRModeObj *r) { (void)r; return calloc(1, 32); }

static void save_screenshot(const char *path)
{
    int w, h;
    SDL_GetRendererOutputSize(g_renderer, &w, &h);
    SDL_Surface *s = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!s)
        return;
    if (SDL_RenderReadPixels(g_renderer, NULL, SDL_PIXELFORMAT_ARGB8888, s->pixels, s->pitch) == 0 && SDL_SaveBMP(s, path) == 0)
        fprintf(stderr, "screenshot saved: %s\n", path);
    SDL_FreeSurface(s);
}

/* one "retrace": draw the last copied frame, present, pump events, pace to 60 Hz */
static void present(void)
{
    if (!g_renderer)
        return;
    render_frame();
    g_frames++;
    if (g_vct_opts.screenshot_path && g_frames == (unsigned long)g_vct_opts.screenshot_frame)
        save_screenshot(g_vct_opts.screenshot_path);
    SDL_RenderPresent(g_renderer);

    SDL_Event ev;
    while (SDL_PollEvent(&ev)) {
        if (ev.type == SDL_QUIT)
            g_quit = 1;
        else if (ev.type == SDL_KEYDOWN) {
            SDL_Keycode k = ev.key.keysym.sym;
            if (k == SDLK_ESCAPE || k == SDLK_AC_BACK)
                g_quit = 1;
            else if (k == SDLK_F11 || (k == SDLK_RETURN && (ev.key.keysym.mod & KMOD_ALT))) {
                Uint32 f = SDL_GetWindowFlags(g_window);
                SDL_SetWindowFullscreen(g_window, (f & SDL_WINDOW_FULLSCREEN_DESKTOP) ? 0 : SDL_WINDOW_FULLSCREEN_DESKTOP);
            }
        } else {
            vct_platform_event(&ev);
        }
    }
    if (g_vct_opts.max_frames > 0 && g_frames >= (unsigned long)g_vct_opts.max_frames)
        g_quit = 1;

    /* pace to ~59.94 Hz when vsync is not available */
    Uint64 freq = SDL_GetPerformanceFrequency();
    Uint64 target = g_last_frame + freq * 1001 / 60000;
    Uint64 now = SDL_GetPerformanceCounter();
    if (now < target) {
        Uint32 ms = (Uint32)((target - now) * 1000 / freq);
        if (ms > 1)
            SDL_Delay(ms - 1);
        while (SDL_GetPerformanceCounter() < target) {}
    }
    g_last_frame = SDL_GetPerformanceCounter();

    g_retrace++;
    vct_pad_frame_tick();
    if (g_post_retrace)
        g_post_retrace(g_retrace);
}

void VIDEO_WaitForFlush(void) { present(); }
void VIDEO_WaitVSync(void) { present(); }
void VIDEO_WaitForRetrace(u32 count)
{
    while (g_retrace < count && !g_quit)
        present();
}
