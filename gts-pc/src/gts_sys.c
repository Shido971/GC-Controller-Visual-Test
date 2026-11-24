/*
 * gts_sys.c - time, threads, file system and system stubs for the PC build of GTS.
 * Copyright (C) 2026 Shido971 - GPL-3.0-or-later (linked with GTS, GPL-3.0).
 */
#include <SDL.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#endif

#include "ogc/lwp.h"
#include "ogc/system.h"
#include "ogc/timesupp.h"

/* ----------------------------------------------------------- time */
u64 gettime(void) { return (u64)SDL_GetPerformanceCounter(); }
u32 ticks_to_microsecs(u64 t) { return (u32)(t * 1000000ULL / SDL_GetPerformanceFrequency()); }
u32 ticks_to_millisecs(u64 t) { return (u32)(t * 1000ULL / SDL_GetPerformanceFrequency()); }
u64 diff_usec(u64 a, u64 b) { return (b - a) * 1000000ULL / SDL_GetPerformanceFrequency(); }

/* ----------------------------------------------------------- threads */
typedef struct { void *(*entry)(void *); void *arg; } ThreadStart;

static int SDLCALL thread_tramp(void *p)
{
    ThreadStart ts = *(ThreadStart *)p;
    free(p);
    ts.entry(ts.arg);
    return 0;
}

s32 LWP_CreateThread(lwp_t *th, void *(*entry)(void *), void *arg, void *stack, u32 size, u8 prio)
{
    (void)stack; (void)size; (void)prio;
    ThreadStart *ts = (ThreadStart *)malloc(sizeof *ts);
    ts->entry = entry;
    ts->arg = arg;
    SDL_Thread *t = SDL_CreateThread(thread_tramp, "lwp", ts);
    if (!t) {
        free(ts);
        return -1;
    }
    SDL_DetachThread(t);
    if (th)
        *th = 1;
    return 0;
}

s32 LWP_JoinThread(lwp_t t, void **v) { (void)t; if (v) *v = NULL; return 0; }

/* ----------------------------------------------------------- SD card -> user folder */
static char g_base[1024];

static const char *base_dir(void)
{
    if (!g_base[0]) {
        char *p = SDL_GetPrefPath("PhobGCCTool", "GTS");
        snprintf(g_base, sizeof g_base, "%s", p ? p : "./");
        SDL_free(p);
        size_t n = strlen(g_base);
        if (n && (g_base[n - 1] == '/' || g_base[n - 1] == '\\'))
            g_base[n - 1] = 0;
    }
    return g_base;
}

/* "/GTS/x.csv" or "sd:/GTS/x.csv" -> "<pref path>/GTS/x.csv" */
static void map_path(const char *in, char *out, size_t n)
{
    if (!strncmp(in, "sd:", 3) || !strncmp(in, "fat:", 4))
        in = strchr(in, ':') + 1;
    if (in[0] == '/')
        snprintf(out, n, "%s%s", base_dir(), in);
    else
        snprintf(out, n, "%s", in);
}

#undef fopen
#undef mkdir
FILE *gts_fopen(const char *path, const char *mode)
{
    char p[1536];
    map_path(path, p, sizeof p);
    return fopen(p, mode);
}

int gts_mkdir(const char *path, int mode)
{
    char p[1536];
    map_path(path, p, sizeof p);
#ifdef _WIN32
    (void)mode;
    return _mkdir(p);
#else
    return mkdir(p, (mode_t)mode);
#endif
}

const char *gts_data_dir(void) { return base_dir(); }

/* ----------------------------------------------------------- fat */
#include "fat.h"
bool fatInitDefault(void) { return true; }
void fatDeinit(void) {}
