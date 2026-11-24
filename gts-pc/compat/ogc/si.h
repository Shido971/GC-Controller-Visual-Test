#ifndef GTS_COMPAT_SI_H
#define GTS_COMPAT_SI_H
#include "ogc_compat.h"
/* the polling rate is set by the USB adapter on PC: accepted and ignored */
static inline u32 SI_SetXY(u16 line, u8 cnt) { (void)line; (void)cnt; return 0; }
#endif
