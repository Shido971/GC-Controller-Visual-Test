package fr.phobtool.ui

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import fr.phobtool.core.Cal
import fr.phobtool.core.CalState
import fr.phobtool.core.CalibrationTracker
import fr.phobtool.core.Guidance
import fr.phobtool.core.PadState

val SHORTCUTS = listOf(
    "A+X+Y+Start (maintenir)" to "Activer / désactiver le safe mode",
    "A+X+Y+L" to "Calibrer le stick analogique",
    "A+X+Y+R" to "Calibrer le C-stick",
    "A+B+Z+Start" to "Soft reset (après une mise à jour)",
    "A+B+Z+D-bas" to "Hard reset (efface aussi la calibration)",
    "A+Z+D-haut" to "Afficher la version du firmware",
    "Start au branchement" to "Mode BOOTSEL (Phob 2) pour flasher",
)

/** Choix du port : -1 = premier port branché. */
fun selectPad(pads: List<PadState>?, port: Int): Pair<Int, PadState>? {
    if (pads == null) return null
    if (port >= 0) return if (pads[port].connected) port to pads[port] else null
    pads.forEachIndexed { i, p -> if (p.connected) return i to p }
    return null
}

class TestPage(private val ctx: Context) : Page {
    private val tracker = CalibrationTracker()
    private var port = -1
    private var stick = 'A'
    private var latest: Pair<Int, PadState>? = null
    private var guidance: Guidance = tracker.guidance()
    private lateinit var stickRadios: android.widget.RadioGroup
    private var syncingStick = false

    private val title = ctx.text("Prêt", 19f, bold = true)
    private val detail = ctx.text("", 14f)
    private val bar = ctx.progress()
    private val viewA = StickView(ctx, "Stick analogique", C.ACCENT)
    private val viewC = StickView(ctx, "C-stick", C.YELLOW)
    private val trigL = TriggerBar(ctx, "L")
    private val trigR = TriggerBar(ctx, "R")
    private val info = ctx.text("—", 13f, color = C.DIM).apply { gravity = Gravity.CENTER }
    private val btnLabels = LinkedHashMap<String, TextView>()

    override val view: View = ScrollView(ctx).apply {
        val root = ctx.vbox(12)
        addView(root)

        val ctl = ctx.card("Calibration guidée")
        ctl.add(ctx.hbox().apply {
            add(ctx.text("Port : "), w = LinearLayout.LayoutParams.WRAP_CONTENT)
            add(ctx.spinner(listOf("Auto", "Port 1", "Port 2", "Port 3", "Port 4")) { port = it - 1 },
                w = 0, weight = 1f)
        })
        stickRadios = ctx.radios(listOf("Stick analogique", "C-stick")) {
            if (!syncingStick) { stick = if (it == 0) 'A' else 'C'; tracker.reset(); refreshGuidance() }
        }
        ctl.add(stickRadios)
        ctl.add(ctx.hbox().apply {
            add(ctx.button("Démarrer", primary = true) { tracker.arm(stick); viewA.clearTrail(); viewC.clearTrail(); refreshGuidance() },
                w = 0, weight = 1f)
            add(View(ctx), w = ctx.dp(8))
            add(ctx.button("Arrêter") { tracker.reset(); refreshGuidance() }, w = 0, weight = 1f)
        }, top = 6)
        root.add(ctl)
        root.gap()

        val g = ctx.card("Étape en cours")
        g.add(title); g.add(detail, top = 4); g.add(bar, top = 8)
        root.add(g)
        root.gap()

        root.add(ctx.hbox().apply {
            add(trigL, w = ctx.dp(34), h = ctx.dp(150))
            add(viewA, w = 0, weight = 1f)
            add(viewC, w = 0, weight = 1f)
            add(trigR, w = ctx.dp(34), h = ctx.dp(150))
        })
        val row = ctx.hbox().apply { gravity = Gravity.CENTER }
        for (n in listOf("A", "B", "X", "Y", "Z", "L", "R", "S", "Du", "Dd", "Dl", "Dr")) {
            val label = mapOf("S" to "St", "Du" to "↑", "Dd" to "↓", "Dl" to "←", "Dr" to "→")[n] ?: n
            val tv = ctx.text(label, 12f, bold = true).apply {
                gravity = Gravity.CENTER
                setPadding(ctx.dp(2), ctx.dp(4), ctx.dp(2), ctx.dp(4))
            }
            btnLabels[n] = tv
            row.add(tv, w = 0, weight = 1f)
        }
        root.add(row, top = 6)
        root.add(info, top = 4)
        root.add(ctx.button("Effacer les traînées") { viewA.clearTrail(); viewC.clearTrail() }, top = 6)
        root.gap()

        val sc = ctx.card("Raccourcis PhobGCC")
        for ((k, d) in SHORTCUTS) sc.add(ctx.html("<b>$k</b> — $d", 13f), top = 3)
        root.add(sc)
        refreshGuidance()
    }

    private fun refreshGuidance() {
        guidance = tracker.guidance()
        title.text = guidance.title
        title.setTextColor(if (guidance.state == CalState.DONE) C.GREEN else C.TEXT)
        detail.text = guidance.detail
        bar.progress = (guidance.progress * 1000).toInt()
    }

    override fun onPads(pads: List<PadState>?, status: String) {
        val sel = selectPad(pads, port)
        latest = sel
        if (sel != null) guidance = tracker.feed(sel.second)
        if (pads == null) info.text = status
    }

    /** le suivi a pu corriger le stick d'après le combo réellement utilisé sur la manette */
    private fun syncStickChoice() {
        val st = guidance.state
        if (st == CalState.IDLE || st == CalState.ARMED || tracker.stick == stick) return
        syncingStick = true
        stick = tracker.stick
        val idx = if (stick == 'A') 0 else 1
        for (i in 0 until stickRadios.childCount) {
            val rb = stickRadios.getChildAt(i) as android.widget.RadioButton
            if (rb.tag == idx) rb.isChecked = true
        }
        syncingStick = false
    }

    override fun onFrame() {
        syncStickChoice()
        val sel = latest
        if (sel == null) {
            viewA.set(null); viewC.set(null)
            return
        }
        val (p, pad) = sel
        val g = guidance
        val active = g.state == CalState.MEASURE || g.state == CalState.ADJUST
        val notch = if (active) Cal.stepNotch(g.step) else null
        val a = pad.aX to pad.aY
        val c = pad.cX to pad.cY
        when {
            active && tracker.stick == 'A' -> { viewA.set(a, g.target, notch, "← stick en calibration"); viewC.set(c, null, null, "cible du firmware") }
            active -> { viewC.set(c, g.target, notch, "← stick en calibration"); viewA.set(a, null, null, "cible du firmware") }
            else -> {
                val ma = pad.melee('A'); val mc = pad.melee('C')
                viewA.set(a, subtitle = "Melee %+.4f, %+.4f".format(ma.first, ma.second))
                viewC.set(c, subtitle = "Melee %+.4f, %+.4f".format(mc.first, mc.second))
            }
        }
        trigL.set(pad.l, "L" in pad.buttons); trigR.set(pad.r, "R" in pad.buttons)
        for ((n, tv) in btnLabels) {
            val on = n in pad.buttons
            tv.setTextColor(if (on) Color.WHITE else C.DIM)
            tv.background = if (on) GradientDrawable().apply { setColor(C.ACCENT_DARK); cornerRadius = 8f } else null
        }
        info.text = "Port ${p + 1} · manette ${if (pad.wireless) "WaveBird" else "filaire"}"
        title.text = g.title
        title.setTextColor(if (g.state == CalState.DONE) C.GREEN else C.TEXT)
        detail.text = g.detail
        bar.progress = (g.progress * 1000).toInt()
    }
}
