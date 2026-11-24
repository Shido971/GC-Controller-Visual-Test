/*
 * grrlib.h - the subset of GRRLIB 4.x used by Visual Controller Test,
 * re-implemented on top of SDL2 (see src/grrlib_sdl.c).
 * Colors are 0xRRGGBBAA, the logical screen is 640x480 like on the Wii.
 */
#ifndef VCT_COMPAT_GRRLIB_H
#define VCT_COMPAT_GRRLIB_H

#include "ogc_compat.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct GRRLIB_texImg {
    unsigned int w, h;
    int handlex, handley;     /* rotation pivot, default = centre */
    int offsetx, offsety;
    bool tiledtex;
    unsigned int tilew, tileh, nbtilew, nbtileh, tilestart;
    void *sdl_texture;        /* SDL_Texture* */
} GRRLIB_texImg;

void GRRLIB_Init(void);
void GRRLIB_Exit(void);
void GRRLIB_Render(void);

GRRLIB_texImg *GRRLIB_LoadTextureMem(const u8 *data, unsigned int size);
/* main.c calls GRRLIB_LoadTexture(foo_png); the embedded asset also exports foo_png_size */
#define GRRLIB_LoadTexture(name) GRRLIB_LoadTextureMem(name, name##_size)
void GRRLIB_FreeTexture(GRRLIB_texImg *tex);
void GRRLIB_SetHandle(GRRLIB_texImg *tex, int x, int y);
void GRRLIB_InitTileSet(GRRLIB_texImg *tex, unsigned int tilew, unsigned int tileh, unsigned int tilestart);

void GRRLIB_DrawImg(f32 xpos, f32 ypos, const GRRLIB_texImg *tex, f32 degrees, f32 scaleX, f32 scaleY, u32 color);
void GRRLIB_DrawTile(f32 xpos, f32 ypos, const GRRLIB_texImg *tex, f32 degrees, f32 scaleX, f32 scaleY, u32 color, int frame);
void GRRLIB_Printf(f32 xpos, f32 ypos, const GRRLIB_texImg *tex, u32 color, f32 zoom, const char *text, ...);
void GRRLIB_Rectangle(f32 x, f32 y, f32 width, f32 height, u32 color, bool filled);
void GRRLIB_Circle(f32 x, f32 y, f32 radius, u32 color, u8 filled);
void GRRLIB_Line(f32 x1, f32 y1, f32 x2, f32 y2, u32 color);

#ifdef __cplusplus
}
#endif
#endif
