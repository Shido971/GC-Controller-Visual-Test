/* malloc.h - memalign() for platforms that lack it (MinGW); alignment is irrelevant on PC */
#ifndef GTS_COMPAT_MALLOC_H
#define GTS_COMPAT_MALLOC_H
#include <stdlib.h>
static inline void *gts_memalign(size_t align, size_t size) { (void)align; return malloc(size); }
#define memalign gts_memalign
#endif
