package fr.phobtool.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View
import fr.phobtool.core.Cal
import fr.phobtool.core.Snap
import fr.phobtool.core.SnapbackResult
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.min

private const val RANGE = 128f

/** Stick : gate, encoches, position live, cible et traînée. */
class StickView(ctx: Context, var title: String, private val color: Int) : View(ctx) {
    var pos: Pair<Float, Float>? = null
    var target: Pair<Float, Float>? = null
    var highlight: Int? = null
    var subtitle = ""
    private val trail = ArrayDeque<Pair<Float, Float>>()
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)

    fun set(pos: Pair<Int, Int>?, target: Pair<Double, Double>? = null, highlight: Int? = null, subtitle: String = "") {
        this.pos = pos?.let { it.first.toFloat() to it.second.toFloat() }
        this.target = target?.let { it.first.toFloat() to it.second.toFloat() }
        this.highlight = highlight
        this.subtitle = subtitle
        this.pos?.let { trail.addLast(it); if (trail.size > 60) trail.removeFirst() }
        invalidate()
    }

    fun clearTrail() { trail.clear(); invalidate() }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, (width * 1.22f).toInt())
    }

    override fun onDraw(c: Canvas) {
        val w = width.toFloat()
        val top = context.dp(22).toFloat()
        val bottom = context.dp(36).toFloat()
        val size = min(w, height - top - bottom) - context.dp(6)
        val cx = w / 2
        val cy = top + (height - top - bottom) / 2
        val rad = size / 2
        fun px(x: Float, y: Float) = (cx + x / RANGE * rad) to (cy - y / RANGE * rad)

        p.style = Paint.Style.FILL; p.color = C.TEXT; p.textSize = context.dp(13).toFloat()
        p.textAlign = Paint.Align.CENTER; p.isFakeBoldText = true
        c.drawText(title, cx, top - context.dp(6), p)
        p.isFakeBoldText = false

        p.color = Color.argb(40, 0, 0, 0); c.drawCircle(cx, cy, rad, p)
        p.style = Paint.Style.STROKE; p.strokeWidth = 2f; p.color = Color.argb(70, 232, 228, 255)
        c.drawCircle(cx, cy, rad, p)
        val gate = Path()
        for (i in 0 until 16 step 2) {
            val (x, y) = Cal.notchTarget(i).let { px(it.first.toFloat(), it.second.toFloat()) }
            if (i == 0) gate.moveTo(x, y) else gate.lineTo(x, y)
        }
        gate.close(); c.drawPath(gate, p)
        c.drawLine(cx - rad, cy, cx + rad, cy, p); c.drawLine(cx, cy - rad, cx, cy + rad, p)

        for (i in 0 until 16) {
            val (x, y) = Cal.notchTarget(i).let { px(it.first.toFloat(), it.second.toFloat()) }
            if (highlight == i) {
                p.style = Paint.Style.FILL; p.color = Color.argb(90, 255, 211, 77); c.drawCircle(x, y, context.dp(9).toFloat(), p)
                p.style = Paint.Style.STROKE; p.color = C.YELLOW; c.drawCircle(x, y, context.dp(9).toFloat(), p)
            } else {
                p.style = Paint.Style.FILL; p.color = Color.argb(70, 232, 228, 255)
                c.drawCircle(x, y, context.dp(if (i % 2 == 0) 3 else 2).toFloat(), p)
            }
        }
        if (trail.size > 1) {
            p.style = Paint.Style.STROKE; p.strokeWidth = context.dp(2).toFloat()
            val l = trail.toList()
            for (i in 1 until l.size) {
                p.color = Color.argb(20 + 120 * i / l.size, Color.red(color), Color.green(color), Color.blue(color))
                val (a1, b1) = px(l[i - 1].first, l[i - 1].second); val (a2, b2) = px(l[i].first, l[i].second)
                c.drawLine(a1, b1, a2, b2, p)
            }
        }
        target?.let { (tx, ty) ->
            val (x, y) = px(tx, ty)
            p.style = Paint.Style.STROKE; p.color = C.YELLOW; p.strokeWidth = context.dp(2).toFloat()
            val r = context.dp(10).toFloat()
            c.drawCircle(x, y, r, p); c.drawLine(x - r * 1.5f, y, x + r * 1.5f, y, p); c.drawLine(x, y - r * 1.5f, x, y + r * 1.5f, p)
        }
        pos?.let { (sx, sy) ->
            val (x, y) = px(sx, sy)
            p.style = Paint.Style.FILL; p.color = color; c.drawCircle(x, y, context.dp(7).toFloat(), p)
            p.style = Paint.Style.STROKE; p.color = Color.WHITE; p.strokeWidth = 2f; c.drawCircle(x, y, context.dp(7).toFloat(), p)
        }
        p.style = Paint.Style.FILL; p.color = C.TEXT; p.textSize = context.dp(11).toFloat()
        val line1 = pos?.let { (x, y) ->
            var a = Math.toDegrees(atan2(y.toDouble(), x.toDouble())); if (a < 0) a += 360.0
            "x %+4.0f  y %+4.0f  %5.1f°  r %3.0f".format(x, y, a, hypot(x, y))
        } ?: "—"
        c.drawText(line1, cx, height - bottom + context.dp(14), p)
        if (subtitle.isNotEmpty()) { p.color = C.DIM; c.drawText(subtitle, cx, height - bottom + context.dp(30), p) }
    }
}

class TriggerBar(ctx: Context, private val label: String) : View(ctx) {
    var value = 0; var digital = false
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    fun set(v: Int, d: Boolean) { value = v; digital = d; invalidate() }
    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat()
        val top = context.dp(18).toFloat(); val bot = h - context.dp(18)
        val bw = context.dp(14).toFloat()
        val bar = RectF(w / 2 - bw / 2, top, w / 2 + bw / 2, bot)
        p.style = Paint.Style.STROKE; p.color = C.DIM; c.drawRoundRect(bar, 6f, 6f, p)
        p.style = Paint.Style.FILL; p.color = if (digital) C.YELLOW else C.ACCENT
        val fill = bar.height() * value / 255f
        c.drawRoundRect(RectF(bar.left, bar.bottom - fill, bar.right, bar.bottom), 6f, 6f, p)
        p.color = C.TEXT; p.textAlign = Paint.Align.CENTER; p.textSize = context.dp(12).toFloat()
        c.drawText(label, w / 2, context.dp(13).toFloat(), p)
        c.drawText("$value", w / 2, h - context.dp(3), p)
    }
}

/** Graphe temporel d'un lâcher (façon oscilloscope GTS). */
class SnapbackPlotView(ctx: Context) : View(ctx) {
    var result: SnapbackResult? = null
        set(v) { field = v; invalidate() }
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val dash = DashPathEffect(floatArrayOf(10f, 8f), 0f)

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, (width * 0.72f).toInt())
    }

    override fun onDraw(c: Canvas) {
        val left = context.dp(34).toFloat(); val right = context.dp(6).toFloat()
        val top = context.dp(6).toFloat(); val bottom = context.dp(22).toFloat()
        val plot = RectF(left, top, width - right, height - bottom)
        fun ypx(v: Float) = plot.centerY() - v / 128f * plot.height() / 2
        p.pathEffect = null
        p.style = Paint.Style.FILL; p.color = Color.argb(40, 0, 0, 0); c.drawRect(plot, p)
        p.color = Color.argb(30, 95, 211, 141)
        c.drawRect(plot.left, ypx(Snap.MELEE_DEADZONE + 0.5f), plot.right, ypx(-Snap.MELEE_DEADZONE - 0.5f), p)
        p.textSize = context.dp(10).toFloat(); p.textAlign = Paint.Align.RIGHT
        for ((v, col, dashed) in listOf(Triple(0, C.DIM, false), Triple(23, C.GREEN, true), Triple(-23, C.GREEN, true),
                Triple(64, C.DIM, true), Triple(-64, C.DIM, true), Triple(80, C.DIM, true), Triple(-80, C.DIM, true))) {
            p.style = Paint.Style.STROKE; p.strokeWidth = 1.5f; p.color = col
            p.pathEffect = if (dashed) dash else null
            c.drawLine(plot.left, ypx(v.toFloat()), plot.right, ypx(v.toFloat()), p)
            p.pathEffect = null; p.style = Paint.Style.FILL
            c.drawText(if (v == 0) "0" else "%+d".format(v), left - context.dp(4), ypx(v.toFloat()) + context.dp(4), p)
        }
        val r = result
        if (r == null || r.samples.size < 2) {
            p.color = C.TEXT; p.textAlign = Paint.Align.CENTER; p.textSize = context.dp(13).toFloat()
            c.drawText("Pousse le stick à fond, maintiens, puis lâche-le d'un coup.", plot.centerX(), plot.centerY() - context.dp(40), p)
            return
        }
        val t0 = r.samples.first().t; val t1 = r.samples.last().t
        val span = maxOf(t1 - t0, 1e-3)
        fun xpx(t: Double) = (plot.left + (t - t0) / span * plot.width()).toFloat()
        val spanMs = span * 1000
        val step = if (spanMs <= 150) 10 else if (spanMs <= 400) 25 else 100
        var ms = -(((r.t0 - t0) * 1000).toInt() / step) * step
        p.textAlign = Paint.Align.CENTER
        while (ms <= (t1 - r.t0) * 1000) {
            val x = xpx(r.t0 + ms / 1000.0)
            if (x in plot.left..plot.right) {
                p.color = Color.argb(50, 232, 228, 255); p.style = Paint.Style.STROKE; p.pathEffect = dash
                c.drawLine(x, plot.top, x, plot.bottom, p)
                p.pathEffect = null; p.style = Paint.Style.FILL; p.color = C.DIM
                c.drawText("$ms ms", x, height - context.dp(6).toFloat(), p)
            }
            ms += step
        }
        val otherAxis = if (r.axis == 'x') 'y' else 'x'
        for ((axis, col, sw) in listOf(Triple(otherAxis, Color.argb(120, 255, 211, 77), 2f), Triple(r.axis, C.ACCENT, 4f))) {
            val vals = r.values(axis)
            val path = Path()
            r.samples.forEachIndexed { i, s ->
                val x = xpx(s.t); val y = ypx(vals[i].toFloat())
                if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            p.style = Paint.Style.STROKE; p.strokeWidth = sw; p.color = col; c.drawPath(path, p)
            if (axis == r.axis && vals.size <= 300) {
                p.style = Paint.Style.FILL
                r.samples.forEachIndexed { i, s -> c.drawCircle(xpx(s.t), ypx(vals[i].toFloat()), 3.5f, p) }
            }
        }
        if (r.overshoot != 0) {
            val vals = r.values()
            val i = vals.indexOf(r.overshoot)
            val x = xpx(r.samples[i].t); val y = ypx(r.overshoot.toFloat())
            val col = if (r.passed) C.GREEN else C.RED
            p.style = Paint.Style.STROKE; p.color = col; p.strokeWidth = 3f
            c.drawCircle(x, y, context.dp(7).toFloat(), p)
            p.style = Paint.Style.FILL; p.isFakeBoldText = true; p.textSize = context.dp(12).toFloat()
            c.drawText("rebond %+d".format(r.overshoot), x, y + if (r.overshoot < 0) context.dp(22) else -context.dp(12), p)
            p.isFakeBoldText = false
        }
    }
}
