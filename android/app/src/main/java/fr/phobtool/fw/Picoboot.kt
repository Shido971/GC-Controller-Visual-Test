package fr.phobtool.fw

import android.hardware.usb.UsbConstants
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbEndpoint
import android.hardware.usb.UsbInterface
import android.hardware.usb.UsbManager
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Protocole PICOBOOT du bootrom RP2040 (mode BOOTSEL, VID 2E8A PID 0003),
 * d'après pico-sdk boot/picoboot.h et picotool picoboot_connection.c.
 * Évite d'avoir à monter le lecteur RPI-RP2 sur le téléphone.
 */
object PicobootProto {
    const val VID = 0x2E8A
    const val PID_RP2040_BOOT = 0x0003
    const val MAGIC = 0x431FD10BL
    const val IF_RESET = 0x41
    const val PC_EXCLUSIVE_ACCESS = 0x01
    const val PC_REBOOT = 0x02
    const val PC_FLASH_ERASE = 0x03
    const val PC_READ = 0x84
    const val PC_WRITE = 0x05
    const val PC_EXIT_XIP = 0x06
    const val EXCLUSIVE = 1
    const val NOT_EXCLUSIVE = 0
    const val SRAM_END_RP2040 = 0x20042000L

    /** Commande de 32 octets (little-endian). */
    fun command(token: Int, id: Int, args: ByteArray, transferLength: Int): ByteArray {
        require(args.size <= 16)
        val b = ByteBuffer.allocate(32).order(ByteOrder.LITTLE_ENDIAN)
        b.putInt(MAGIC.toInt())
        b.putInt(token)
        b.put(id.toByte())
        b.put(args.size.toByte())
        b.putShort(0)
        b.putInt(transferLength)
        b.put(args)
        return b.array()
    }

    fun u32s(vararg v: Long): ByteArray {
        val b = ByteBuffer.allocate(4 * v.size).order(ByteOrder.LITTLE_ENDIAN)
        v.forEach { b.putInt(it.toInt()) }
        return b.array()
    }
}

class PicobootDevice private constructor(
    private val conn: UsbDeviceConnection,
    private val intf: UsbInterface,
    private val epOut: UsbEndpoint,
    private val epIn: UsbEndpoint,
) : AutoCloseable {
    private var token = 1

    companion object {
        fun isBootrom(d: UsbDevice) = d.vendorId == PicobootProto.VID && d.productId == PicobootProto.PID_RP2040_BOOT

        fun open(manager: UsbManager, device: UsbDevice): PicobootDevice {
            var found: Triple<UsbInterface, UsbEndpoint, UsbEndpoint>? = null
            for (i in 0 until device.interfaceCount) {
                val itf = device.getInterface(i)
                if (itf.interfaceClass != 0xFF || itf.endpointCount != 2) continue
                var o: UsbEndpoint? = null
                var inn: UsbEndpoint? = null
                for (e in 0 until itf.endpointCount) {
                    val ep = itf.getEndpoint(e)
                    if (ep.type != UsbConstants.USB_ENDPOINT_XFER_BULK) continue
                    if (ep.direction == UsbConstants.USB_DIR_OUT) o = ep else inn = ep
                }
                if (o != null && inn != null) { found = Triple(itf, o, inn); break }
            }
            val (itf, o, inn) = found ?: throw FirmwareException("interface PICOBOOT introuvable sur le RP2040")
            val c = manager.openDevice(device) ?: throw FirmwareException("impossible d'ouvrir le RP2040 (permission ?)")
            if (!c.claimInterface(itf, true)) {
                c.close(); throw FirmwareException("impossible de réserver l'interface PICOBOOT")
            }
            return PicobootDevice(c, itf, o, inn)
        }
    }

    fun reset() {
        val r = conn.controlTransfer(0x41, PicobootProto.IF_RESET, 0, intf.id, null, 0, 1000)
        if (r < 0) throw FirmwareException("reset PICOBOOT refusé")
    }

    // bulkTransfer avec offset n'existe qu'à partir d'Android 9 : on passe par un tampon (minSdk 24)
    private fun bulkOut(data: ByteArray, len: Int, timeout: Int): Int {
        var off = 0
        while (off < len) {
            val n = minOf(16384, len - off)
            val chunk = if (off == 0 && n == data.size) data else data.copyOfRange(off, off + n)
            val r = conn.bulkTransfer(epOut, chunk, n, timeout)
            if (r < 0) return r
            off += r
            if (r == 0) break
        }
        return off
    }

    private fun bulkIn(buf: ByteArray, len: Int, timeout: Int): Int {
        var off = 0
        val tmp = ByteArray(16384)
        while (off < len) {
            val r = conn.bulkTransfer(epIn, tmp, minOf(16384, len - off), timeout)
            if (r <= 0) return if (off > 0) off else r
            System.arraycopy(tmp, 0, buf, off, r)
            off += r
        }
        return off
    }

    /** Envoi d'une commande + phase de données + acquittement dans le sens opposé (comme picotool). */
    private fun cmd(id: Int, args: ByteArray, data: ByteArray? = null, inLen: Int = 0): ByteArray? {
        val isIn = id and 0x80 != 0
        val tl = if (isIn) inLen else (data?.size ?: 0)
        val c = PicobootProto.command(token++, id, args, tl)
        if (bulkOut(c, c.size, 3000) != c.size) throw FirmwareException("commande 0x${id.toString(16)} non envoyée")
        val timeout = 10000
        var result: ByteArray? = null
        if (tl > 0) {
            if (isIn) {
                val buf = ByteArray(tl)
                if (bulkIn(buf, tl, timeout) != tl) throw FirmwareException("lecture 0x${id.toString(16)} incomplète")
                result = buf
            } else {
                if (bulkOut(data!!, tl, timeout) != tl) throw FirmwareException("écriture 0x${id.toString(16)} incomplète")
            }
        }
        val spoon = ByteArray(64)
        val ack = if (isIn) conn.bulkTransfer(epOut, spoon, 1, if (tl == 0) timeout else 3000)
        else conn.bulkTransfer(epIn, spoon, 1, if (tl == 0) timeout else 3000)
        if (ack < 0) throw FirmwareException("pas d'acquittement pour la commande 0x${id.toString(16)}")
        return result
    }

    fun exclusiveAccess(level: Int) = cmd(PicobootProto.PC_EXCLUSIVE_ACCESS, byteArrayOf(level.toByte()))
    fun exitXip() = cmd(PicobootProto.PC_EXIT_XIP, ByteArray(0))
    fun flashErase(addr: Long, size: Int) = cmd(PicobootProto.PC_FLASH_ERASE, PicobootProto.u32s(addr, size.toLong()))
    fun write(addr: Long, data: ByteArray) = cmd(PicobootProto.PC_WRITE, PicobootProto.u32s(addr, data.size.toLong()), data)
    fun read(addr: Long, size: Int): ByteArray =
        cmd(PicobootProto.PC_READ, PicobootProto.u32s(addr, size.toLong()), inLen = size)!!
    fun reboot(delayMs: Long = 500) =
        cmd(PicobootProto.PC_REBOOT, PicobootProto.u32s(0, PicobootProto.SRAM_END_RP2040, delayMs))

    /** Flash complet : effacement + écriture + relecture de chaque secteur, puis redémarrage. */
    fun flash(img: Uf2Image, progress: (done: Int, total: Int, phase: String) -> Unit, cancelled: () -> Boolean) {
        val sectors = img.sectors()
        reset()
        exclusiveAccess(PicobootProto.EXCLUSIVE)
        exitXip()
        sectors.forEachIndexed { i, (addr, data) ->
            if (cancelled()) throw FirmwareException(
                "annulé pendant l'écriture : la manette reste en mode BOOTSEL, relance la mise à jour")
            flashErase(addr, data.size)
            write(addr, data)
            progress(i + 1, sectors.size * 2, "écriture")
        }
        sectors.forEachIndexed { i, (addr, data) ->
            val back = read(addr, data.size)
            if (!back.contentEquals(data)) throw FirmwareException(
                "vérification échouée à 0x${addr.toString(16)} : relance la mise à jour (la manette reste en BOOTSEL)")
            progress(sectors.size + i + 1, sectors.size * 2, "vérification")
        }
        reboot()
    }

    override fun close() {
        try { conn.releaseInterface(intf) } catch (_: Exception) {}
        conn.close()
    }
}
