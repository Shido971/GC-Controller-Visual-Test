package fr.phobtool.core

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Test de snapback sur le modèle de l'oscilloscope de GTS (greenwave-1/GTS).
 * Port de phobtool/snapback.py.
 */
object Snap {
    const val MOVEMENT_THRESHOLD = 15
    const val ORIGIN_TIME_S = 0.025
    const val PREPEND_S = 0.025
    const val TRIGGER_RANGE = 64
    const val MELEE_DEADZONE = 22
    const val MAX_SAMPLES = 3000
    const val MAX_DURATION_S = 1.5
    const val STILL_CANCEL_S = 0.25
}

data class Sample(val t: Double, val x: Int, val y: Int)

data class SnapbackResult(
    val samples: List<Sample>,
    val axis: Char,
    val startValue: Int,
    val minX: Int, val maxX: Int, val minY: Int, val maxY: Int,
    val overshoot: Int,
    val settleMs: Double,
    val crossings: Int,
    val samplePeriodMs: Double,
    val t0: Double,
) {
    val direction: String
        get() = if (axis == 'x') (if (startValue > 0) "droite" else "gauche") else (if (startValue > 0) "haut" else "bas")
    val passed: Boolean get() = abs(overshoot) <= Snap.MELEE_DEADZONE
    fun values(a: Char = axis): List<Int> = samples.map { if (a == 'x') it.x else it.y }
}

class SnapbackDetector {
    private val history = ArrayDeque<Sample>()
    private var crossed = false
    private var startX = 0
    private var startY = 0
    private var recording: MutableList<Sample>? = null
    private var inOriginS = 0.0
    private var stillS = 0.0
    private var releaseT = 0.0

    val state: String get() = when {
        recording != null -> "recording"
        crossed -> "armed"
        else -> "waiting"
    }

    fun reset() {
        crossed = false; startX = 0; startY = 0; recording = null
        inOriginS = 0.0; stillS = 0.0; releaseT = 0.0; history.clear()
    }

    fun feed(t: Double, x: Int, y: Int): SnapbackResult? {
        val s = Sample(t, x, y)
        val prev = history.lastOrNull()
        history.addLast(s)
        if (history.size > 400) history.removeFirst()
        val dt = if (prev != null) t - prev.t else 0.0

        val rec = recording
        if (rec != null) {
            rec += s
            val near = abs(x) < Snap.MOVEMENT_THRESHOLD && abs(y) < Snap.MOVEMENT_THRESHOLD
            inOriginS = if (near) inOriginS + dt else 0.0
            val still = prev != null && abs(x - prev.x) <= 2 && abs(y - prev.y) <= 2
            stillS = if (still && !near) stillS + dt else 0.0
            val tooLong = rec.size >= Snap.MAX_SAMPLES || stillS >= Snap.STILL_CANCEL_S ||
                t - rec[0].t > Snap.MAX_DURATION_S
            if (inOriginS >= Snap.ORIGIN_TIME_S || tooLong) {
                if (near) {
                    val res = analyse(rec, startX, startY, releaseT)
                    recording = null; crossed = false; startX = 0; startY = 0; inOriginS = 0.0
                    return res
                }
                recording = null; crossed = false; startX = x; startY = y
            }
            return null
        }

        if (!crossed) {
            if (abs(x) > Snap.TRIGGER_RANGE || abs(y) > Snap.TRIGGER_RANGE) {
                crossed = true; startX = x; startY = y
            }
            return null
        }
        var grew = false
        if (abs(x) > abs(startX)) { startX = x; grew = true }
        if (abs(y) > abs(startY)) { startY = y; grew = true }
        if (!grew && (abs(x) + Snap.MOVEMENT_THRESHOLD <= abs(startX) || abs(y) + Snap.MOVEMENT_THRESHOLD <= abs(startY))) {
            releaseT = t
            val pre = history.toList().dropLast(1).filter { t - it.t <= Snap.PREPEND_S }
            recording = (pre + s).toMutableList()
            inOriginS = 0.0; stillS = 0.0
        }
        return null
    }

    companion object {
        fun analyse(rec: List<Sample>, startX: Int, startY: Int, releaseT: Double): SnapbackResult {
            val xs = rec.map { it.x }
            val ys = rec.map { it.y }
            val maxAx = xs.maxOfOrNull { abs(it) } ?: 0
            val maxAy = ys.maxOfOrNull { abs(it) } ?: 0
            val axis = if (maxAx >= maxAy) 'x' else 'y'
            val vals = if (axis == 'x') xs else ys
            var start = if (axis == 'x') startX else startY
            if (start == 0) start = vals.maxByOrNull { abs(it) } ?: 0
            val sign = if (start >= 0) 1 else -1
            val opposite = vals.filter { it * sign < 0 }
            val overshoot = opposite.maxByOrNull { abs(it) } ?: 0
            var crossings = 0
            var outside = false
            for (v in vals) {
                val o = v * sign < 0 && abs(v) > Snap.MELEE_DEADZONE
                if (o && !outside) crossings++
                outside = o
            }
            var lastOut = releaseT
            for (s in rec) {
                val v = if (axis == 'x') s.x else s.y
                if (s.t >= releaseT && abs(v) > Snap.MELEE_DEADZONE) lastOut = s.t
            }
            val periods = rec.zipWithNext().map { (a, b) -> b.t - a.t }.filter { it > 0 }
            return SnapbackResult(rec, axis, start,
                xs.minOrNull() ?: 0, xs.maxOrNull() ?: 0, ys.minOrNull() ?: 0, ys.maxOrNull() ?: 0,
                overshoot, max(0.0, (lastOut - releaseT) * 1000), crossings,
                if (periods.isEmpty()) 0.0 else periods.average() * 1000, releaseT)
        }

        /** Lâcher synthétique (oscillation amortie) – tests et démo. */
        fun simulateRelease(start: Double = 100.0, axis: Char = 'x', overshoot: Double = 0.35,
                            freqHz: Double = 70.0, decayMs: Double = 12.0, rateHz: Double = 1000.0,
                            holdMs: Double = 60.0, afterMs: Double = 120.0, t0: Double = 0.0): List<Sample> {
            val out = ArrayList<Sample>()
            val dt = 1.0 / rateHz
            var t = t0
            repeat((holdMs / 1000 * rateHz).toInt()) {
                val v = start.roundToInt()
                out += Sample(t, if (axis == 'x') v else 0, if (axis == 'y') v else 0); t += dt
            }
            for (i in 0 until (afterMs / 1000 * rateHz).toInt()) {
                val tau = i * dt * 1000
                val fall = max(0.0, 1 - tau / 3.0)
                val osc = -overshoot * start * exp(-tau / decayMs) * sin(2 * PI * freqHz * (tau / 1000))
                val v = (start * fall + if (fall > 0) 0.0 else osc).roundToInt()
                out += Sample(t, if (axis == 'x') v else 0, if (axis == 'y') v else 0); t += dt
            }
            return out
        }
    }
}

class RateMeter(private val window: Int = 250) {
    private val ts = ArrayDeque<Double>()
    fun tick(t: Double) {
        if (ts.isEmpty() || t > ts.last()) { ts.addLast(t); if (ts.size > window) ts.removeFirst() }
    }
    val hz: Double get() {
        if (ts.size < 10) return 0.0
        val span = ts.last() - ts.first()
        return if (span > 0) (ts.size - 1) / span else 0.0
    }
}
