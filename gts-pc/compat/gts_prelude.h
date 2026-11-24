/*
 * gts_prelude.h - force-included before every GTS source file.
 *  - main() becomes gts_main() (gts_main_pc.c provides the real entry point);
 *    a force-included header wins over SDL's "-Dmain=SDL_main" on Windows.
 *  - SD-card paths ("/GTS/...") are redirected to a per-user data folder.
 */
#ifndef GTS_PRELUDE_H
#define GTS_PRELUDE_H
#include <stdio.h>
#include <sys/stat.h>
#include <sys/types.h>

#undef main
#define main gts_main

FILE *gts_fopen(const char *path, const char *mode);
int gts_mkdir(const char *path, int mode);
#define fopen(p, m) gts_fopen((p), (m))
#define mkdir(p, m) gts_mkdir((p), (m))
#endif
