package fr.phobtool.ui

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.Html
import android.text.method.LinkMovementMethod
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView

/** Petite boîte à outils pour construire l'interface en code (sans AndroidX). */
object C {
    val BG = Color.parseColor("#1E1B2E")
    val CARD = Color.parseColor("#262238")
    val TEXT = Color.parseColor("#E8E4FF")
    val DIM = Color.parseColor("#8A84A8")
    val ACCENT = Color.parseColor("#8F7BEA")
    val ACCENT_DARK = Color.parseColor("#6A5ACD")
    val YELLOW = Color.parseColor("#FFD34D")
    val GREEN = Color.parseColor("#5FD38D")
    val RED = Color.parseColor("#FF6B6B")
    val ORANGE = Color.parseColor("#FFB347")
}

fun Context.dp(v: Number): Int =
    TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

fun Context.vbox(pad: Int = 0): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    setPadding(dp(pad), dp(pad), dp(pad), dp(pad))
}

fun Context.hbox(): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.HORIZONTAL
    gravity = Gravity.CENTER_VERTICAL
}

fun Context.text(s: CharSequence = "", size: Float = 14f, bold: Boolean = false, color: Int = C.TEXT): TextView =
    TextView(this).apply {
        text = s
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        setLineSpacing(0f, 1.1f)
    }

fun Context.html(s: String, size: Float = 14f): TextView = text(size = size).apply {
    text = Html.fromHtml(s, Html.FROM_HTML_MODE_COMPACT)
    movementMethod = LinkMovementMethod.getInstance()
    setLinkTextColor(C.ACCENT)
}

fun Context.card(title: String? = null): LinearLayout = vbox(12).apply {
    background = GradientDrawable().apply { setColor(C.CARD); cornerRadius = dp(10).toFloat() }
    if (title != null) addView(text(title, 15f, bold = true).apply { setPadding(0, 0, 0, dp(6)) })
}

fun Context.button(label: String, primary: Boolean = false, onClick: () -> Unit): Button =
    Button(this).apply {
        text = label
        isAllCaps = false
        setTextColor(Color.WHITE)
        background = GradientDrawable().apply {
            setColor(if (primary) C.ACCENT_DARK else Color.parseColor("#3A3456"))
            cornerRadius = dp(8).toFloat()
        }
        setPadding(dp(14), dp(8), dp(14), dp(8))
        minHeight = dp(42)
        setOnClickListener { onClick() }
    }

fun Context.spinner(items: List<String>, onSelect: (Int) -> Unit): Spinner = Spinner(this).apply {
    adapter = ArrayAdapter(context, android.R.layout.simple_spinner_item, items).also {
        it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
    }
    onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
        override fun onItemSelected(p: android.widget.AdapterView<*>?, v: View?, pos: Int, id: Long) = onSelect(pos)
        override fun onNothingSelected(p: android.widget.AdapterView<*>?) {}
    }
}

fun Spinner.setItems(items: List<String>) {
    @Suppress("UNCHECKED_CAST")
    val a = adapter as ArrayAdapter<String>
    a.clear(); a.addAll(items); a.notifyDataSetChanged()
}

fun Context.radios(labels: List<String>, onChange: (Int) -> Unit): RadioGroup = RadioGroup(this).apply {
    orientation = RadioGroup.HORIZONTAL
    labels.forEachIndexed { i, l ->
        addView(RadioButton(context).apply {
            id = View.generateViewId(); text = l; setTextColor(C.TEXT); tag = i
            if (i == 0) isChecked = true
        })
    }
    setOnCheckedChangeListener { g, id -> onChange(g.findViewById<View>(id).tag as Int) }
}

fun Context.progress(): ProgressBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
    max = 1000
}

fun ViewGroup.add(v: View, w: Int = ViewGroup.LayoutParams.MATCH_PARENT, h: Int = ViewGroup.LayoutParams.WRAP_CONTENT,
                  weight: Float = 0f, top: Int = 0): View {
    val lp = LinearLayout.LayoutParams(w, h, weight)
    lp.topMargin = context.dp(top)
    addView(v, lp)
    return v
}

fun ViewGroup.gap(dpv: Int = 10) = add(View(context), h = context.dp(dpv))

/** Interface commune aux pages de l'appli. */
interface Page {
    val view: View
    fun onShow() {}
    fun onHide() {}
    /** appelé sur le thread principal à chaque rapport de l'adaptateur */
    fun onPads(pads: List<fr.phobtool.core.PadState>?, status: String) {}
    /** appelé ~60 fois/s quand la page est visible */
    fun onFrame() {}
}
