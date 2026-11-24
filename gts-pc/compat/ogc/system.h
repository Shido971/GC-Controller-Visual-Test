#ifndef GTS_COMPAT_SYSTEM_H
#define GTS_COMPAT_SYSTEM_H
#include "ogc_compat.h"
#include <stdarg.h>
/* SYS_ResetButtonDown() reports the PC quit request (Esc / closed window / Start+B+X) */
u32 SYS_ResetButtonDown(void);
static inline s32 SYS_MainLoop(void) { return !SYS_ResetButtonDown(); }
static inline void SYS_EnableGecko(s32 chan, bool safe) { (void)chan; (void)safe; }
static inline void SYS_Report(const char *fmt, ...) { (void)fmt; }
static inline void SYS_Reportv(const char *fmt, va_list list) { (void)fmt; (void)list; }
#endif
