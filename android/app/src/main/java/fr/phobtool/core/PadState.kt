package fr.phobtool.core

/** État d'une manette lue via l'adaptateur GameCube officiel (WUP-028). */
data class PadState(
    val connected: Boolean = false,
    val wireless: Boolean = false,
    val buttons: Set<String> = emptySet(),
    val ax: Int = 128,
    val ay: Int = 128,
    val cx: Int = 128,
    val cy: Int = 128,
    val l: Int = 0,
    val r: Int = 0,
    /** horodatage de réception en secondes (horloge monotone) */
    val t: Double = 0.0,
) {
    fun pressed(vararg names: String) = names.all { it in buttons }

    /** coordonnées centrées (-128..127), Y vers le haut */
    val aX get() = ax - 128
    val aY get() = ay - 128
    val cX get() = cx - 128
    val cY get() = cy - 128

    fun melee(stick: Char): Pair<Double, Double> {
        val (x, y) = if (stick == 'A') aX to aY else cX to cY
        fun conv(v: Int) = Math.round(v.coerceIn(-80, 80) * 0.0125 * 10000.0) / 10000.0
        return conv(x) to conv(y)
    }

    companion object {
        private val B1 = listOf(0x01 to "A", 0x02 to "B", 0x04 to "X", 0x08 to "Y",
            0x10 to "Dl", 0x20 to "Dr", 0x40 to "Dd", 0x80 to "Du")
        private val B2 = listOf(0x01 to "S", 0x02 to "Z", 0x04 to "R", 0x08 to "L")

        /** Rapport de 37 octets : 0x21 puis 4 x [status, b1, b2, sx, sy, cx, cy, l, r]. */
        fun parseReport(d: ByteArray, len: Int = d.size, t: Double = 0.0): List<PadState>? {
            if (len < 37 || (d[0].toInt() and 0xFF) != 0x21) return null
            return (0 until 4).map { i ->
                val o = 1 + 9 * i
                fun u(k: Int) = d[o + k].toInt() and 0xFF
                val kind = (u(0) shr 4) and 0x3
                if (kind == 0) PadState(t = t) else {
                    val btn = HashSet<String>()
                    for ((m, n) in B1) if (u(1) and m != 0) btn += n
                    for ((m, n) in B2) if (u(2) and m != 0) btn += n
                    PadState(true, kind == 2, btn, u(3), u(4), u(5), u(6), u(7), u(8), t)
                }
            }
        }
    }
}
