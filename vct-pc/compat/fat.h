/* fat.h - no SD card on PC; nothing needed. */
#ifndef VCT_COMPAT_FAT_H
#define VCT_COMPAT_FAT_H
static inline int fatInitDefault(void) { return 1; }
#endif
