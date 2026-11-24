package fr.phobtool.fw

import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager

/**
 * Flash d'un Teensy (PhobGCC 1.x) via le bootloader HalfKay (VID 16C0 PID 0478),
 * d'après teensy_loader_cli (PJRC).
 */
enum class TeensyModel(val label: String, val codeSize: Int, val blockSize: Int) {
    TEENSY40("Teensy 4.0", 2031616, 1024),
    TEENSY32("Teensy 3.2", 262144, 1024),
}

class IntelHexImage(val model: TeensyModel) {
    val image = ByteArray(model.codeSize) { 0xFF.toByte() }
    val mask = BooleanArray(model.codeSize)
    var byteCount = 0
        private set

    fun bytesWithin(begin: Int, endInclusive: Int): Boolean {
        for (a in begin..minOf(endInclusive, model.codeSize - 1)) if (mask[a]) return true
        return false
    }

    fun isBlank(addr: Int, size: Int): Boolean {
        for (a in addr until minOf(addr + size, model.codeSize)) if (image[a] != 0xFF.toByte()) return false
        return true
    }

    /** Blocs HalfKay prêts à envoyer (en-tête 64 octets + 1024 octets de données). */
    fun blocks(): List<ByteArray> {
        val bs = model.blockSize
        val out = ArrayList<ByteArray>()
        var addr = 0
        while (addr < model.codeSize) {
            val first = out.isEmpty()
            if (first || (bytesWithin(addr, addr + bs - 1) && !isBlank(addr, bs))) {
                val buf = ByteArray(bs + 64)
                buf[0] = (addr and 0xFF).toByte()
                buf[1] = ((addr shr 8) and 0xFF).toByte()
                buf[2] = ((addr shr 16) and 0xFF).toByte()
                System.arraycopy(image, addr, buf, 64, minOf(bs, model.codeSize - addr))
                out += buf
            }
            addr += bs
        }
        return out
    }

    fun bootPacket(): ByteArray = ByteArray(model.blockSize + 64).also {
        it[0] = 0xFF.toByte(); it[1] = 0xFF.toByte(); it[2] = 0xFF.toByte()
    }

    companion object {
        fun parse(text: String, model: TeensyModel): IntelHexImage {
            val img = IntelHexImage(model)
            var ext = 0L
            var end = false
            for ((ln, raw) in text.lineSequence().withIndex()) {
                val line = raw.trim()
                if (line.isEmpty()) continue
                if (!line.startsWith(":") || line.length < 11) throw FirmwareException("ligne ${ln + 1} : format Intel HEX invalide")
                val bytes = try {
                    ByteArray((line.length - 1) / 2) { line.substring(1 + 2 * it, 3 + 2 * it).toInt(16).toByte() }
                } catch (e: NumberFormatException) { throw FirmwareException("ligne ${ln + 1} : caractère non hexadécimal") }
                val len = bytes[0].toInt() and 0xFF
                if (bytes.size < len + 5) throw FirmwareException("ligne ${ln + 1} : ligne tronquée")
                if (bytes.take(len + 5).sumOf { it.toInt() and 0xFF } and 0xFF != 0)
                    throw FirmwareException("ligne ${ln + 1} : somme de contrôle incorrecte")
                val addr = ((bytes[1].toInt() and 0xFF) shl 8) or (bytes[2].toInt() and 0xFF)
                when (bytes[3].toInt() and 0xFF) {
                    0 -> {
                        for (k in 0 until len) {
                            val a = addr + ext + k
                            if (a < 0 || a >= model.codeSize) throw FirmwareException(
                                "adresse 0x${a.toString(16)} hors de la mémoire du ${model.label} : mauvais modèle choisi ?")
                            img.image[a.toInt()] = bytes[4 + k]
                            img.mask[a.toInt()] = true
                        }
                        img.byteCount += len
                    }
                    1 -> { end = true }
                    2 -> ext = (((bytes[4].toInt() and 0xFF) shl 8) or (bytes[5].toInt() and 0xFF)).toLong() shl 4
                    4 -> {
                        ext = (((bytes[4].toInt() and 0xFF) shl 8) or (bytes[5].toInt() and 0xFF)).toLong() shl 16
                        // les .hex Teensy 4.x sont à l'adresse FlexSPI 0x60000000
                        if (model.codeSize > 1048576 && ext >= 0x60000000L && ext < 0x60000000L + model.codeSize) ext -= 0x60000000L
                    }
                }
                if (end) break
            }
            if (img.byteCount == 0) throw FirmwareException("fichier HEX vide")
            return img
        }
    }
}

class TeensyLoader(private val conn: UsbDeviceConnection) : AutoCloseable {
    companion object {
        const val VID = 0x16C0
        const val PID_HALFKAY = 0x0478
        fun isHalfKay(d: UsbDevice) = d.vendorId == VID && d.productId == PID_HALFKAY
        fun open(m: UsbManager, d: UsbDevice): TeensyLoader {
            val c = m.openDevice(d) ?: throw FirmwareException("impossible d'ouvrir le Teensy (permission ?)")
            if (d.interfaceCount > 0) c.claimInterface(d.getInterface(0), true)
            return TeensyLoader(c)
        }
    }

    private fun write(buf: ByteArray, timeoutS: Double): Boolean {
        var left = timeoutS
        while (left > 0) {
            val r = conn.controlTransfer(0x21, 9, 0x0200, 0, buf, buf.size, (left * 1000).toInt().coerceAtLeast(100))
            if (r >= 0) return true
            Thread.sleep(10)
            left -= 0.01
        }
        return false
    }

    fun flash(img: IntelHexImage, progress: (Int, Int) -> Unit, cancelled: () -> Boolean) {
        val blocks = img.blocks()
        blocks.forEachIndexed { i, b ->
            if (cancelled()) throw FirmwareException("annulé : le Teensy reste en mode programmation, relance la mise à jour")
            if (!write(b, if (i <= 4) 45.0 else 0.5)) throw FirmwareException("erreur d'écriture sur le Teensy (bloc ${i + 1})")
            progress(i + 1, blocks.size)
        }
        write(img.bootPacket(), 0.5)
    }

    override fun close() = conn.close()
}
