/* fat.h - the "SD card" is a folder in the user's application data on PC (see gts_sys.c) */
#ifndef GTS_COMPAT_FAT_H
#define GTS_COMPAT_FAT_H
#include <stdbool.h>
bool fatInitDefault(void);
void fatDeinit(void);
#endif
