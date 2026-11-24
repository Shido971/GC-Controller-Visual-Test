package fr.phobtool.usb

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Recherche de périphériques USB et demande de permission. */
object UsbAccess {
    private const val ACTION = "fr.phobtool.USB_PERMISSION"
    private val pending = HashSet<String>()

    fun manager(ctx: Context) = ctx.getSystemService(Context.USB_SERVICE) as UsbManager

    fun find(ctx: Context, pred: (UsbDevice) -> Boolean): UsbDevice? =
        manager(ctx).deviceList.values.firstOrNull(pred)

    /** Demande la permission (asynchrone). Le callback est appelé sur le thread principal. */
    fun request(ctx: Context, device: UsbDevice, cb: (Boolean) -> Unit) {
        val m = manager(ctx)
        if (m.hasPermission(device)) { cb(true); return }
        val app = ctx.applicationContext
        Handler(Looper.getMainLooper()).post {
            synchronized(pending) {
                if (!pending.add(device.deviceName)) return@post
            }
            val receiver = object : BroadcastReceiver() {
                override fun onReceive(c: Context, intent: Intent) {
                    if (intent.action != ACTION) return
                    try { app.unregisterReceiver(this) } catch (_: Exception) {}
                    synchronized(pending) { pending.remove(device.deviceName) }
                    cb(intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false) || m.hasPermission(device))
                }
            }
            val filter = IntentFilter(ACTION)
            if (Build.VERSION.SDK_INT >= 33) app.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
            else app.registerReceiver(receiver, filter)
            var flags = PendingIntent.FLAG_UPDATE_CURRENT
            if (Build.VERSION.SDK_INT >= 31) flags = flags or PendingIntent.FLAG_MUTABLE
            val pi = PendingIntent.getBroadcast(app, device.deviceId, Intent(ACTION).setPackage(app.packageName), flags)
            m.requestPermission(device, pi)
        }
    }

    /** Version bloquante pour les threads de travail. */
    fun requestBlocking(ctx: Context, device: UsbDevice, timeoutS: Long = 120): Boolean {
        if (manager(ctx).hasPermission(device)) return true
        val latch = CountDownLatch(1)
        var ok = false
        request(ctx, device) { ok = it; latch.countDown() }
        latch.await(timeoutS, TimeUnit.SECONDS)
        return ok
    }
}
