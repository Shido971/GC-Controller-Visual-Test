package fr.phobtool

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Choreographer
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import fr.phobtool.core.PadState
import fr.phobtool.core.SnapbackDetector
import fr.phobtool.ui.C
import fr.phobtool.ui.FirmwarePage
import fr.phobtool.ui.HelpPage
import fr.phobtool.ui.Page
import fr.phobtool.ui.SnapbackPage
import fr.phobtool.ui.TestPage
import fr.phobtool.ui.VctPage
import fr.phobtool.ui.add
import fr.phobtool.ui.dp
import fr.phobtool.ui.hbox
import fr.phobtool.ui.text
import fr.phobtool.ui.vbox
import fr.phobtool.usb.GcAdapter
import kotlin.math.cos
import kotlin.math.sin

class MainActivity : Activity() {
    private val ui = Handler(Looper.getMainLooper())
    private lateinit var adapter: GcAdapter
    private lateinit var pages: List<Pair<String, Page>>
    private lateinit var firmware: FirmwarePage
    private var current = 0
    private val tabs = ArrayList<TextView>()
    private lateinit var content: FrameLayout
    private lateinit var status: TextView
    private var lastStatus = ""
    private var demo = false
    private var demoT0 = 0L
    private var demoSeq: List<fr.phobtool.core.Sample>? = null
    private var demoI = 0
    private var frameRunning = false

    private val listener = GcAdapter.Listener { pads, st, _ -> if (!demo) ui.post { dispatch(pads, st) } }

    private val frame = object : Choreographer.FrameCallback {
        override fun doFrame(t: Long) {
            if (!frameRunning) return
            if (demo) demoTick()
            pages[current].second.onFrame()
            status.text = lastStatus
            Choreographer.getInstance().postFrameCallback(this)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("DEPRECATION")
        window.statusBarColor = C.BG
        @Suppress("DEPRECATION")
        window.navigationBarColor = C.BG
        adapter = GcAdapter(this)
        firmware = FirmwarePage(this)
        pages = listOf(
            "Firmware" to firmware,
            "Test / calibration" to TestPage(this),
            "Snapback" to SnapbackPage(this),
            "VCT / GTS" to VctPage(this) { adapter.stop() },
            "Aide" to HelpPage(this) { on -> demo = on; demoT0 = SystemClock.uptimeMillis(); demoSeq = null },
        )

        val root = vbox().apply { setBackgroundColor(C.BG) }
        val header = vbox(12)
        header.add(text("PhobGCC Tool", 22f, bold = true))
        status = text("", 12f, color = C.DIM)
        header.add(status)
        root.add(header)

        val bar = hbox().apply { setPadding(dp(8), 0, dp(8), dp(6)) }
        pages.forEachIndexed { i, (name, _) ->
            val t = text(name, 14f, bold = true).apply {
                gravity = Gravity.CENTER
                setPadding(dp(14), dp(8), dp(14), dp(8))
                setOnClickListener { select(i) }
            }
            tabs += t
            bar.add(t, w = LinearLayout.LayoutParams.WRAP_CONTENT)
            bar.add(android.view.View(this), w = dp(6))
        }
        root.add(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(bar) })
        content = FrameLayout(this)
        root.add(content, h = 0, weight = 1f)
        setContentView(root)
        // Android 15+ : affichage bord à bord, on décale le contenu des barres système
        root.setOnApplyWindowInsetsListener { v, insets ->
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                val b = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.displayCutout())
                v.setPadding(b.left, b.top, b.right, b.bottom)
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        adapter.addListener(listener)
        select(intent?.getIntExtra("tab", 1) ?: 1)
        if (intent?.action == android.hardware.usb.UsbManager.ACTION_USB_DEVICE_ATTACHED) onUsbIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        onUsbIntent(intent)
    }

    /** branchement d'un RP2040 en BOOTSEL ou d'un Teensy : on montre l'onglet firmware */
    private fun onUsbIntent(intent: Intent) {
        @Suppress("DEPRECATION")
        val dev = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(android.hardware.usb.UsbManager.EXTRA_DEVICE)
        if (dev != null && !GcAdapter.isAdapter(dev)) select(0)
    }

    private fun select(i: Int) {
        if (::pages.isInitialized && current in pages.indices) pages[current].second.onHide()
        current = i
        content.removeAllViews()
        content.addView(pages[i].second.view)
        tabs.forEachIndexed { k, t ->
            t.setTextColor(if (k == i) Color.WHITE else C.DIM)
            t.background = if (k == i) GradientDrawable().apply { setColor(C.ACCENT_DARK); cornerRadius = dp(18).toFloat() } else null
        }
        pages[i].second.onShow()
    }

    private fun dispatch(pads: List<PadState>?, st: String) {
        val n = pads?.count { it.connected } ?: 0
        lastStatus = if (pads == null) st else "$st · $n manette(s)"
        // calibration et snapback reçoivent chaque rapport, même hors écran
        for ((_, p) in pages) p.onPads(pads, st)
    }

    override fun onStart() {
        super.onStart()
        if (!demo) adapter.start()
        frameRunning = true
        Choreographer.getInstance().postFrameCallback(frame)
    }

    override fun onStop() {
        frameRunning = false
        adapter.stop()   // libère l'adaptateur pour VCT ou une autre appli
        super.onStop()
    }

    override fun onDestroy() {
        adapter.removeListener(listener)
        super.onDestroy()
    }

    @Deprecated("API Activity simple, sans AndroidX")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FirmwarePage.REQ_PICK && resultCode == RESULT_OK) data?.data?.let { firmware.onPicked(it) }
    }

    // ------------------------------------------------------------- démo
    private fun demoTick() {
        val now = SystemClock.elapsedRealtimeNanos() / 1e9
        if (current == 2) {
            var seq = demoSeq
            if (seq == null) {
                val s = ArrayList<fr.phobtool.core.Sample>()
                var t = now
                for ((st, ax, ov) in listOf(Triple(100.0, 'x', 0.45), Triple(-98.0, 'x', 0.12), Triple(96.0, 'y', 0.2), Triple(-95.0, 'y', 0.4))) {
                    val part = SnapbackDetector.simulateRelease(start = st, axis = ax, overshoot = ov, holdMs = 300.0, afterMs = 500.0, t0 = t)
                    s += part; t = part.last().t + 0.001
                }
                seq = s; demoSeq = s; demoI = 0
            }
            while (demoI < seq.size && seq[demoI].t <= now) {
                val p = seq[demoI++]
                dispatch(listOf(PadState(true, false, emptySet(), p.x + 128, p.y + 128, 128, 128, 0, 0, p.t),
                    PadState(), PadState(), PadState()), "démo")
            }
            if (demoI >= seq.size) demoSeq = null
            return
        }
        val t = (SystemClock.uptimeMillis() - demoT0) / 1000.0
        val btn = if ((t * 2).toInt() % 3 == 0) setOf("A") else emptySet()
        dispatch(listOf(PadState(true, false, btn,
            (128 + 100 * cos(t * 1.5)).toInt(), (128 + 100 * sin(t * 1.5)).toInt(),
            (128 + 70 * cos(t * 0.7 + 1)).toInt(), (128 + 70 * sin(t * 0.9)).toInt(),
            (127 + 127 * sin(t)).toInt(), (127 - 127 * sin(t)).toInt(), now), PadState(), PadState(), PadState()), "démo")
    }
}
