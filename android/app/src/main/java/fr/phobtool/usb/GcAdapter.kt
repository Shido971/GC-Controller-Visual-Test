package fr.phobtool.usb

import android.content.Context
import android.hardware.usb.UsbConstants
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbEndpoint
import android.hardware.usb.UsbInterface
import android.os.SystemClock
import fr.phobtool.core.PadState
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Lecture de l'adaptateur GameCube officiel (WUP-028, VID 057E PID 0337) par l'API USB host,
 * comme Dolphin Android. Les callbacks sont appelés sur le thread de lecture.
 */
class GcAdapter(context: Context) {
    companion object {
        const val VID = 0x057E
        const val PID = 0x0337
        fun isAdapter(d: UsbDevice) = d.vendorId == VID && d.productId == PID
    }

    fun interface Listener {
        /** pads = null quand l'adaptateur n'est pas disponible ; raw = rapport brut de 37 octets */
        fun onReport(pads: List<PadState>?, status: String, raw: ByteArray?)
    }

    private val ctx = context.applicationContext
    private val listeners = CopyOnWriteArrayList<Listener>()
    @Volatile private var running = false
    private var thread: Thread? = null
    private val rumble = IntArray(4)
    @Volatile var status: String = "Adaptateur GameCube non détecté"
        private set

    fun addListener(l: Listener) { listeners += l }
    fun removeListener(l: Listener) { listeners -= l }
    fun setRumble(port: Int, on: Boolean) = synchronized(rumble) { rumble[port] = if (on) 1 else 0 }
    fun setRumbleMask(mask: Int) = synchronized(rumble) { for (i in 0..3) rumble[i] = (mask shr i) and 1 }
    val isRunning get() = running

    private fun emit(p: List<PadState>?, s: String, raw: ByteArray?) {
        status = s
        for (l in listeners) l.onReport(p, s, raw)
    }

    fun start() {
        if (running) return
        running = true
        thread = Thread({ loop() }, "gc-adapter").also { it.isDaemon = true; it.start() }
    }

    /** Libère complètement l'adaptateur (avant de lancer VCT). */
    fun stop() {
        running = false
        thread?.join(1500)
        thread = null
    }

    private class Open(val conn: UsbDeviceConnection, val itf: UsbInterface, val inEp: UsbEndpoint, val outEp: UsbEndpoint?)

    private fun open(dev: UsbDevice): Open? {
        val m = UsbAccess.manager(ctx)
        if (!m.hasPermission(dev)) {
            emit(null, "Autorise l'accès à l'adaptateur (fenêtre Android)", null)
            if (!UsbAccess.requestBlocking(ctx, dev, 60)) {
                emit(null, "Accès à l'adaptateur refusé", null); return null
            }
        }
        val itf = dev.getInterface(0)
        var inEp: UsbEndpoint? = null
        var outEp: UsbEndpoint? = null
        for (i in 0 until itf.endpointCount) {
            val e = itf.getEndpoint(i)
            if (e.direction == UsbConstants.USB_DIR_IN) inEp = e else outEp = e
        }
        if (inEp == null) { emit(null, "Adaptateur : endpoint introuvable", null); return null }
        val conn = m.openDevice(dev) ?: run { emit(null, "Impossible d'ouvrir l'adaptateur", null); return null }
        if (!conn.claimInterface(itf, true)) {
            conn.close(); emit(null, "Adaptateur déjà utilisé par une autre appli (Dolphin ?)", null); return null
        }
        conn.controlTransfer(0x21, 11, 0x0001, 0, null, 0, 1000)
        if (outEp != null) conn.bulkTransfer(outEp, byteArrayOf(0x13), 1, 1000)
        return Open(conn, itf, inEp, outEp)
    }

    private fun close(o: Open) {
        try {
            if (o.outEp != null) o.conn.bulkTransfer(o.outEp, byteArrayOf(0x11, 0, 0, 0, 0), 5, 100)
            o.conn.releaseInterface(o.itf)
        } catch (_: Exception) {}
        o.conn.close()
    }

    private fun loop() {
        var o: Open? = null
        val buf = ByteArray(37)
        var sent: IntArray? = null
        var errors = 0
        var lastAbsent = false
        while (running) {
            if (o == null) {
                val dev = UsbAccess.find(ctx, ::isAdapter)
                if (dev == null) {
                    if (!lastAbsent) emit(null, "Adaptateur GameCube non détecté (OTG)", null)
                    lastAbsent = true
                    SystemClock.sleep(700); continue
                }
                lastAbsent = false
                o = open(dev)
                if (o == null) { SystemClock.sleep(1500); continue }
                sent = null; errors = 0
            }
            val n = o.conn.bulkTransfer(o.inEp, buf, buf.size, 100)
            val t = SystemClock.elapsedRealtimeNanos() / 1e9
            if (n == 37) {
                errors = 0
                val pads = PadState.parseReport(buf, n, t)
                if (pads != null) emit(pads, "Adaptateur connecté", buf.copyOf())
            } else if (n < 0) {
                // timeout ou débranchement : on vérifie que l'appareil est toujours là
                if (++errors > 20 && UsbAccess.find(ctx, ::isAdapter) == null) {
                    close(o); o = null; emit(null, "Adaptateur débranché", null); continue
                }
            }
            val want = synchronized(rumble) { rumble.copyOf() }
            if (o.outEp != null && (sent == null || !want.contentEquals(sent))) {
                val cmd = byteArrayOf(0x11, want[0].toByte(), want[1].toByte(), want[2].toByte(), want[3].toByte())
                if (o.conn.bulkTransfer(o.outEp, cmd, 5, 50) >= 0) sent = want
            }
        }
        o?.let { close(it) }
    }
}
