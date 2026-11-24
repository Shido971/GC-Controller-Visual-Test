package fr.phobtool.ui

import android.content.Context
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import fr.phobtool.core.PadState
import fr.phobtool.core.RateMeter
import fr.phobtool.core.SnapbackDetector
import fr.phobtool.core.SnapbackResult

class SnapbackPage(private val ctx: Context) : Page {
    private val det = SnapbackDetector()
    private val rate = RateMeter()
    private val results = ArrayList<SnapbackResult>()
    private var port = -1
    private var stick = 'A'
    private var dirty = false
    private var shown: SnapbackResult? = null

    private val state = ctx.text("", 17f, bold = true)
    private val plot = SnapbackPlotView(ctx)
    private val verdict = ctx.text("", 14f)
    private val details = ctx.text("", 12f, color = C.DIM)
    private val rateText = ctx.html("Fréquence de l'adaptateur : —", 13f)
    private val dirs = listOf("droite", "gauche", "haut", "bas")
    private val dirText = dirs.associateWith { ctx.text("—", 13f) }
    private val history = ctx.vbox()

    override val view: View = ScrollView(ctx).apply {
        val root = ctx.vbox(12)
        addView(root)
        val ctl = ctx.card("Test de snapback")
        ctl.add(ctx.hbox().apply {
            add(ctx.text("Port : "), w = LinearLayout.LayoutParams.WRAP_CONTENT)
            add(ctx.spinner(listOf("Auto", "Port 1", "Port 2", "Port 3", "Port 4")) { port = it - 1 }, w = 0, weight = 1f)
        })
        ctl.add(ctx.radios(listOf("Stick analogique", "C-stick")) { stick = if (it == 0) 'A' else 'C'; reset() })
        ctl.add(ctx.button("Remettre à zéro") { reset() }, top = 4)
        root.add(ctl)
        root.add(state, top = 10)
        root.add(ctx.html("Pousse le stick <b>à fond</b>, maintiens-le, puis <b>lâche-le d'un coup</b>. Teste droite, gauche, " +
            "haut et bas plusieurs fois. Un rebond qui sort de <b>±22</b> du côté opposé peut être lu par Melee comme un input.", 13f), top = 4)
        root.add(plot, top = 8)
        root.add(verdict, top = 6)
        root.add(details, top = 2)
        root.gap()
        val summ = ctx.card("Bilan par direction (pire rebond)")
        for (d in dirs) summ.add(ctx.hbox().apply {
            add(ctx.text(d.replaceFirstChar { it.uppercase() }, 13f, bold = true), w = ctx.dp(80))
            add(dirText.getValue(d), w = 0, weight = 1f)
        }, top = 2)
        summ.add(rateText, top = 8)
        root.add(summ)
        root.gap()
        val hist = ctx.card("Historique (touche pour réafficher)")
        hist.add(history)
        root.add(hist)
        root.gap()
        val tips = ctx.card("Si ça rebondit trop (filtre snapback PhobGCC)")
        tips.add(ctx.html("Stick : <b>A+X+D-haut / D-bas</b> (axe X), <b>A+Y+D-haut / D-bas</b> (axe Y).<br>" +
            "C-stick : même combo <b>+ Z</b>.<br>D-haut renforce le filtre, D-bas l'allège (0 = désactivé, 4 = défaut). " +
            "La valeur s'affiche sur l'autre stick pendant le réglage. Refais le test après chaque cran : trop de filtrage " +
            "ajoute de la latence.", 13f))
        root.add(tips)
        updateState()
    }

    private fun reset() {
        det.reset(); results.clear(); history.removeAllViews(); shown = null
        plot.result = null; verdict.text = ""; details.text = ""
        dirText.values.forEach { it.text = "—"; it.setTextColor(C.TEXT) }
        updateState()
    }

    private fun updateState() {
        state.text = when (det.state) {
            "armed" -> "Prêt : lâche le stick d'un coup !"
            "recording" -> "Mesure en cours…"
            else -> "En attente : pousse le stick à fond…"
        }
        state.setTextColor(if (det.state == "armed") C.YELLOW else C.TEXT)
    }

    /** à chaque rapport, sans limitation : toutes les mesures comptent */
    override fun onPads(pads: List<PadState>?, status: String) {
        val (_, pad) = selectPad(pads, port) ?: return
        rate.tick(pad.t)
        val before = det.state
        val r = det.feed(pad.t, if (stick == 'A') pad.aX else pad.cX, if (stick == 'A') pad.aY else pad.cY)
        if (r != null) add(r)
        if (det.state != before) dirty = true
    }

    override fun onFrame() {
        if (dirty) { dirty = false; updateState() }
    }

    private fun add(r: SnapbackResult) {
        results += r
        val idx = results.size
        history.addView(ctx.text("%s  %3d · %-7s rebond %+4d · stabilisé en %.0f ms".format(
            if (r.passed) "✔" else "✘", idx, r.direction, r.overshoot, r.settleMs), 13f,
            color = if (r.passed) C.GREEN else C.RED).apply {
            setPadding(0, ctx.dp(4), 0, ctx.dp(4))
            setOnClickListener { show(r) }
        }, 0)
        show(r)
        for (d in dirs) {
            val rs = results.filter { it.direction == d }
            if (rs.isEmpty()) continue
            val worst = rs.maxBy { kotlin.math.abs(it.overshoot) }
            val fails = rs.count { !it.passed }
            dirText.getValue(d).apply {
                text = "%+d  (%d essai%s, %d hors zone)".format(worst.overshoot, rs.size, if (rs.size > 1) "s" else "", fails)
                setTextColor(if (fails == 0) C.GREEN else C.RED)
            }
        }
        val hz = rate.hz
        if (hz > 0) {
            var t = "Fréquence de l'adaptateur : <b>%.0f Hz</b>".format(hz)
            if (hz < 500) t += "<br><font color='#FFB347'>Une mesure toutes les %.0f ms : un rebond plus court peut passer entre deux mesures. Un adaptateur overclocké à 1000 Hz donne une courbe plus fidèle.</font>".format(1000 / hz)
            rateText.text = android.text.Html.fromHtml(t, android.text.Html.FROM_HTML_MODE_COMPACT)
        }
    }

    private fun show(r: SnapbackResult) {
        shown = r
        plot.result = r
        verdict.text = if (r.passed) "✔ OK : le rebond reste dans la zone morte de Melee"
        else "✘ Snapback : le rebond sort de la zone morte (±22)"
        verdict.setTextColor(if (r.passed) C.GREEN else C.RED)
        details.text = ("Lâcher vers la %s depuis %+d · rebond max côté opposé %+d · %d sortie(s) de zone · " +
            "stabilisé en %.0f ms\nX min/max (%+d, %+d) | Y min/max (%+d, %+d) · %d mesures, une toutes les %.1f ms").format(
            r.direction, r.startValue, r.overshoot, r.crossings, r.settleMs,
            r.minX, r.maxX, r.minY, r.maxY, r.samples.size, r.samplePeriodMs)
    }
}
