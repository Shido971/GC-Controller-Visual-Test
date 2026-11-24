#ifndef GTS_COMPAT_VIDEO_H
#define GTS_COMPAT_VIDEO_H
#include "gx.h"
#include "video_types.h"
typedef void (*VIRetraceCallback)(u32 retraceCnt);
void VIDEO_Init(void);
GXRModeObj *VIDEO_GetPreferredMode(GXRModeObj *mode);
void VIDEO_Configure(GXRModeObj *rmode);
void VIDEO_ClearFrameBuffer(GXRModeObj *rmode, void *fb, u32 color);
void VIDEO_SetNextFramebuffer(void *fb);
void VIDEO_SetBlack(bool black);
void VIDEO_Flush(void);
void VIDEO_WaitForFlush(void);
void VIDEO_WaitVSync(void);
void VIDEO_WaitForRetrace(u32 retraceCount);
u32 VIDEO_GetRetraceCount(void);
u32 VIDEO_GetScanMode(void);
u32 VIDEO_GetCurrentTvMode(void);
VIRetraceCallback VIDEO_SetPostRetraceCallback(VIRetraceCallback callback);
void *SYS_AllocateFramebuffer(GXRModeObj *rmode);
#define MEM_K0_TO_K1(x) (x)
#endif
