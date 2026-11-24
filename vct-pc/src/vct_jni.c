/*
 * vct_jni.c - Android bridge: the Kotlin GcAdapter forwards raw WUP-028
 * reports to the PAD_* layer (see VctBridge.kt).
 */
#include <jni.h>

int vct_bridge_report(const unsigned char *data, int len);

JNIEXPORT jint JNICALL
Java_fr_phobtool_vct_VctBridge_nativeReport(JNIEnv *env, jclass cls, jbyteArray arr)
{
    (void)cls;
    if (!arr)
        return vct_bridge_report(NULL, 0);
    jsize len = (*env)->GetArrayLength(env, arr);
    jbyte *data = (*env)->GetByteArrayElements(env, arr, NULL);
    if (!data)
        return 0;
    int mask = vct_bridge_report((const unsigned char *)data, (int)len);
    (*env)->ReleaseByteArrayElements(env, arr, data, JNI_ABORT);
    return mask;
}
