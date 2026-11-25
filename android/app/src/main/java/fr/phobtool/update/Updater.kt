package fr.phobtool.update

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import fr.phobtool.ui.progress
import fr.phobtool.ui.text
import fr.phobtool.ui.vbox
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** Description du dernier build publié (version.json de la release « latest »). */
data class UpdateInfo(val build: Long, val sha: String, val date: String, val apkUrl: String?, val apkName: String?) {
    val label get() = "build $build" + if (sha.isNotEmpty()) " (${sha.take(7)}, $date)" else ""

    companion object {
        fun parse(json: String): UpdateInfo {
            val o = JSONObject(json)
            val a = o.optJSONObject("assets")?.optJSONObject("android")
            return UpdateInfo(o.optLong("build"), o.optString("sha"), o.optString("date"),
                a?.optString("url")?.ifEmpty { null }, a?.optString("name")?.ifEmpty { null })
        }
    }
}

/**
 * Vérifie et installe les mises à jour de l'appli depuis les Releases GitHub du projet.
 * L'installation passe par PackageInstaller : Android affiche sa propre confirmation.
 */
class Updater(private val act: Activity) {
    companion object {
        const val REPO = "Shido971/GC-Controller-Visual-Test"
        const val VERSION_URL = "https://github.com/$REPO/releases/download/latest/version.json"
        const val PAGE_URL = "https://github.com/$REPO/releases/tag/latest"
        private const val ACTION = "fr.phobtool.UPDATE_INSTALL_RESULT"
        private const val PREFS = "update"

        @Suppress("DEPRECATION")
        fun currentBuild(ctx: Context): Long {
            val pi = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
            return if (Build.VERSION.SDK_INT >= 28) pi.longVersionCode else pi.versionCode.toLong()
        }

        fun currentLabel(ctx: Context): String {
            val pi = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
            return "${pi.versionName} · build ${currentBuild(ctx)}"
        }

        fun autoCheck(ctx: Context) = ctx.getSharedPreferences(PREFS, 0).getBoolean("auto", true)
        fun setAutoCheck(ctx: Context, on: Boolean) = ctx.getSharedPreferences(PREFS, 0).edit().putBoolean("auto", on).apply()
    }

    private val ui = Handler(Looper.getMainLooper())
    @Volatile private var busy = false
    private var pendingApk: File? = null
    private var receiver: BroadcastReceiver? = null
    /** message d'état pour la page Aide */
    var onStatus: (String) -> Unit = {}

    private fun open(url: String): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        setRequestProperty("User-Agent", "PhobGCC-Tool-Android")
        setRequestProperty("Cache-Control", "no-cache")
        connectTimeout = 15000; readTimeout = 30000; instanceFollowRedirects = true
    }

    fun check(manual: Boolean) {
        if (busy) return
        busy = true
        onStatus("Recherche d'une mise à jour…")
        Thread {
            val res = runCatching {
                val c = open(VERSION_URL)
                if (c.responseCode != 200) throw Exception("GitHub a répondu ${c.responseCode}")
                UpdateInfo.parse(c.inputStream.bufferedReader().use { it.readText() })
            }
            ui.post {
                busy = false
                res.onFailure { onStatus("Impossible de vérifier les mises à jour : ${it.message}") }
                res.onSuccess { info -> onChecked(info, manual) }
            }
        }.start()
    }

    private fun onChecked(info: UpdateInfo, manual: Boolean) {
        if (act.isFinishing) return
        val cur = currentBuild(act)
        if (info.build <= cur) {
            onStatus("✔ L'appli est à jour (${currentLabel(act)}).")
            if (manual) AlertDialog.Builder(act).setTitle("Mise à jour").setMessage("Tu as déjà la dernière version.")
                .setPositiveButton("OK", null).show()
            return
        }
        onStatus("Nouvelle version disponible : ${info.label}")
        if (info.apkUrl == null) return
        AlertDialog.Builder(act)
            .setTitle("Mise à jour disponible")
            .setMessage("Une nouvelle version de PhobGCC Tool est disponible (${info.label}).\n" +
                "Version installée : ${currentLabel(act)}.\n\nLa télécharger et l'installer maintenant ?")
            .setPositiveButton("Mettre à jour") { _, _ -> download(info) }
            .setNegativeButton("Plus tard", null)
            .show()
    }

    private fun download(info: UpdateInfo) {
        busy = true
        val box = act.vbox(20)
        val label = act.text("Téléchargement…")
        val bar = act.progress()
        box.addView(label); box.addView(bar)
        val cancelled = java.util.concurrent.atomic.AtomicBoolean(false)
        val dlg = AlertDialog.Builder(act).setTitle("Mise à jour").setView(box)
            .setNegativeButton("Annuler") { _, _ -> cancelled.set(true) }.setCancelable(false).show()
        Thread {
            val res = runCatching {
                val dir = File(act.cacheDir, "update").apply { deleteRecursively(); mkdirs() }
                val dest = File(dir, "PhobGCCTool.apk")
                val c = open(info.apkUrl!!)
                if (c.responseCode != 200) throw Exception("téléchargement refusé (${c.responseCode})")
                val total = c.contentLengthLong
                c.inputStream.use { ins ->
                    dest.outputStream().use { out ->
                        val buf = ByteArray(65536); var done = 0L
                        while (true) {
                            if (cancelled.get()) throw InterruptedException("annulé")
                            val n = ins.read(buf); if (n < 0) break
                            out.write(buf, 0, n); done += n
                            ui.post {
                                if (total > 0) bar.progress = (done * 1000 / total).toInt()
                                label.text = "Téléchargement… %.1f / %.1f Mo".format(done / 1e6, total / 1e6)
                            }
                        }
                    }
                }
                dest
            }
            ui.post {
                busy = false
                dlg.dismiss()
                res.onFailure { if (!cancelled.get()) error("Échec du téléchargement : ${it.message}") }
                res.onSuccess { install(it) }
            }
        }.start()
    }

    // ---------------------------------------------------------------- installation
    @Suppress("DEPRECATION")
    private fun signatures(pi: PackageInfo?): Set<String> {
        if (pi == null) return emptySet()
        val sigs = if (Build.VERSION.SDK_INT >= 28) pi.signingInfo?.apkContentsSigners else pi.signatures
        return sigs.orEmpty().map { s ->
            MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }
        }.toSet()
    }

    @Suppress("DEPRECATION")
    private fun sameSigner(apk: File): Boolean? {
        val flag = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val newSig = signatures(act.packageManager.getPackageArchiveInfo(apk.path, flag))
        val curSig = signatures(act.packageManager.getPackageInfo(act.packageName, flag))
        if (newSig.isEmpty() || curSig.isEmpty()) return null
        return newSig == curSig
    }

    private fun install(apk: File) {
        if (sameSigner(apk) == false) {
            AlertDialog.Builder(act).setTitle("Réinstallation nécessaire")
                .setMessage("Cette nouvelle version est signée avec une autre clé que celle installée " +
                    "(les anciennes versions étaient signées avec une clé temporaire).\n\n" +
                    "Android refuse ce type de mise à jour : désinstalle PhobGCC Tool, puis installe le nouvel APK " +
                    "depuis la page des téléchargements. Ce ne sera nécessaire qu'une seule fois.")
                .setPositiveButton("Ouvrir la page") { _, _ ->
                    act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(PAGE_URL)))
                }
                .setNegativeButton("Fermer", null).show()
            return
        }
        if (Build.VERSION.SDK_INT >= 26 && !act.packageManager.canRequestPackageInstalls()) {
            pendingApk = apk
            AlertDialog.Builder(act).setTitle("Autorisation nécessaire")
                .setMessage("Pour installer la mise à jour, autorise PhobGCC Tool à installer des applications, " +
                    "puis reviens dans l'appli : l'installation reprendra toute seule.")
                .setPositiveButton("Autoriser") { _, _ ->
                    act.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${act.packageName}")))
                }
                .setNegativeButton("Annuler") { _, _ -> pendingApk = null }.show()
            return
        }
        runCatching { commit(apk) }.onFailure { error("Installation impossible : ${it.message}") }
    }

    /** À appeler dans onResume : reprend l'installation après l'autorisation. */
    fun onResume() {
        val apk = pendingApk ?: return
        if (Build.VERSION.SDK_INT >= 26 && !act.packageManager.canRequestPackageInstalls()) return
        pendingApk = null
        install(apk)
    }

    private fun commit(apk: File) {
        registerReceiver()
        val pi = act.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(act.packageName)
        if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        val id = pi.createSession(params)
        pi.openSession(id).use { s ->
            s.openWrite("base.apk", 0, apk.length()).use { out ->
                apk.inputStream().use { it.copyTo(out, 65536) }
                s.fsync(out)
            }
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
            val intent = Intent(ACTION).setPackage(act.packageName)
            s.commit(PendingIntent.getBroadcast(act, id, intent, flags).intentSender)
        }
        onStatus("Installation de la mise à jour…")
    }

    private fun registerReceiver() {
        if (receiver != null) return
        val r = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                when (val st = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
                    PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                        @Suppress("DEPRECATION")
                        val confirm = i.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                        if (confirm != null) act.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }
                    PackageInstaller.STATUS_SUCCESS -> onStatus("Mise à jour installée.")
                    PackageInstaller.STATUS_FAILURE_ABORTED -> onStatus("Installation annulée.")
                    else -> {
                        val msg = i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "erreur $st"
                        val hint = if (st == PackageInstaller.STATUS_FAILURE_CONFLICT || st == PackageInstaller.STATUS_FAILURE_INCOMPATIBLE)
                            "\n\nDésinstalle l'appli puis installe le nouvel APK depuis la page des téléchargements (une seule fois)." else ""
                        error("Installation refusée : $msg$hint")
                    }
                }
            }
        }
        val f = IntentFilter(ACTION)
        if (Build.VERSION.SDK_INT >= 33) act.registerReceiver(r, f, Context.RECEIVER_NOT_EXPORTED)
        else @Suppress("UnspecifiedRegisterReceiverFlag") act.registerReceiver(r, f)
        receiver = r
    }

    fun release() {
        receiver?.let { runCatching { act.unregisterReceiver(it) } }
        receiver = null
    }

    private fun error(msg: String) {
        onStatus(msg)
        if (!act.isFinishing) AlertDialog.Builder(act).setTitle("Mise à jour").setMessage(msg).setPositiveButton("OK", null).show()
    }
}
