/*
 * ogc_compat.h - minimal libogc surface used by Visual Controller Test,
 * re-implemented for PC (SDL2 + official GameCube adapter via libusb).
 */
#ifndef OGC_COMPAT_H
#define OGC_COMPAT_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef uint8_t  u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t   s8;
typedef int16_t  s16;
typedef int32_t  s32;
typedef int64_t  s64;
typedef float    f32;

/* ---------------- GameCube pad (PAD_*) ---------------- */
#define PAD_CHAN0 0
#define PAD_CHAN1 1
#define PAD_CHAN2 2
#define PAD_CHAN3 3

/* Same bit layout as libogc */
#define PAD_BUTTON_LEFT   0x0001
#define PAD_BUTTON_RIGHT  0x0002
#define PAD_BUTTON_DOWN   0x0004
#define PAD_BUTTON_UP     0x0008
#define PAD_TRIGGER_Z     0x0010
#define PAD_TRIGGER_R     0x0020
#define PAD_TRIGGER_L     0x0040
#define PAD_BUTTON_A      0x0100
#define PAD_BUTTON_B      0x0200
#define PAD_BUTTON_X      0x0400
#define PAD_BUTTON_Y      0x0800
#define PAD_BUTTON_START  0x1000

u32 PAD_Init(void);
u32 PAD_ScanPads(void);
u16 PAD_ButtonsHeld(int pad);
u16 PAD_ButtonsDown(int pad);
s8  PAD_StickX(int pad);
s8  PAD_StickY(int pad);
s8  PAD_SubStickX(int pad);
s8  PAD_SubStickY(int pad);
u8  PAD_TriggerL(int pad);
u8  PAD_TriggerR(int pad);
void PAD_ControlMotor(int pad, u32 cmd);
/* 0 = wired controller, 1 = WaveBird (matches CON_TYPE_* ordering in main.c) */
int PAD_GetType(int pad);
/* GameCube ASCII keyboard: not available through the USB adapter */
s32 PAD_KeyboardDown(int pad, u8 *keys);
s32 PAD_KeyboardHeld(int pad, u8 *keys);

/* ---------------- System / video stubs ---------------- */
#define SYS_POWEROFF 4
typedef void (*powercallback)(void);
typedef void (*resetcallback)(u32 irq, void *ctx);
static inline powercallback SYS_SetPowerCallback(powercallback cb) { (void)cb; return NULL; }
static inline resetcallback SYS_SetResetCallback(resetcallback cb) { (void)cb; return NULL; }
static inline void SYS_ResetSystem(s32 r, u32 t, s32 f) { (void)r; (void)t; (void)f; }

#define CONF_ASPECT_4_3  0
#define CONF_ASPECT_16_9 1
static inline s32 CONF_GetAspectRatio(void) { return CONF_ASPECT_4_3; }
static inline void GX_SetViewport(f32 x, f32 y, f32 w, f32 h, f32 n, f32 f)
{ (void)x; (void)y; (void)w; (void)h; (void)n; (void)f; }

static inline void __exception_setreload(int t) { (void)t; }

#ifdef __cplusplus
}
#endif
#endif
