/*
 * pad_pc.c - libogc PAD_* API for PC.
 *
 * Sources, in priority order:
 *  1. Official Nintendo GameCube adapter for Wii U / Switch (WUP-028,
 *     VID 057E PID 0337) through libusb - same protocol as Dolphin.
 *  2. Optional fallback: SDL game controllers mapped to ports 1-4.
 *  3. --demo: synthetic animated input on port 1.
 *  4. Android (VCT_NO_LIBUSB): the Kotlin side owns the USB connection and
 *     forwards raw 37-byte reports through vct_bridge_report() (JNI).
 */
#include <SDL.h>
#ifndef VCT_NO_LIBUSB
#include <libusb.h>
#endif
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "ogc_compat.h"
#include "vct_platform.h"
#include "gc_adapter_proto.h"

#define GC_VID 0x057E
#define GC_PID 0x0337
#define EP_IN  0x81
#define EP_OUT 0x02

/* ------------------------------------------------------------------ */
/* Shared state                                                        */
/* ------------------------------------------------------------------ */
static gc_port_state g_live[4];      /* written by the USB thread  */
static gc_port_state g_origin[4];    /* first report after connection */
static int g_was_connected[4];
static SDL_SpinLock g_scan_lock = 0;  /* PAD_ScanPads may run on two threads (GTS) */
static volatile sampling_callback g_sampling_cb = NULL;
static gc_port_state g_snap[4];      /* snapshot used by PAD_*     */
static u16 g_prev_held[4];
static u16 g_down[4];
static u8  g_rumble_want[4];

/* spinlock: usable before PAD_Init (the Android bridge may deliver reports early) */
static SDL_SpinLock g_lock = 0;
#define LOCK() SDL_AtomicLock(&g_lock)
#define UNLOCK() SDL_AtomicUnlock(&g_lock)
static SDL_atomic_t g_run;
static SDL_atomic_t g_adapter_ok;
#ifndef VCT_NO_LIBUSB
static SDL_Thread *g_thread = NULL;
static libusb_context *g_usb = NULL;
#endif

static SDL_GameController *g_sdl_pads[4];

/* ------------------------------------------------------------------ */
/* USB adapter thread                                                   */
/* ------------------------------------------------------------------ */
#ifndef VCT_NO_LIBUSB
static libusb_device_handle *adapter_open(void)
{
    libusb_device_handle *h = libusb_open_device_with_vid_pid(g_usb, GC_VID, GC_PID);
    if (!h)
        return NULL;
#if !defined(_WIN32)
    libusb_set_auto_detach_kernel_driver(h, 1);
#endif
    if (libusb_claim_interface(h, 0) != 0) {
        fprintf(stderr, "[adapter] cannot claim interface (driver? another program using it?)\n");
        libusb_close(h);
        return NULL;
    }
    /* Some adapters need a control transfer first (Dolphin does the same). */
    libusb_control_transfer(h, 0x21, 11, 0x0001, 0, NULL, 0, 1000);
    unsigned char init = 0x13;
    int tx = 0;
    libusb_interrupt_transfer(h, EP_OUT, &init, 1, &tx, 1000);
    fprintf(stderr, "[adapter] GameCube adapter connected\n");
    return h;
}

static int SDLCALL adapter_thread(void *unused)
{
    (void)unused;
    libusb_device_handle *h = NULL;
    u8 sent_rumble[4] = { 0xFF, 0xFF, 0xFF, 0xFF };
    unsigned char buf[37];

    while (SDL_AtomicGet(&g_run)) {
        if (!h) {
            h = adapter_open();
            if (!h) {
                SDL_AtomicSet(&g_adapter_ok, 0);
                SDL_Delay(1000);
                continue;
            }
            SDL_AtomicSet(&g_adapter_ok, 1);
            memset(sent_rumble, 0xFF, sizeof sent_rumble);
        }

        int got = 0;
        int r = libusb_interrupt_transfer(h, EP_IN, buf, sizeof buf, &got, 50);
        if (r == LIBUSB_ERROR_NO_DEVICE || r == LIBUSB_ERROR_IO || r == LIBUSB_ERROR_PIPE) {
            fprintf(stderr, "[adapter] disconnected (%s)\n", libusb_error_name(r));
            libusb_close(h);
            h = NULL;
            LOCK();
            memset(g_live, 0, sizeof g_live);
            UNLOCK();
            continue;
        }
        if (r == 0 && got == 37) {
            gc_port_state parsed[4];
            if (gc_adapter_parse(buf, (size_t)got, parsed)) {
                LOCK();
                memcpy(g_live, parsed, sizeof g_live);
                UNLOCK();
                sampling_callback cb = g_sampling_cb;
                if (cb)
                    cb();
            }
        }

        /* rumble */
        u8 want[4];
        LOCK();
        memcpy(want, g_rumble_want, 4);
        UNLOCK();
        if (memcmp(want, sent_rumble, 4) != 0) {
            unsigned char cmd[5] = { 0x11, want[0], want[1], want[2], want[3] };
            int tx = 0;
            if (libusb_interrupt_transfer(h, EP_OUT, cmd, 5, &tx, 50) == 0)
                memcpy(sent_rumble, want, 4);
        }
    }

    if (h) {
        unsigned char stop[5] = { 0x11, 0, 0, 0, 0 };
        int tx = 0;
        libusb_interrupt_transfer(h, EP_OUT, stop, 5, &tx, 100);
        libusb_release_interface(h, 0);
        libusb_close(h);
    }
    return 0;
}
#endif /* VCT_NO_LIBUSB */

/* Raw report pushed by the host application (Android/JNI). len < 37 = adapter gone.
   Returns the rumble bitmask (bit n = port n) the game currently wants. */
int vct_bridge_report(const unsigned char *data, int len)
{
    gc_port_state parsed[4];
    int ok = data && len >= 37 && gc_adapter_parse(data, (size_t)len, parsed);
    if (!ok)
        memset(parsed, 0, sizeof parsed);
    LOCK();
    memcpy(g_live, parsed, sizeof g_live);
    int mask = 0;
    for (int i = 0; i < 4; i++)
        mask |= (g_rumble_want[i] ? 1 : 0) << i;
    UNLOCK();
    SDL_AtomicSet(&g_adapter_ok, ok);
    sampling_callback cb = g_sampling_cb;
    if (cb)
        cb();
    return mask;
}

sampling_callback PAD_SetSamplingCallback(sampling_callback cb)
{
    sampling_callback old = g_sampling_cb;
    g_sampling_cb = cb;
    return old;
}

/* Lets the host loop drive the callback when no adapter thread does (demo, SDL pads). */
void vct_pad_frame_tick(void)
{
    sampling_callback cb = g_sampling_cb;
    if (cb && !SDL_AtomicGet(&g_adapter_ok))
        cb();
}

u32 PAD_GetOrigin(PADStatus *origin)
{
    if (!origin)
        return 0;
    for (int i = 0; i < 4; i++) {
        PADStatus *o = &origin[i];
        memset(o, 0, sizeof *o);
        if (!g_snap[i].connected) {
            o->err = PAD_ERR_NO_CONTROLLER;
            continue;
        }
        o->stickX = gc_axis_to_s8(g_origin[i].stick_x);
        o->stickY = gc_axis_to_s8(g_origin[i].stick_y);
        o->substickX = gc_axis_to_s8(g_origin[i].cstick_x);
        o->substickY = gc_axis_to_s8(g_origin[i].cstick_y);
        o->triggerL = g_origin[i].trig_l;
        o->triggerR = g_origin[i].trig_r;
        o->err = PAD_ERR_NONE;
    }
    return 1;
}

/* ------------------------------------------------------------------ */
/* SDL game controller fallback                                         */
/* ------------------------------------------------------------------ */
static u8 axis_to_u8(Sint16 v, int invert)
{
    int x = v / 256 + 128;
    if (invert)
        x = 256 - x;
    if (x < 0) x = 0;
    if (x > 255) x = 255;
    return (u8)x;
}

static void sdl_pads_refresh(void)
{
    for (int i = 0; i < 4; i++) {
        if (g_sdl_pads[i] && !SDL_GameControllerGetAttached(g_sdl_pads[i])) {
            SDL_GameControllerClose(g_sdl_pads[i]);
            g_sdl_pads[i] = NULL;
        }
    }
    int slot = 0;
    for (int j = 0; j < SDL_NumJoysticks() && slot < 4; j++) {
        if (!SDL_IsGameController(j))
            continue;
        SDL_JoystickID id = SDL_JoystickGetDeviceInstanceID(j);
        int already = 0;
        for (int i = 0; i < 4; i++)
            if (g_sdl_pads[i] && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(g_sdl_pads[i])) == id)
                already = 1;
        if (already)
            continue;
        while (slot < 4 && g_sdl_pads[slot])
            slot++;
        if (slot < 4)
            g_sdl_pads[slot] = SDL_GameControllerOpen(j);
    }
}

static void sdl_pad_read(int i, gc_port_state *s)
{
    SDL_GameController *c = g_sdl_pads[i];
    memset(s, 0, sizeof *s);
    if (!c)
        return;
    s->connected = 1;
    s->wireless = 0;
#define B(btn) SDL_GameControllerGetButton(c, SDL_CONTROLLER_BUTTON_##btn)
    u16 b = 0;
    if (B(A)) b |= PAD_BUTTON_A;
    if (B(B)) b |= PAD_BUTTON_B;
    if (B(X)) b |= PAD_BUTTON_X;
    if (B(Y)) b |= PAD_BUTTON_Y;
    if (B(START)) b |= PAD_BUTTON_START;
    if (B(RIGHTSHOULDER)) b |= PAD_TRIGGER_Z;
    if (B(DPAD_UP)) b |= PAD_BUTTON_UP;
    if (B(DPAD_DOWN)) b |= PAD_BUTTON_DOWN;
    if (B(DPAD_LEFT)) b |= PAD_BUTTON_LEFT;
    if (B(DPAD_RIGHT)) b |= PAD_BUTTON_RIGHT;
#undef B
    Sint16 lt = SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_TRIGGERLEFT);
    Sint16 rt = SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_TRIGGERRIGHT);
    s->trig_l = (u8)(lt / 128);
    s->trig_r = (u8)(rt / 128);
    if (lt > 30000) b |= PAD_TRIGGER_L;
    if (rt > 30000) b |= PAD_TRIGGER_R;
    s->buttons = b;
    s->stick_x = axis_to_u8(SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_LEFTX), 0);
    s->stick_y = axis_to_u8(SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_LEFTY), 1);
    s->cstick_x = axis_to_u8(SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_RIGHTX), 0);
    s->cstick_y = axis_to_u8(SDL_GameControllerGetAxis(c, SDL_CONTROLLER_AXIS_RIGHTY), 1);
}

/* ------------------------------------------------------------------ */
/* Demo input (tests / screenshots without hardware)                     */
/* ------------------------------------------------------------------ */
static void demo_read(gc_port_state *s)
{
    double t = SDL_GetTicks() / 1000.0;
    memset(s, 0, sizeof *s);
    s->connected = 1;
    s->stick_x = (u8)(128 + 100 * cos(t * 2.0));
    s->stick_y = (u8)(128 + 100 * sin(t * 2.0));
    s->cstick_x = (u8)(128 + 80 * sin(t * 1.3));
    s->cstick_y = (u8)(128 + 80 * cos(t * 1.7));
    s->trig_l = (u8)(127 + 127 * sin(t));
    s->trig_r = (u8)(127 - 127 * sin(t));
    u16 b = PAD_BUTTON_A | PAD_BUTTON_Y | PAD_BUTTON_UP;
    if (((int)(t * 2)) & 1)
        b |= PAD_BUTTON_B | PAD_TRIGGER_Z;
    s->buttons = b;
}

/* ------------------------------------------------------------------ */
/* libogc API                                                            */
/* ------------------------------------------------------------------ */
u32 PAD_Init(void)
{
    SDL_AtomicSet(&g_run, 1);
#ifndef VCT_NO_LIBUSB
    SDL_AtomicSet(&g_adapter_ok, 0);
    if (g_vct_opts.use_adapter) {
        if (libusb_init(&g_usb) == 0) {
            g_thread = SDL_CreateThread(adapter_thread, "gc-adapter", NULL);
        } else {
            fprintf(stderr, "[adapter] libusb_init failed\n");
            g_usb = NULL;
        }
    }
#endif
    if (g_vct_opts.use_sdl_gamepads)
        sdl_pads_refresh();
    return 1;
}

u32 PAD_ScanPads(void)
{
    SDL_AtomicLock(&g_scan_lock);
    gc_port_state cur[4];
    LOCK();
    memcpy(cur, g_live, sizeof cur);
    UNLOCK();

    int adapter = SDL_AtomicGet(&g_adapter_ok);
    for (int i = 0; i < 4; i++) {
        if (!adapter && g_vct_opts.use_sdl_gamepads && g_sdl_pads[i])
            sdl_pad_read(i, &cur[i]);
    }
    if (g_vct_opts.demo)
        demo_read(&cur[0]);

    u32 mask = 0;
    for (int i = 0; i < 4; i++) {
        if (cur[i].connected && !g_was_connected[i])
            g_origin[i] = cur[i];
        g_was_connected[i] = cur[i].connected;
        g_snap[i] = cur[i];
        u16 held = cur[i].connected ? cur[i].buttons : 0;
        g_down[i] = held & (u16)~g_prev_held[i];
        g_prev_held[i] = held;
        if (cur[i].connected)
            mask |= 1u << i;
    }
    SDL_AtomicUnlock(&g_scan_lock);
    return mask;
}

static int valid(int p) { return p >= 0 && p < 4 && g_snap[p].connected; }

u16 PAD_ButtonsHeld(int p) { return valid(p) ? g_snap[p].buttons : 0; }
u16 PAD_ButtonsDown(int p) { return (p >= 0 && p < 4) ? g_down[p] : 0; }
s8 PAD_StickX(int p)    { return valid(p) ? gc_axis_to_s8(g_snap[p].stick_x) : 0; }
s8 PAD_StickY(int p)    { return valid(p) ? gc_axis_to_s8(g_snap[p].stick_y) : 0; }
s8 PAD_SubStickX(int p) { return valid(p) ? gc_axis_to_s8(g_snap[p].cstick_x) : 0; }
s8 PAD_SubStickY(int p) { return valid(p) ? gc_axis_to_s8(g_snap[p].cstick_y) : 0; }
u8 PAD_TriggerL(int p)  { return valid(p) ? g_snap[p].trig_l : 0; }
u8 PAD_TriggerR(int p)  { return valid(p) ? g_snap[p].trig_r : 0; }
int PAD_GetType(int p)  { return (valid(p) && g_snap[p].wireless) ? 1 : 0; }

void PAD_ControlMotor(int p, u32 cmd)
{
    if (p < 0 || p > 3)
        return;
    u8 v = (cmd == PAD_MOTOR_RUMBLE) ? 1 : 0;   /* STOP and STOP_HARD both stop */
    if (g_vct_opts.use_sdl_gamepads && g_sdl_pads[p] && !SDL_AtomicGet(&g_adapter_ok))
        SDL_GameControllerRumble(g_sdl_pads[p], v ? 0xC000 : 0, v ? 0xC000 : 0, v ? 100 : 0);
    LOCK();
    g_rumble_want[p] = v;
    UNLOCK();
}

s32 PAD_KeyboardDown(int p, u8 *keys) { (void)p; (void)keys; return 0; }
s32 PAD_KeyboardHeld(int p, u8 *keys) { (void)p; (void)keys; return 0; }

/* ------------------------------------------------------------------ */
void vct_platform_event(const SDL_Event *ev)
{
    if (!g_vct_opts.use_sdl_gamepads)
        return;
    if (ev->type == SDL_CONTROLLERDEVICEADDED || ev->type == SDL_CONTROLLERDEVICEREMOVED)
        sdl_pads_refresh();
}

const char *vct_input_status(void)
{
    if (SDL_AtomicGet(&g_adapter_ok))
        return "adaptateur GameCube";
    return g_vct_opts.use_sdl_gamepads ? "manettes SDL (adaptateur absent)" : "adaptateur absent";
}

void vct_platform_shutdown(void)
{
    static int done = 0;
    if (done)
        return;
    done = 1;
    SDL_AtomicSet(&g_run, 0);
#ifndef VCT_NO_LIBUSB
    if (g_thread)
        SDL_WaitThread(g_thread, NULL);
    g_thread = NULL;
    if (g_usb)
        libusb_exit(g_usb);
    g_usb = NULL;
#endif
    for (int i = 0; i < 4; i++)
        if (g_sdl_pads[i])
            SDL_GameControllerClose(g_sdl_pads[i]);
}
