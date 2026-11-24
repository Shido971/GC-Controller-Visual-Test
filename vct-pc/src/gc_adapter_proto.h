/*
 * gc_adapter_proto.h - parser for the WUP-028 input report (37 bytes).
 *
 *   byte 0      : 0x21 (input report)
 *   then 4 x 9  : [status, btn1, btn2, stickX, stickY, cX, cY, L, R]
 *   status      : 0x10 = wired pad, 0x20 = WaveBird, 0x04 = rumble power
 *   btn1        : A 01, B 02, X 04, Y 08, Left 10, Right 20, Down 40, Up 80
 *   btn2        : Start 01, Z 02, R 04, L 08
 */
#ifndef GC_ADAPTER_PROTO_H
#define GC_ADAPTER_PROTO_H

#include <stddef.h>
#include <string.h>
#include "ogc_compat.h"

typedef struct {
    int connected;
    int wireless;
    u16 buttons;            /* PAD_BUTTON_* bits (libogc layout) */
    u8 stick_x, stick_y;    /* raw 0..255, centre ~128 */
    u8 cstick_x, cstick_y;
    u8 trig_l, trig_r;
} gc_port_state;

static inline u16 gc_adapter_map_buttons(u8 b1, u8 b2)
{
    u16 b = 0;
    if (b1 & 0x01) b |= PAD_BUTTON_A;
    if (b1 & 0x02) b |= PAD_BUTTON_B;
    if (b1 & 0x04) b |= PAD_BUTTON_X;
    if (b1 & 0x08) b |= PAD_BUTTON_Y;
    if (b1 & 0x10) b |= PAD_BUTTON_LEFT;
    if (b1 & 0x20) b |= PAD_BUTTON_RIGHT;
    if (b1 & 0x40) b |= PAD_BUTTON_DOWN;
    if (b1 & 0x80) b |= PAD_BUTTON_UP;
    if (b2 & 0x01) b |= PAD_BUTTON_START;
    if (b2 & 0x02) b |= PAD_TRIGGER_Z;
    if (b2 & 0x04) b |= PAD_TRIGGER_R;
    if (b2 & 0x08) b |= PAD_TRIGGER_L;
    return b;
}

/* returns 1 if the report was valid */
static inline int gc_adapter_parse(const unsigned char *d, size_t len, gc_port_state out[4])
{
    if (len < 37 || d[0] != 0x21)
        return 0;
    for (int i = 0; i < 4; i++) {
        const unsigned char *p = d + 1 + 9 * i;
        gc_port_state *s = &out[i];
        memset(s, 0, sizeof *s);
        int type = (p[0] >> 4) & 0x3;
        if (type == 0)
            continue;
        s->connected = 1;
        s->wireless = (type == 2);
        s->buttons = gc_adapter_map_buttons(p[1], p[2]);
        s->stick_x = p[3];
        s->stick_y = p[4];
        s->cstick_x = p[5];
        s->cstick_y = p[6];
        s->trig_l = p[7];
        s->trig_r = p[8];
    }
    return 1;
}

/* raw 0..255 (centre 128) -> libogc signed value */
static inline s8 gc_axis_to_s8(u8 v)
{
    int x = (int)v - 128;
    if (x > 127) x = 127;
    if (x < -128) x = -128;
    return (s8)x;
}

#endif
