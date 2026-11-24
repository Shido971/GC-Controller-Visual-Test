#include <assert.h>
#include <stdio.h>
#include "gc_adapter_proto.h"

int main(void)
{
    unsigned char r[37] = { 0x21 };
    /* port 1: wired, A + Start + L, stick right, c-stick down */
    unsigned char *p = r + 1;
    p[0] = 0x14; p[1] = 0x01; p[2] = 0x09;
    p[3] = 0xFF; p[4] = 0x80; p[5] = 0x80; p[6] = 0x00; p[7] = 200; p[8] = 3;
    /* port 3: WaveBird, D-up + Z */
    p = r + 1 + 18;
    p[0] = 0x20; p[1] = 0x80; p[2] = 0x02; p[3] = 0x80; p[4] = 0x80; p[5] = 0x80; p[6] = 0x80;

    gc_port_state s[4];
    assert(gc_adapter_parse(r, sizeof r, s));
    assert(s[0].connected && !s[0].wireless);
    assert(s[0].buttons == (PAD_BUTTON_A | PAD_BUTTON_START | PAD_TRIGGER_L));
    assert(gc_axis_to_s8(s[0].stick_x) == 127);
    assert(gc_axis_to_s8(s[0].stick_y) == 0);
    assert(gc_axis_to_s8(s[0].cstick_y) == -128);
    assert(s[0].trig_l == 200 && s[0].trig_r == 3);
    assert(!s[1].connected);
    assert(s[2].connected && s[2].wireless);
    assert(s[2].buttons == (PAD_BUTTON_UP | PAD_TRIGGER_Z));
    assert(!s[3].connected);

    r[0] = 0x22;
    assert(!gc_adapter_parse(r, sizeof r, s));
    assert(!gc_adapter_parse(r, 10, s));
    puts("adapter_proto: OK");
    return 0;
}
