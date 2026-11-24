#ifndef GTS_COMPAT_LWP_H
#define GTS_COMPAT_LWP_H
#include "ogc_compat.h"
typedef u32 lwp_t;
#define LWP_THREAD_NULL 0xffffffff
#define LWP_PRIO_NORMAL 64
#define LWP_PRIO_HIGHEST 127
s32 LWP_CreateThread(lwp_t *thethread, void *(*entry)(void *), void *arg, void *stackbase, u32 stack_size, u8 prio);
s32 LWP_JoinThread(lwp_t thethread, void **value_ptr);
#endif
