#ifndef VCT_PLATFORM_H
#define VCT_PLATFORM_H

#include <SDL.h>

typedef struct {
    float scale;               /* window scale relative to 640x480 */
    int fullscreen;
    int hidden;                /* create hidden window (headless tests) */
    int use_adapter;           /* official GameCube adapter via libusb */
    int use_sdl_gamepads;      /* fallback: any SDL game controller, mapped to ports */
    int demo;                  /* synthetic animated input on port 1 (tests / screenshots) */
    int max_frames;            /* quit after N frames (0 = never) */
    const char *screenshot_path;
    int screenshot_frame;
} vct_options;

extern vct_options g_vct_opts;

void vct_platform_event(const SDL_Event *ev);
void vct_platform_shutdown(void);

/* adapter status for the window title / logs */
const char *vct_input_status(void);

#endif
