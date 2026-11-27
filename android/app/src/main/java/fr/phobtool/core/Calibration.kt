package fr.phobtool.core

import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Suivi en direct de la calibration PhobGCC (firmware v0.29+, common/stick.h + phobGCC.h).
 * Port fidèle de phobtool/calibration.py : la cible affichée par le firmware sur l'autre
 * stick sert de référence, les boutons servent d'indices.
 */
object Cal {
    const val NO_OF_NOTCHES = 16
    const val NO_OF_CAL_POINTS = 32
    const val NO_OF_ADJ_NOTCHES = 12
    val CAL_ORDER = intArrayOf(0, 1, 8, 9, 16, 17, 24, 25, 4, 5, 12, 13, 20, 21, 28, 29,
        2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23, 26, 27, 30, 31)
    val NOTCH_ADJ_ORDER = intArrayOf(2, 6, 10, 14, 1, 3, 5, 7, 9, 11, 13, 15)
    const val MAX_STICK_ANGLE = 0.4886921906

    val NOTCH_NAMES = mapOf(
        0 to "droite", 1 to "encoche droite-haut (tertiaire)", 2 to "diagonale haut-droite",
        3 to "encoche haut-droite (tertiaire)", 4 to "haut", 5 to "encoche haut-gauche (tertiaire)",
        6 to "diagonale haut-gauche", 7 to "encoche gauche-haut (tertiaire)", 8 to "gauche",
        9 to "encoche gauche-bas (tertiaire)", 10 to "diagonale bas-gauche",
        11 to "encoche bas-gauche (tertiaire)", 12 to "bas", 13 to "encoche bas-droite (tertiaire)",
        14 to "diagonale bas-droite", 15 to "encoche droite-bas (tertiaire)")
    val ARROWS = mapOf(0 to "→", 2 to "↗", 4 to "↑", 6 to "↖", 8 to "←", 10 to "↙", 12 to "↓", 14 to "↘")

    fun notchTarget(n: Int): Pair<Double, Double> {
        val a = n * PI / 8
        val x = 100 * atan2(sin(MAX_STICK_ANGLE) * cos(a), cos(MAX_STICK_ANGLE)) / MAX_STICK_ANGLE
        val y = 100 * atan2(sin(MAX_STICK_ANGLE) * sin(a), cos(MAX_STICK_ANGLE)) / MAX_STICK_ANGLE
        return x to y
    }

    /** encoche visée à une étape (null = neutre) */
    fun stepNotch(step: Int): Int? = when {
        step in 0 until NO_OF_CAL_POINTS -> CAL_ORDER[step].let { if (it % 2 == 1) it / 2 else null }
        step in NO_OF_CAL_POINTS until NO_OF_CAL_POINTS + NO_OF_ADJ_NOTCHES -> NOTCH_ADJ_ORDER[step - NO_OF_CAL_POINTS]
        else -> null
    }

    fun nearestNotch(x: Double, y: Double): Int {
        var a = atan2(y, x)
        if (a < 0) a += 2 * PI
        return (a / (PI / 8)).roundToInt() % NO_OF_NOTCHES
    }

    val PHASE1_STEP_FOR_NOTCH: Map<Int, Int> =
        (0 until NO_OF_CAL_POINTS).filter { CAL_ORDER[it] % 2 == 1 }.associateBy { CAL_ORDER[it] / 2 }
    val PHASE2_STEP_FOR_NOTCH: Map<Int, Int> =
        NOTCH_ADJ_ORDER.withIndex().associate { (k, n) -> n to NO_OF_CAL_POINTS + k }

    const val TARGET_CENTER_RADIUS = 25.0
    const val TARGET_NOTCH_RADIUS = 60.0

    /** freezeSticks() du firmware : les 4 axes sont envoyés à 255, aucun bouton, pendant 2 s. */
    const val FREEZE_MIN = 250
    const val COMBO_MEMORY = 1.5        // s : boutons du combo vus récemment avant le gel
    const val CONFIRM_TIMEOUT = 0.6     // s : combo complet tenu sans gel = la manette n'a pas réagi
    const val FALLBACK_RATE = 125.0     // Hz, pour dater les trames sans horodatage

    fun isFrozen(p: PadState) = minOf(minOf(p.ax, p.ay), minOf(p.cx, p.cy)) >= FREEZE_MIN && p.buttons.isEmpty()
}

enum class CalState { IDLE, ARMED, FROZEN, MEASURE, ADJUST, DONE }

data class Guidance(
    val state: CalState,
    val step: Int,
    val title: String,
    val detail: String,
    val target: Pair<Double, Double>?,
    val progress: Double,
)

class CalibrationTracker(var stick: Char = 'A') {
    var state = CalState.IDLE
        private set
    var step = -1
        private set
    private var prevButtons: Set<String> = emptySet()
    private var lastTargetKind: String? = null
    private var target: Pair<Double, Double>? = null
    private var centerFrames = 0
    private var frames = 0L
    private val seen = HashMap<String, Double>()
    private var comboSince: Double? = null
    /** combo tenu sans réaction de la manette (safe mode, manette non Phob) */
    var error: String? = null
        private set
    /** stick corrigé d'après le combo réellement utilisé */
    var notice: String? = null
        private set

    val combo: List<String> get() = if (stick == 'A') listOf("A", "X", "Y", "L") else listOf("A", "X", "Y", "R")

    fun arm(s: Char) {
        stick = s; state = CalState.ARMED; step = -1; lastTargetKind = null; centerFrames = 0
        seen.clear(); comboSince = null; error = null; notice = null
    }

    fun reset() {
        state = CalState.IDLE; step = -1
    }

    private fun other(p: PadState) = if (stick == 'A') p.cX to p.cY else p.aX to p.aY

    private fun recent(name: String, now: Double) = seen[name]?.let { now - it <= Cal.COMBO_MEMORY } ?: false

    /**
     * Le combo complet n'apparaît presque jamais dans les rapports : le firmware gèle sa sortie dans la même
     * boucle. La preuve que la calibration a démarré, c'est le gel (4 axes à 255) juste après A+X+Y.
     */
    private fun armStep(p: PadState, now: Double) {
        if (Cal.isFrozen(p)) {
            if (listOf("A", "X", "Y").all { recent(it, now) }) {
                val tl = seen["L"] ?: -1e9; val tr = seen["R"] ?: -1e9
                if (recent("L", now) || recent("R", now)) {
                    val real = if (tl > tr) 'A' else 'C'
                    if (real != stick) {
                        notice = "Combo du ${if (real == 'A') "stick analogique" else "C-stick"} détecté : c'est lui que " +
                            "la manette calibre, l'appli suit ce stick."
                        stick = real
                    }
                }
                state = CalState.FROZEN; error = null
            }
            return
        }
        for (b in p.buttons) seen[b] = now
        if (p.pressed(*combo.toTypedArray())) {
            val since = comboSince
            if (since == null) comboSince = now
            else if (now - since > Cal.CONFIRM_TIMEOUT)
                error = "La manette n'est pas entrée en calibration : ses sticks ne se sont pas figés. Elle est sans " +
                    "doute en safe mode (maintiens A+X+Y+Start quelques secondes pour le désactiver), ou ce n'est pas une PhobGCC."
        } else comboSince = null
    }

    fun feed(p: PadState): Guidance {
        frames++
        val now = if (p.t > 0) p.t else frames / Cal.FALLBACK_RATE
        val held = p.buttons
        val down = held - prevButtons
        prevButtons = held
        when (state) {
            CalState.ARMED -> armStep(p, now)
            CalState.FROZEN -> if (!Cal.isFrozen(p)) {
                state = CalState.MEASURE; step = 0; lastTargetKind = "center"
                track(p, down)
            }
            CalState.MEASURE, CalState.ADJUST -> if (!Cal.isFrozen(p)) track(p, down)
            else -> {}
        }
        return guidance()
    }

    private fun track(p: PadState, down: Set<String>) {
        val (oxI, oyI) = other(p)
        val ox = oxI.toDouble(); val oy = oyI.toDouble()
        val r = hypot(ox, oy)
        val kind = when {
            r < Cal.TARGET_CENTER_RADIUS -> "center"
            r > Cal.TARGET_NOTCH_RADIUS -> "notch"
            else -> null
        }
        if (kind != null) target = ox to oy

        if ("S" in down && state == CalState.MEASURE) {
            state = CalState.ADJUST; step = Cal.NO_OF_CAL_POINTS; lastTargetKind = null; return
        }
        if ("Z" in down) {
            if (state == CalState.MEASURE && step > 0) step = maxOf(0, step - if (step % 2 == 0) 2 else 3)
            else if (state == CalState.ADJUST && step > Cal.NO_OF_CAL_POINTS) step -= 1
            lastTargetKind = null
            return
        }
        val advanced = down.any { it == "A" || it == "L" || it == "R" }

        if (state == CalState.MEASURE) {
            if (kind == "notch") {
                val n = Cal.nearestNotch(ox, oy)
                if (lastTargetKind == "notch" && step % 2 == 1 && !advanced && Cal.PHASE1_STEP_FOR_NOTCH[n] != step) {
                    state = CalState.ADJUST
                    step = Cal.PHASE2_STEP_FOR_NOTCH[n] ?: Cal.NO_OF_CAL_POINTS
                } else if (step == Cal.NO_OF_CAL_POINTS - 1 && advanced) {
                    state = CalState.ADJUST
                    step = Cal.PHASE2_STEP_FOR_NOTCH[n] ?: Cal.NO_OF_CAL_POINTS
                } else {
                    step = Cal.PHASE1_STEP_FOR_NOTCH[n] ?: step
                }
                lastTargetKind = "notch"
            } else if (kind == "center") {
                if (lastTargetKind == "notch" && step % 2 == 1) step += 1
                lastTargetKind = "center"
            }
            if (step >= Cal.NO_OF_CAL_POINTS) state = CalState.ADJUST
        } else if (state == CalState.ADJUST) {
            if (kind == "notch") {
                centerFrames = 0
                val n = Cal.nearestNotch(ox, oy)
                Cal.PHASE2_STEP_FOR_NOTCH[n]?.let { step = it }
            } else if (kind == "center") {
                centerFrames++
                if (centerFrames > 20) { state = CalState.DONE; return }
            }
            if (advanced) {
                val last = step == Cal.NO_OF_CAL_POINTS + Cal.NO_OF_ADJ_NOTCHES - 1
                step += 1
                if (last || step >= Cal.NO_OF_CAL_POINTS + Cal.NO_OF_ADJ_NOTCHES) state = CalState.DONE
            }
        }
    }

    fun guidance(): Guidance {
        val name = if (stick == 'A') "stick analogique" else "C-stick"
        val other = if (stick == 'A') "C-stick" else "stick analogique"
        val comboTxt = combo.joinToString("+")
        when (state) {
            CalState.IDLE -> return Guidance(state, -1, "Prêt",
                "Choisis le stick à calibrer puis appuie sur « Démarrer ».", null, 0.0)
            CalState.ARMED -> return error?.let {
                Guidance(state, -1, "⚠ La manette n'a pas réagi", "$it\nRelâche tout, puis appuie de nouveau sur $comboTxt.", null, 0.0)
            } ?: Guidance(state, -1, "Lance la calibration du $name",
                "Sur la manette, appuie en même temps sur $comboTxt.\nL'appli attend que la manette confirme " +
                    "(sticks figés 2 secondes) avant de te guider.", null, 0.0)
            CalState.FROZEN -> return Guidance(state, -1, "Calibration du $name confirmée par la manette",
                (notice?.let { "$it\n" } ?: "") + "Relâche tous les boutons et laisse le $name au neutre.", null, 0.0)
            CalState.DONE -> return Guidance(state, step, "Calibration terminée ✔",
                "Le firmware a enregistré les points et les angles d'encoches. Vérifie le résultat dans le testeur " +
                    "ou avec Visual Controller Test.", null, 1.0)
            else -> {}
        }
        val notch = Cal.stepNotch(step)
        val total = Cal.NO_OF_CAL_POINTS + Cal.NO_OF_ADJ_NOTCHES
        val prog = (step.toDouble() / total).coerceIn(0.0, 1.0)
        val tgt = notch?.let { Cal.notchTarget(it) } ?: (0.0 to 0.0)
        if (state == CalState.MEASURE) {
            return if (notch == null) {
                Guidance(state, step, "Mesure ${step + 1}/32 – neutre",
                    "Lâche le $name pour qu'il revienne au centre, puis appuie sur A.\n" +
                        "Z = annuler la dernière mesure · Start = sauter à l'ajustement des encoches.", tgt, prog)
            } else {
                var d = "Pousse le $name à fond dans l'encoche ${Cal.NOTCH_NAMES[notch]} (cible affichée sur le $other), " +
                    "maintiens-le et appuie sur A."
                if (notch % 2 == 1) d += "\nEncoche tertiaire : si ta gate n'en a pas, laisse le stick au neutre et appuie " +
                    "sur A – elle sera ignorée."
                Guidance(state, step, "Mesure ${step + 1}/32 – ${Cal.NOTCH_NAMES[notch]} ${Cal.ARROWS[notch] ?: ""}", d, tgt, prog)
            }
        }
        val k = step - Cal.NO_OF_CAL_POINTS + 1
        val ideal = (notch ?: 0) * 22.5
        return Guidance(state, step, "Ajustement $k/12 – ${Cal.NOTCH_NAMES[notch] ?: "?"} ${Cal.ARROWS[notch] ?: ""}",
            "Bloque le $name dans cette encoche. X/Y font tourner l'angle de sortie (objectif ≈ ${"%.1f".format(ideal)}°), " +
                "B le remet à la valeur mesurée, A valide et passe à la suivante.", tgt, prog)
    }
}
