/*
 * grrlib_sdl.c - GRRLIB drawing primitives on top of SDL2.
 * Keeps the Wii's 640x480 logical resolution and scales the window.
 */
#include <SDL.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "grrlib.h"
#include "vct_platform.h"

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_NO_STDIO
#include "stb_image.h"

static SDL_Window *g_window = NULL;
static SDL_Renderer *g_renderer = NULL;
static Uint32 g_last_frame = 0;
static unsigned long g_frame = 0;

extern int quitState; /* defined in the original main.c */

static void set_color(u32 c)
{
    SDL_SetRenderDrawColor(g_renderer, (c >> 24) & 0xFF, (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF);
}

void GRRLIB_Init(void)
{
    Uint32 sub = SDL_INIT_VIDEO | SDL_INIT_EVENTS;
    if (g_vct_opts.use_sdl_gamepads)
        sub |= SDL_INIT_GAMECONTROLLER;
    if (SDL_Init(sub) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        exit(1);
    }
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "linear");
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");

    int w = (int)(640 * g_vct_opts.scale);
    int h = (int)(480 * g_vct_opts.scale);
    Uint32 flags = SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI;
    if (g_vct_opts.fullscreen)
        flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
    if (g_vct_opts.hidden)
        flags |= SDL_WINDOW_HIDDEN;

    g_window = SDL_CreateWindow("Visual Controller Test (PC)", SDL_WINDOWPOS_CENTERED,
                                SDL_WINDOWPOS_CENTERED, w, h, flags);
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
    SDL_RenderSetLogicalSize(g_renderer, 640, 480);
    SDL_SetRenderDrawBlendMode(g_renderer, SDL_BLENDMODE_BLEND);
    set_color(0x000000FF);
    SDL_RenderClear(g_renderer);
    g_last_frame = SDL_GetTicks();
}

void GRRLIB_Exit(void)
{
    vct_platform_shutdown();
    /* textures are freed after GRRLIB_Exit in main.c: keep the renderer alive,
       SDL_Quit at process exit releases everything. */
}

static void save_screenshot(const char *path)
{
    int w, h;
    SDL_GetRendererOutputSize(g_renderer, &w, &h);
    SDL_Surface *s = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!s)
        return;
    if (SDL_RenderReadPixels(g_renderer, NULL, SDL_PIXELFORMAT_ARGB8888, s->pixels, s->pitch) == 0) {
        if (SDL_SaveBMP(s, path) == 0)
            fprintf(stderr, "screenshot saved: %s\n", path);
    }
    SDL_FreeSurface(s);
}

void GRRLIB_Render(void)
{
    g_frame++;
    if (g_vct_opts.screenshot_path && g_frame == (unsigned long)g_vct_opts.screenshot_frame)
        save_screenshot(g_vct_opts.screenshot_path);

    SDL_RenderPresent(g_renderer);

    SDL_Event ev;
    while (SDL_PollEvent(&ev)) {
        switch (ev.type) {
        case SDL_QUIT:
            quitState = 1;
            break;
        case SDL_KEYDOWN:
            if (ev.key.keysym.sym == SDLK_ESCAPE || ev.key.keysym.sym == SDLK_AC_BACK)
                quitState = 1;
            else if (ev.key.keysym.sym == SDLK_F11 ||
                     (ev.key.keysym.sym == SDLK_RETURN && (ev.key.keysym.mod & KMOD_ALT))) {
                Uint32 f = SDL_GetWindowFlags(g_window);
                SDL_SetWindowFullscreen(g_window, (f & SDL_WINDOW_FULLSCREEN_DESKTOP) ? 0 : SDL_WINDOW_FULLSCREEN_DESKTOP);
            }
            break;
        default:
            vct_platform_event(&ev);
            break;
        }
    }

    if (g_vct_opts.max_frames > 0 && g_frame >= (unsigned long)g_vct_opts.max_frames)
        quitState = 1;

    /* frame pacing when vsync is unavailable (software / dummy drivers) */
    Uint32 now = SDL_GetTicks();
    Uint32 elapsed = now - g_last_frame;
    if (elapsed < 16)
        SDL_Delay(16 - elapsed);
    g_last_frame = SDL_GetTicks();

    set_color(0x000000FF);
    SDL_RenderClear(g_renderer);
}

GRRLIB_texImg *GRRLIB_LoadTextureMem(const u8 *data, unsigned int size)
{
    int w, h, n;
    unsigned char *pixels = stbi_load_from_memory(data, (int)size, &w, &h, &n, 4);
    if (!pixels) {
        fprintf(stderr, "texture decode failed: %s\n", stbi_failure_reason());
        return NULL;
    }
    SDL_Texture *t = SDL_CreateTexture(g_renderer, SDL_PIXELFORMAT_ABGR8888, SDL_TEXTUREACCESS_STATIC, w, h);
    if (!t) {
        stbi_image_free(pixels);
        return NULL;
    }
    SDL_UpdateTexture(t, NULL, pixels, w * 4);
    SDL_SetTextureBlendMode(t, SDL_BLENDMODE_BLEND);
    stbi_image_free(pixels);

    GRRLIB_texImg *tex = (GRRLIB_texImg *)calloc(1, sizeof(GRRLIB_texImg));
    tex->w = (unsigned)w;
    tex->h = (unsigned)h;
    tex->sdl_texture = t;
    return tex;
}

void GRRLIB_FreeTexture(GRRLIB_texImg *tex)
{
    if (!tex)
        return;
    if (tex->sdl_texture && g_renderer)
        SDL_DestroyTexture((SDL_Texture *)tex->sdl_texture);
    free(tex);
}

/* Handle = rotation pivot in image-local pixels (GRRLIB default: 0,0) */
void GRRLIB_SetHandle(GRRLIB_texImg *tex, int x, int y)
{
    if (!tex)
        return;
    tex->handlex = x;
    tex->handley = y;
}

void GRRLIB_InitTileSet(GRRLIB_texImg *tex, unsigned int tilew, unsigned int tileh, unsigned int tilestart)
{
    if (!tex)
        return;
    tex->tiledtex = true;
    tex->tilew = tilew;
    tex->tileh = tileh;
    tex->nbtilew = tex->w / tilew;
    tex->nbtileh = tex->h / tileh;
    tex->tilestart = tilestart;
}

static void draw_region(f32 x, f32 y, const GRRLIB_texImg *tex, const SDL_Rect *src, int sw, int sh,
                        f32 degrees, f32 sx, f32 sy, u32 color)
{
    if (!tex || !tex->sdl_texture)
        return;
    SDL_Texture *t = (SDL_Texture *)tex->sdl_texture;
    SDL_SetTextureColorMod(t, (color >> 24) & 0xFF, (color >> 16) & 0xFF, (color >> 8) & 0xFF);
    SDL_SetTextureAlphaMod(t, color & 0xFF);

    SDL_RendererFlip flip = SDL_FLIP_NONE;
    if (sx < 0) { flip |= SDL_FLIP_HORIZONTAL; sx = -sx; }
    if (sy < 0) { flip |= SDL_FLIP_VERTICAL; sy = -sy; }

    SDL_FRect dst;
    dst.x = x + tex->handlex - tex->handlex * sx;
    dst.y = y + tex->handley - tex->handley * sy;
    dst.w = sw * sx;
    dst.h = sh * sy;
    SDL_FPoint pivot = { tex->handlex * sx, tex->handley * sy };
    SDL_RenderCopyExF(g_renderer, t, src, &dst, degrees, &pivot, flip);
}

void GRRLIB_DrawImg(f32 xpos, f32 ypos, const GRRLIB_texImg *tex, f32 degrees, f32 scaleX, f32 scaleY, u32 color)
{
    if (!tex)
        return;
    draw_region(xpos, ypos, tex, NULL, (int)tex->w, (int)tex->h, degrees, scaleX, scaleY, color);
}

void GRRLIB_DrawTile(f32 xpos, f32 ypos, const GRRLIB_texImg *tex, f32 degrees, f32 scaleX, f32 scaleY, u32 color, int frame)
{
    if (!tex || !tex->tiledtex || frame < 0 || (unsigned)frame >= tex->nbtilew * tex->nbtileh)
        return;
    SDL_Rect src = { (int)((frame % tex->nbtilew) * tex->tilew), (int)((frame / tex->nbtilew) * tex->tileh),
                     (int)tex->tilew, (int)tex->tileh };
    draw_region(xpos, ypos, tex, &src, (int)tex->tilew, (int)tex->tileh, degrees, scaleX, scaleY, color);
}

void GRRLIB_Printf(f32 xpos, f32 ypos, const GRRLIB_texImg *tex, u32 color, f32 zoom, const char *text, ...)
{
    if (!tex || !text)
        return;
    char buf[1024];
    va_list ap;
    va_start(ap, text);
    vsnprintf(buf, sizeof buf, text, ap);
    va_end(ap);
    size_t len = strlen(buf);
    for (size_t i = 0; i < len; i++) {
        int frame = (int)(unsigned char)buf[i] - (int)tex->tilestart;
        GRRLIB_DrawTile(xpos + i * tex->tilew * zoom, ypos, tex, 0, zoom, zoom, color, frame);
    }
}

void GRRLIB_Rectangle(f32 x, f32 y, f32 width, f32 height, u32 color, bool filled)
{
    set_color(color);
    SDL_FRect r = { x, y, width, height };
    if (filled)
        SDL_RenderFillRectF(g_renderer, &r);
    else
        SDL_RenderDrawRectF(g_renderer, &r);
}

void GRRLIB_Line(f32 x1, f32 y1, f32 x2, f32 y2, u32 color)
{
    set_color(color);
    SDL_RenderDrawLineF(g_renderer, x1, y1, x2, y2);
}

void GRRLIB_Circle(f32 x, f32 y, f32 radius, u32 color, u8 filled)
{
    enum { SEG = 48 };
    SDL_Color c = { (color >> 24) & 0xFF, (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF };
    if (filled) {
        SDL_Vertex v[SEG + 2];
        int idx[SEG * 3];
        v[0].position.x = x; v[0].position.y = y; v[0].color = c;
        v[0].tex_coord.x = v[0].tex_coord.y = 0;
        for (int i = 0; i <= SEG; i++) {
            double a = 2.0 * M_PI * i / SEG;
            v[i + 1].position.x = x + (float)(radius * cos(a));
            v[i + 1].position.y = y + (float)(radius * sin(a));
            v[i + 1].color = c;
            v[i + 1].tex_coord.x = v[i + 1].tex_coord.y = 0;
        }
        for (int i = 0; i < SEG; i++) {
            idx[i * 3] = 0;
            idx[i * 3 + 1] = i + 1;
            idx[i * 3 + 2] = i + 2;
        }
        SDL_RenderGeometry(g_renderer, NULL, v, SEG + 2, idx, SEG * 3);
    } else {
        SDL_FPoint p[SEG + 1];
        for (int i = 0; i <= SEG; i++) {
            double a = 2.0 * M_PI * i / SEG;
            p[i].x = x + (float)(radius * cos(a));
            p[i].y = y + (float)(radius * sin(a));
        }
        SDL_SetRenderDrawColor(g_renderer, c.r, c.g, c.b, c.a);
        SDL_RenderDrawLinesF(g_renderer, p, SEG + 1);
    }
}
