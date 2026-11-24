/* malloc.h - forwards to the system header; adds memalign() where it is missing (MinGW).
   Alignment is irrelevant on PC. Bionic declares free/realloc here, so the real header must be kept. */
#ifndef GTS_COMPAT_MALLOC_H
#define GTS_COMPAT_MALLOC_H
#include_next <malloc.h>
#include <stdlib.h>
#ifdef _WIN32
static inline void *gts_memalign(size_t align, size_t size) { (void)align; return malloc(size); }
#define memalign gts_memalign
#endif
#endif
