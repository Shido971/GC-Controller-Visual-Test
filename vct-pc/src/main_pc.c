/*
 * main_pc.c - PC entry point. Parses options, then runs the original
 * Visual Controller Test main() (compiled with -Dmain=vct_main).
 */
#ifndef __ANDROID__
#define SDL_MAIN_HANDLED  /* on Android, SDL_main.h renames main() to SDL_main() */
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
    .hidden = 0,
    .use_adapter = 0,       /* fed by the Kotlin side through JNI */
    .use_sdl_gamepads = 0,  /* keep SDL's HIDAPI away from the adapter */
#else
    .fullscreen = 0,
    .hidden = 0,
    .use_adapter = 1,
    .use_sdl_gamepads = 1,
#endif
    .demo = 0,
    .max_frames = 0,
    .screenshot_path = NULL,
    .screenshot_frame = 60,
};

int vct_main(void);

static void usage(const char *argv0)
{
    printf("Visual Controller Test - PC port\n"
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
           "Quit: Start+B+X on the controller, Esc, or close the window.\n",
           argv0);
}

int main(int argc, char **argv)
{
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
        else if (!strcmp(a, "-h") || !strcmp(a, "--help")) { usage(argv[0]); return 0; }
        else { fprintf(stderr, "unknown option: %s\n", a); usage(argv[0]); return 2; }
    }
    if (g_vct_opts.scale < 0.5f || g_vct_opts.scale > 8.0f)
        g_vct_opts.scale = 1.5f;

    SDL_SetMainReady();
    int rc = vct_main();
    vct_platform_shutdown();
    SDL_Quit();
    return rc;
}
