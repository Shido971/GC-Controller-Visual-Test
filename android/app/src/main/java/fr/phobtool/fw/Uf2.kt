package fr.phobtool.fw

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.TreeMap

class FirmwareException(msg: String) : Exception(msg)

/**
 * Fichier UF2 pour RP2040 : validation (magic, numérotation, famille RP2040)
 * et découpage en secteurs de 4 Ko pour le flash via PICOBOOT.
 */
class Uf2Image private constructor(
    val blocks: Int,
    val familyId: Long?,
    /** pages de 256 octets indexées par adresse absolue (0x10000000…) */
    val pages: TreeMap<Long, ByteArray>,
) {
    val payloadBytes: Int get() = pages.size * PAGE

    /** Secteurs de 4096 octets à effacer puis écrire (pages absentes = 0xFF). */
    fun sectors(): List<Pair<Long, ByteArray>> {
        val out = TreeMap<Long, ByteArray>()
        for ((addr, data) in pages) {
            val base = addr and (SECTOR - 1).toLong().inv()
            val buf = out.getOrPut(base) { ByteArray(SECTOR) { 0xFF.toByte() } }
            System.arraycopy(data, 0, buf, (addr - base).toInt(), PAGE)
        }
        return out.entries.map { it.key to it.value }
    }

    companion object {
        const val MAGIC0 = 0x0A324655L
        const val MAGIC1 = 0x9E5D5157L
        const val MAGIC_END = 0x0AB16F30L
        const val FLAG_NOT_MAIN_FLASH = 0x00000001L
        const val FLAG_FAMILY_ID = 0x00002000L
        const val RP2040_FAMILY = 0xE48BFF56L
        const val FLASH_START = 0x10000000L
        const val FLASH_END = 0x11000000L
        const val PAGE = 256
        const val SECTOR = 4096

        fun parse(data: ByteArray, requireRp2040: Boolean = true): Uf2Image {
            if (data.isEmpty() || data.size % 512 != 0)
                throw FirmwareException("taille de fichier UF2 invalide (doit être un multiple de 512 octets)")
            val n = data.size / 512
            var family: Long? = null
            val pages = TreeMap<Long, ByteArray>()
            val bb = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
            for (i in 0 until n) {
                val o = i * 512
                fun u32(off: Int) = bb.getInt(o + off).toLong() and 0xFFFFFFFFL
                if (u32(0) != MAGIC0 || u32(4) != MAGIC1 || u32(508) != MAGIC_END)
                    throw FirmwareException("bloc UF2 $i corrompu (magic incorrect)")
                val flags = u32(8)
                val addr = u32(12)
                val size = u32(16).toInt()
                val blockNo = u32(20)
                val numBlocks = u32(24)
                val fam = u32(28)
                if (blockNo != i.toLong() || numBlocks != n.toLong())
                    throw FirmwareException("numérotation UF2 incohérente au bloc $i")
                if (size > 476) throw FirmwareException("bloc UF2 $i : taille de données invalide")
                if (flags and FLAG_FAMILY_ID != 0L) {
                    if (family == null) family = fam
                    else if (family != fam) throw FirmwareException("plusieurs familles de MCU dans le même UF2")
                }
                if (flags and FLAG_NOT_MAIN_FLASH != 0L) continue
                if (size != PAGE || addr % PAGE != 0L)
                    throw FirmwareException("bloc UF2 $i : seules les pages de 256 octets alignées sont gérées")
                if (addr < FLASH_START || addr + PAGE > FLASH_END)
                    throw FirmwareException("bloc UF2 $i hors de la flash (0x${addr.toString(16)})")
                pages[addr] = data.copyOfRange(o + 32, o + 32 + PAGE)
            }
            if (requireRp2040 && family != RP2040_FAMILY)
                throw FirmwareException("ce UF2 ne cible pas un RP2040 (famille 0x${(family ?: 0).toString(16)})")
            if (pages.isEmpty()) throw FirmwareException("UF2 vide")
            if (pages.firstKey() != FLASH_START)
                throw FirmwareException("le firmware ne commence pas au début de la flash")
            return Uf2Image(n, family, pages)
        }
    }
}
