/*
 * gts_main_pc.c - PC entry point for GTS (GCC Test Suite by greenwave-1).
 * Parses the PC options, then runs the original GTS main() (renamed gts_main).
 * Copyright (C) 2026 Shido971 - GPL-3.0-or-later (linked with GTS, GPL-3.0).
 */
#ifndef __ANDROID__
#define SDL_MAIN_HANDLED   /* on Android SDL_main.h renames main() to SDL_main() */
#endif
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vct_platform.h"

vct_options g_vct_opts = {
    .scale = 1.5f,
#ifdef __ANDROID__
    .fullscreen = 1,
    .use_adapter = 0,
    .use_sdl_gamepads = 0,
#else
    .fullscreen = 0,
    .use_adapter = 1,
    .use_sdl_gamepads = 1,
#endif
    .hidden = 0,
    .demo = 0,
    .max_frames = 0,
    .screenshot_path = NULL,
    .screenshot_frame = 60,
};

int gts_main(int argc, char **argv);
const char *gts_data_dir(void);

static void usage(const char *argv0)
{
    printf("GCC Test Suite (GTS) - PC port\n"
           "usage: %s [options]\n"
           "  --scale N          window scale (default 1.5 = 960x720)\n"
           "  --fullscreen       start fullscreen (F11 / Alt+Enter toggles)\n"
           "  --no-adapter       do not open the official GameCube adapter\n"
           "  --no-sdl-pads      do not use other gamepads as fallback\n"
           "  --demo             synthetic animated input on port 1\n"
           "  --frames N         quit after N frames\n"
           "  --screenshot F     save frame (see --shot-frame) to BMP file F\n"
           "  --shot-frame N     frame number for --screenshot (default 60)\n"
           "  --hidden           hidden window (headless tests)\n"
           "  --menu NAME        open a GTS screen directly (controllertest, oscilloscope,\n"
           "                     2dplot, ... as accepted by GTS)\n"
           "Quit: from the GTS menu, Esc, or close the window.\n"
           "Saved recordings: %s\n",
           argv0, gts_data_dir());
}

int main(int argc, char **argv)
{
    const char *gts_menu = NULL;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *next = (i + 1 < argc) ? argv[i + 1] : NULL;
        if (!strcmp(a, "--scale") && next) { g_vct_opts.scale = (float)atof(next); i++; }
        else if (!strcmp(a, "--fullscreen")) g_vct_opts.fullscreen = 1;
        else if (!strcmp(a, "--no-adapter")) g_vct_opts.use_adapter = 0;
        else if (!strcmp(a, "--no-sdl-pads")) g_vct_opts.use_sdl_gamepads = 0;
        else if (!strcmp(a, "--demo")) g_vct_opts.demo = 1;
        else if (!strcmp(a, "--hidden")) g_vct_opts.hidden = 1;
        else if (!strcmp(a, "--frames") && next) { g_vct_opts.max_frames = atoi(next); i++; }
        else if (!strcmp(a, "--screenshot") && next) { g_vct_opts.screenshot_path = next; i++; }
        else if (!strcmp(a, "--shot-frame") && next) { g_vct_opts.screenshot_frame = atoi(next); i++; }
        else if (!strcmp(a, "--menu") && next) { gts_menu = next; i++; }
        else if (!strcmp(a, "-h") || !strcmp(a, "--help")) { usage(argv[0]); return 0; }
        else { fprintf(stderr, "unknown option: %s\n", a); usage(argv[0]); return 2; }
    }
    if (g_vct_opts.scale < 0.5f || g_vct_opts.scale > 8.0f)
        g_vct_opts.scale = 1.5f;

    SDL_SetMainReady();
    /* GTS's own launch flag (--menu) is forwarded */
    char *gts_argv[4] = { argv[0], NULL, NULL, NULL };
    int gts_argc = 1;
    if (gts_menu) {
        gts_argv[gts_argc++] = (char *)"--menu";
        gts_argv[gts_argc++] = (char *)gts_menu;
    }
    int rc = gts_main(gts_argc, gts_argv);
    vct_platform_shutdown();
    SDL_Quit();
    return rc;
}
