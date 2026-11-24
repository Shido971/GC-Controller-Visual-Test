#ifndef GTS_COMPAT_DEBUG_H
#define GTS_COMPAT_DEBUG_H
#define GDBSTUB_DEVICE_USB 0
static inline void DEBUG_Init(int device, int port) { (void)device; (void)port; }
static inline void _break(void) {}
#endif
