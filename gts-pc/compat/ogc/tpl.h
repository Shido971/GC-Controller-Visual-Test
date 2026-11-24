/* ogc/tpl.h - texture packs: on PC the "TPL" is the list of PNGs from textures.scf */
#ifndef GTS_COMPAT_TPL_H
#define GTS_COMPAT_TPL_H
#include "gx.h"
typedef struct { const void *pack; } TPLFile;
s32 TPL_OpenTPLFromMemory(TPLFile *tdf, void *memory, u32 len);
s32 TPL_GetTexture(TPLFile *tdf, s32 id, GXTexObj *texObj);
void TPL_CloseTPLFile(TPLFile *tdf);
#endif
