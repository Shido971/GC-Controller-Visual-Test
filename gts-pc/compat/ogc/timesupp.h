#ifndef GTS_COMPAT_TIMESUPP_H
#define GTS_COMPAT_TIMESUPP_H
#include "ogc_compat.h"
/* monotonic high-resolution clock (SDL performance counter) */
u64 gettime(void);
u32 ticks_to_microsecs(u64 ticks);
u32 ticks_to_millisecs(u64 ticks);
u64 diff_usec(u64 start, u64 end);
#endif
