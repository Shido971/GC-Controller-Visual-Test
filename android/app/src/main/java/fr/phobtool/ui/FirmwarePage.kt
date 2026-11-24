package fr.phobtool.ui

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import fr.phobtool.fw.Asset
import fr.phobtool.fw.Board
import fr.phobtool.fw.FirmwareException
import fr.phobtool.fw.IntelHexImage
import fr.phobtool.fw.PicobootDevice
import fr.phobtool.fw.Release
import fr.phobtool.fw.Releases
import fr.phobtool.fw.TeensyLoader
import fr.phobtool.fw.TeensyModel
import fr.phobtool.fw.Uf2Image
import fr.phobtool.usb.UsbAccess
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

class FirmwarePage(private val act: Activity) : Page {
    companion object { const val REQ_PICK = 4242 }

    private val ui = Handler(Looper.getMainLooper())
    private val boards = listOf(Board.RP2040, Board.TEENSY40, Board.TEENSY32)
    private var board = Board.RP2040
    private var releases: List<Release> = emptyList()
    private var visible: List<Release> = emptyList()
    private var selected: Release? = null
    private var localFile: File? = null
    private val cancel = AtomicBoolean(false)
    private var busy = false

    private val releaseSpinner = act.spinner(listOf("Chargement…")) { i -> selected = visible.getOrNull(i); showRelease() }
    private val prerelease = CheckBox(act).apply { text = "Inclure les pré-versions"; setTextColor(C.TEXT) }
    private val assetText = act.text("—", 13f, color = C.DIM)
    private val localText = act.text("", 13f, color = C.DIM)
    private val notes = act.text("", 13f)
    private val stage = act.html("Prêt.", 15f)
    private val bar = act.progress()
    private val log = act.text("", 11f, color = C.DIM).apply { typeface = android.graphics.Typeface.MONOSPACE }
    private lateinit var flashBtn: View
    private lateinit var dlBtn: View
    private lateinit var cancelBtn: View

    override val view: View = ScrollView(act).apply {
        val root = act.vbox(12)
        addView(root)
        val top = act.card("Version à installer")
        top.add(act.text("Carte", 13f, color = C.DIM))
        top.add(act.spinner(boards.map { it.label }) { board = boards[it]; showRelease() })
        top.add(act.text("Release", 13f, color = C.DIM), top = 6)
        top.add(releaseSpinner)
        top.add(act.hbox().apply {
            add(prerelease, w = 0, weight = 1f)
            add(act.button("Actualiser") { refresh() }, w = LinearLayout.LayoutParams.WRAP_CONTENT)
        })
        top.add(assetText, top = 4)
        top.add(act.hbox().apply {
            add(act.button("Fichier local…") { pickLocal() }, w = 0, weight = 1f)
            add(View(act), w = act.dp(8))
            add(act.button("Oublier") { localFile = null; localText.text = "" }, w = 0, weight = 1f)
        }, top = 6)
        top.add(localText)
        root.add(top)
        root.gap()

        val fl = act.card("Mise à jour")
        fl.add(stage)
        fl.add(bar, top = 8)
        fl.add(act.hbox().apply {
            dlBtn = add(act.button("Télécharger") { start(downloadOnly = true) }, w = 0, weight = 1f)
            add(View(act), w = act.dp(6))
            flashBtn = add(act.button("Mettre à jour", primary = true) { start(downloadOnly = false) }, w = 0, weight = 1.4f)
            add(View(act), w = act.dp(6))
            cancelBtn = add(act.button("Annuler") { cancel.set(true) }, w = 0, weight = 1f)
        }, top = 8)
        cancelBtn.isEnabled = false
        fl.add(log, top = 8)
        root.add(fl)
        root.gap()
        val nb = act.card("Notes de version")
        nb.add(notes)
        root.add(nb)
        prerelease.setOnCheckedChangeListener { _, _ -> applyFilter() }
    }

    override fun onShow() { if (releases.isEmpty()) refresh() }

    private fun logLine(s: String) = ui.post { log.append(s + "\n") }
    private fun setStage(html: String) = ui.post { stage.text = android.text.Html.fromHtml(html, android.text.Html.FROM_HTML_MODE_COMPACT) }
    private fun setProgress(done: Long, total: Long) = ui.post {
        bar.isIndeterminate = total <= 0
        if (total > 0) bar.progress = (done * 1000 / total).toInt()
    }

    private fun refresh() {
        notes.text = "Chargement des releases depuis GitHub…"
        Thread {
            try {
                val (rel, warn) = Releases.fetch(act.filesDir)
                ui.post { releases = rel; applyFilter(); if (warn != null) logLine(warn) }
            } catch (e: Exception) {
                ui.post { notes.text = "Impossible de joindre GitHub : ${e.message}\nTu peux toujours flasher un fichier local." }
            }
        }.start()
    }

    private fun applyFilter() {
        visible = releases.filter { prerelease.isChecked || !it.prerelease }
        var latestMarked = false
        releaseSpinner.setItems(visible.map {
            var s = "${it.tag}  (${it.publishedAt})"
            if (it.prerelease) s += "  [pré-version]" else if (!latestMarked) { s += "  ★ dernière"; latestMarked = true }
            s
        }.ifEmpty { listOf("—") })
        selected = visible.firstOrNull()
        releaseSpinner.setSelection(0)
        showRelease()
    }

    private fun showRelease() {
        val r = selected ?: run { assetText.text = "—"; return }
        notes.text = "${r.name} — publiée le ${r.publishedAt}\n\n${r.body}"
        val a = r.firmwareFor(board)
        assetText.text = if (a != null) "${a.name} · ${a.size / 1024} Ko · " +
            (if (a.sha256 != null) "SHA-256 vérifié au téléchargement" else "pas d'empreinte publiée")
        else "Pas de fichier pour cette carte dans ${r.tag} (disponibles : ${r.firmwareAssets.joinToString { it.name }.ifEmpty { "aucun" }})"
    }

    private fun pickLocal() {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*")
        act.startActivityForResult(i, REQ_PICK)
    }

    /** appelé par MainActivity.onActivityResult */
    fun onPicked(uri: Uri) {
        val name = act.contentResolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
            ?: uri.lastPathSegment?.substringAfterLast('/')?.substringAfterLast(':') ?: "firmware.bin"
        val dest = File(act.cacheDir, name)
        act.contentResolver.openInputStream(uri)?.use { ins -> dest.outputStream().use { ins.copyTo(it) } }
        localFile = dest
        localText.text = "Fichier local : ${dest.name} (${dest.length() / 1024} Ko) — utilisé à la place de la release"
    }

    private fun setBusy(b: Boolean) = ui.post {
        busy = b
        flashBtn.isEnabled = !b; dlBtn.isEnabled = !b; cancelBtn.isEnabled = b
    }

    private fun start(downloadOnly: Boolean) {
        if (busy) return
        val r = selected
        val asset = r?.firmwareFor(board)
        val local = localFile
        if (local == null && asset == null) { stage.text = "Aucun firmware pour cette carte : choisis une autre release ou un fichier local."; return }
        cancel.set(false)
        log.text = ""
        setBusy(true)
        Thread { job(board, r, asset, local, downloadOnly) }.start()
    }

    private fun waitDevice(pred: (android.hardware.usb.UsbDevice) -> Boolean): android.hardware.usb.UsbDevice? {
        val end = SystemClock.elapsedRealtime() + 10 * 60_000
        while (SystemClock.elapsedRealtime() < end) {
            if (cancel.get()) return null
            UsbAccess.find(act, pred)?.let { return it }
            SystemClock.sleep(500)
        }
        return null
    }

    private fun job(board: Board, r: Release?, asset: Asset?, local: File?, downloadOnly: Boolean) {
        try {
            val fw: File = if (local != null) { logLine("Fichier local : ${local.name}"); local } else {
                setStage("<b>1/4 · Téléchargement</b><br>${asset!!.name} (${r!!.tag})")
                logLine("GET ${asset.url}")
                val f = Releases.download(asset, r.tag, File(act.filesDir, "firmware"), ::setProgress) { cancel.get() }
                logLine("Enregistré : ${f.name}")
                asset.sha256?.let { logLine("SHA-256 OK : $it") }
                f
            }
            if (board == Board.RP2040) {
                val img = Uf2Image.parse(fw.readBytes())
                logLine("UF2 valide : ${img.blocks} blocs, ${img.payloadBytes / 1024} Ko pour RP2040, ${img.sectors().size} secteurs")
                if (downloadOnly) return done(true, "Firmware prêt : ${fw.name}")
                setStage("<b>2/4 · Passe la manette en mode BOOTSEL</b><br>1. Débranche la manette.<br>2. <b>Maintiens Start</b> " +
                    "(ou le bouton BOOTSEL du PCB).<br>3. Branche le câble USB-C de la PhobGCC sur le téléphone (adaptateur OTG), " +
                    "puis relâche.<br>Je la détecte toute seule…")
                setProgress(0, 0)
                val dev = waitDevice(PicobootDevice::isBootrom) ?: throw InterruptedException("annulé")
                logLine("RP2040 en BOOTSEL détecté (${dev.deviceName})")
                if (!UsbAccess.requestBlocking(act, dev)) throw FirmwareException("accès USB refusé")
                setStage("<b>3/4 · Écriture du firmware</b><br>Ne débranche pas la manette.")
                PicobootDevice.open(UsbAccess.manager(act), dev).use { pb ->
                    pb.flash(img, { d, t, ph -> setProgress(d.toLong(), t.toLong()); if (d % 8 == 0 || d == t) logLine("$ph $d/$t") }) { cancel.get() }
                }
                setStage("<b>4/4 · Redémarrage…</b>")
                SystemClock.sleep(1500)
                done(true, "<b>Mise à jour terminée ✔</b><br>Flash écrit et relu sans erreur. Fais un <b>soft reset : " +
                    "A+B+Z+Start</b>. Si les sticks se comportent bizarrement, refais la calibration.")
            } else {
                val model = if (board == Board.TEENSY32) TeensyModel.TEENSY32 else TeensyModel.TEENSY40
                val img = IntelHexImage.parse(fw.readText(), model)
                val blocks = img.blocks().size
                logLine("HEX valide : ${img.byteCount / 1024} Ko, $blocks blocs pour ${model.label}")
                if (downloadOnly) return done(true, "Firmware prêt : ${fw.name}")
                setStage("<b>2/3 · Mode programmation du Teensy</b><br>Branche le Teensy en USB (OTG) puis appuie sur son " +
                    "bouton de programmation. Je le détecte tout seul…")
                setProgress(0, 0)
                val dev = waitDevice(TeensyLoader::isHalfKay) ?: throw InterruptedException("annulé")
                if (!UsbAccess.requestBlocking(act, dev)) throw FirmwareException("accès USB refusé")
                setStage("<b>3/3 · Écriture…</b> ne débranche pas.")
                TeensyLoader.open(UsbAccess.manager(act), dev).use { t ->
                    t.flash(img, { d, tot -> setProgress(d.toLong(), tot.toLong()) }) { cancel.get() }
                }
                done(true, "<b>Teensy programmé ✔</b><br>Fais un soft reset : A+B+Z+Start.")
            }
        } catch (e: InterruptedException) {
            done(false, "Interrompu : ${e.message}")
        } catch (e: Exception) {
            done(false, "Erreur : ${e.message}")
        }
    }

    private fun done(ok: Boolean, msg: String) {
        setBusy(false)
        ui.post { if (bar.isIndeterminate) { bar.isIndeterminate = false; bar.progress = 0 } }
        setStage(if (ok) msg else "<font color='#FF6B6B'>$msg</font>")
        logLine((if (ok) "✔ " else "✘ ") + android.text.Html.fromHtml(msg, android.text.Html.FROM_HTML_MODE_COMPACT))
    }
}
