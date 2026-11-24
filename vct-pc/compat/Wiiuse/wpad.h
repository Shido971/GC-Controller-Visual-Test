/*
 * Wiiuse/wpad.h - compile-time stand-in for the Wii Remote API.
 *
 * On PC there is no Wii Remote stack: every WPAD_* call reports "no
 * controller", so the Wiimote / Classic / Guitar / Wii U Pro screens of
 * Visual Controller Test are compiled but never reached. Only the field
 * names used by main.c are declared.
 */
#ifndef VCT_COMPAT_WPAD_H
#define VCT_COMPAT_WPAD_H

#include "../ogc_compat.h"

#define WPAD_CHAN_ALL -1
#define WPAD_CHAN_0 0
#define WPAD_CHAN_1 1
#define WPAD_CHAN_2 2
#define WPAD_CHAN_3 3

#define WPAD_ERR_NONE 0
#define WPAD_ERR_NO_CONTROLLER -1

#define WPAD_FMT_BTNS_ACC_IR 2

#define WPAD_DISCON_POWER_OFF 1
#define WPAD_DISCON_SYNC_PRESSED 2

#define WPAD_EXP_NONE 0
#define WPAD_EXP_NUNCHUK 1
#define WPAD_EXP_CLASSIC 2
#define WPAD_EXP_GUITARHERO3 3

#define CLASSIC_TYPE_ORIG 0
#define CLASSIC_TYPE_PRO 1
#define CLASSIC_TYPE_WIIU 2

#define WPAD_BUTTON_2     0x0001
#define WPAD_BUTTON_1     0x0002
#define WPAD_BUTTON_B     0x0004
#define WPAD_BUTTON_A     0x0008
#define WPAD_BUTTON_MINUS 0x0010
#define WPAD_BUTTON_HOME  0x0080
#define WPAD_BUTTON_LEFT  0x0100
#define WPAD_BUTTON_RIGHT 0x0200
#define WPAD_BUTTON_DOWN  0x0400
#define WPAD_BUTTON_UP    0x0800
#define WPAD_BUTTON_PLUS  0x1000

#define WPAD_NUNCHUK_BUTTON_Z (0x0001 << 16)
#define WPAD_NUNCHUK_BUTTON_C (0x0002 << 16)

#define WPAD_CLASSIC_BUTTON_UP     (0x0001 << 16)
#define WPAD_CLASSIC_BUTTON_LEFT   (0x0002 << 16)
#define WPAD_CLASSIC_BUTTON_ZR     (0x0004 << 16)
#define WPAD_CLASSIC_BUTTON_X      (0x0008 << 16)
#define WPAD_CLASSIC_BUTTON_A      (0x0010 << 16)
#define WPAD_CLASSIC_BUTTON_Y      (0x0020 << 16)
#define WPAD_CLASSIC_BUTTON_B      (0x0040 << 16)
#define WPAD_CLASSIC_BUTTON_ZL     (0x0080 << 16)
#define WPAD_CLASSIC_BUTTON_FULL_R (0x0200 << 16)
#define WPAD_CLASSIC_BUTTON_PLUS   (0x0400 << 16)
#define WPAD_CLASSIC_BUTTON_HOME   (0x0800 << 16)
#define WPAD_CLASSIC_BUTTON_MINUS  (0x1000 << 16)
#define WPAD_CLASSIC_BUTTON_FULL_L (0x2000 << 16)
#define WPAD_CLASSIC_BUTTON_DOWN   (0x4000 << 16)
#define WPAD_CLASSIC_BUTTON_RIGHT  (0x8000u << 16)
#define WPAD_WII_U_PRO_BUTTON_RSTICK (0x0001 << 15)
#define WPAD_WII_U_PRO_BUTTON_LSTICK (0x0002 << 15)

#define GUITAR_HERO_3_BUTTON_YELLOW     0x0008
#define GUITAR_HERO_3_BUTTON_GREEN      0x0010
#define GUITAR_HERO_3_BUTTON_BLUE       0x0020
#define GUITAR_HERO_3_BUTTON_RED        0x0040
#define GUITAR_HERO_3_BUTTON_ORANGE     0x0080
#define GUITAR_HERO_3_BUTTON_PLUS       0x0400
#define GUITAR_HERO_3_BUTTON_MINUS      0x1000
#define GUITAR_HERO_3_BUTTON_STRUM_UP   0x0001
#define GUITAR_HERO_3_BUTTON_STRUM_DOWN 0x4000
#define GUITAR_HERO_3_TOUCH_AVAILABLE 0x1000
#define GUITAR_HERO_3_TOUCH_GREEN     0x1001
#define GUITAR_HERO_3_TOUCH_RED       0x1002
#define GUITAR_HERO_3_TOUCH_YELLOW    0x1004
#define GUITAR_HERO_3_TOUCH_BLUE      0x1008
#define GUITAR_HERO_3_TOUCH_ORANGE    0x1010

typedef struct { u8 x, y; } vec2b_t;
typedef struct { float x, y, z; } gforce_t;
typedef struct { u16 x, y, z; } vec3w_t;
typedef struct { float roll, pitch, yaw, a_roll, a_pitch; } orient_t;
typedef struct { vec2b_t max, min, center, pos; float ang, mag; } joystick_t;

typedef struct { joystick_t js; orient_t orient; gforce_t gforce; u32 btns_held; } nunchuk_t;
typedef struct {
    joystick_t ljs, rjs;
    float l_shoulder, r_shoulder;
    int type;
    u8 battery;
    bool charging, wired;
    u32 btns_held;
} classic_ctrl_t;
typedef struct {
    joystick_t js;
    float whammy_bar;
    int touch_bar;
    int tb_raw;
    u16 btns_held;
} guitar_hero_3_t;

typedef struct {
    int type;
    nunchuk_t nunchuk;
    classic_ctrl_t classic;
    guitar_hero_3_t gh3;
} expansion_t;

typedef struct { float sx, sy, x, y, angle; int valid; } ir_t;

typedef struct {
    u32 btns_h, btns_d;
    vec3w_t accel;
    orient_t orient;
    gforce_t gforce;
    ir_t ir;
    expansion_t exp;
    u8 battery_level;
} WPADData;

typedef void (*WPADDisconnectCallback)(s32 chan, u8 reason);

static inline s32 WPAD_Init(void) { return 0; }
static inline s32 WPAD_ScanPads(void) { return 0; }
static inline u32 WPAD_ButtonsDown(int chan) { (void)chan; return 0; }
static inline u32 WPAD_ButtonsHeld(int chan) { (void)chan; return 0; }
static inline s32 WPAD_Probe(int chan, u32 *type) { (void)chan; (void)type; return WPAD_ERR_NO_CONTROLLER; }
static inline void WPAD_Expansion(int chan, expansion_t *e) { (void)chan; *e = (expansion_t){0}; }
static inline WPADData *WPAD_Data(int chan) { static WPADData d; (void)chan; return &d; }
static inline void WPAD_IR(int chan, ir_t *ir) { (void)chan; *ir = (ir_t){0}; }
static inline s32 WPAD_Rumble(int chan, int status) { (void)chan; (void)status; return 0; }
static inline u8 WPAD_BatteryLevel(int chan) { (void)chan; return 0; }
static inline bool WPAD_IsBatteryCritical(int chan) { (void)chan; return false; }
static inline s32 WPAD_PadStatus(int chan) { (void)chan; return 0; }
static inline s32 WPAD_SetVRes(int chan, u32 x, u32 y) { (void)chan; (void)x; (void)y; return 0; }
static inline s32 WPAD_SetDataFormat(int chan, int fmt) { (void)chan; (void)fmt; return 0; }
static inline s32 WPAD_SetIdleTimeout(u32 s) { (void)s; return 0; }
static inline s32 WPAD_SetDisconnectCallback(WPADDisconnectCallback cb) { (void)cb; return 0; }

#endif
