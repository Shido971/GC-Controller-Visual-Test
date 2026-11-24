package fr.phobtool.fw

import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

enum class Board(val label: String) {
    RP2040("PhobGCC 2.x (RP2040, .uf2)"),
    TEENSY40("PhobGCC 1.x – Teensy 4.0 (.hex)"),
    TEENSY32("PhobGCC 1.x – Teensy 3.2 (.hex)"),
    UNKNOWN("Autre fichier");

    companion object {
        fun classify(name: String): Board {
            val n = name.lowercase()
            if (n.endsWith(".uf2")) return RP2040
            if (n.endsWith(".hex")) {
                val m = Regex("teensy[^0-9]*([34])[^0-9]?([0-9])").find(n)
                return if (m != null && m.groupValues[1] == "3") TEENSY32 else TEENSY40
            }
            return UNKNOWN
        }
    }
}

data class Asset(val name: String, val url: String, val size: Long, val sha256: String?, val board: Board)

data class Release(
    val tag: String, val name: String, val publishedAt: String, val prerelease: Boolean,
    val body: String, val htmlUrl: String, val assets: List<Asset>,
) {
    fun firmwareFor(b: Board) = assets.firstOrNull { it.board == b }
    val firmwareAssets get() = assets.filter { it.board != Board.UNKNOWN }
}

object Releases {
    const val API = "https://api.github.com/repos/PhobGCC/PhobGCC-SW/releases"
    private const val UA = "PhobGCC-Tool-Android/0.1"

    fun parse(json: String): List<Release> {
        val arr = JSONArray(json)
        val out = ArrayList<Release>()
        for (i in 0 until arr.length()) {
            val r = arr.getJSONObject(i)
            if (r.optBoolean("draft")) continue
            val assets = ArrayList<Asset>()
            val ja = r.optJSONArray("assets") ?: JSONArray()
            for (k in 0 until ja.length()) {
                val a = ja.getJSONObject(k)
                val digest = a.optString("digest", "")
                val sha = if (digest.startsWith("sha256:")) digest.substring(7).lowercase() else null
                val name = a.getString("name")
                assets += Asset(name, a.getString("browser_download_url"), a.optLong("size"), sha, Board.classify(name))
            }
            out += Release(
                r.optString("tag_name"), r.optString("name").ifEmpty { r.optString("tag_name") },
                r.optString("published_at").take(10), r.optBoolean("prerelease"),
                r.optString("body"), r.optString("html_url"), assets)
        }
        return out
    }

    private fun open(url: String, accept: String): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.setRequestProperty("User-Agent", UA)
        c.setRequestProperty("Accept", accept)
        c.connectTimeout = 15000
        c.readTimeout = 30000
        c.instanceFollowRedirects = true
        return c
    }

    /** Interroge GitHub ; en cas d'échec réseau, réutilise la dernière réponse en cache. */
    fun fetch(cacheDir: File): Pair<List<Release>, String?> {
        val cache = File(cacheDir, "releases.json")
        return try {
            val c = open("$API?per_page=15", "application/vnd.github+json")
            val code = c.responseCode
            if (code != 200) throw Exception("GitHub a répondu $code")
            val txt = c.inputStream.bufferedReader().use { it.readText() }
            cache.writeText(txt)
            parse(txt) to null
        } catch (e: Exception) {
            if (cache.exists()) parse(cache.readText()) to "hors-ligne : ${e.message}" else throw e
        }
    }

    fun sha256(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { ins ->
            val buf = ByteArray(65536)
            while (true) { val n = ins.read(buf); if (n < 0) break; md.update(buf, 0, n) }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    fun download(a: Asset, tag: String, dir: File, progress: (Long, Long) -> Unit, cancelled: () -> Boolean): File {
        val d = File(dir, tag).apply { mkdirs() }
        val dest = File(d, a.name)
        if (dest.exists() && dest.length() == a.size && a.size > 0 && (a.sha256 == null || sha256(dest) == a.sha256)) {
            progress(a.size, a.size); return dest
        }
        val tmp = File(d, a.name + ".part")
        val c = open(a.url, "application/octet-stream")
        if (c.responseCode != 200) throw Exception("téléchargement refusé (${c.responseCode})")
        val total = if (c.contentLengthLong > 0) c.contentLengthLong else a.size
        c.inputStream.use { ins ->
            tmp.outputStream().use { out ->
                val buf = ByteArray(32768)
                var done = 0L
                while (true) {
                    if (cancelled()) throw InterruptedException("téléchargement annulé")
                    val n = ins.read(buf); if (n < 0) break
                    out.write(buf, 0, n); done += n; progress(done, total)
                }
            }
        }
        if (a.sha256 != null) {
            val got = sha256(tmp)
            if (got != a.sha256) { tmp.delete(); throw FirmwareException("SHA-256 incorrect pour ${a.name}\nattendu ${a.sha256}\nobtenu  $got") }
        }
        if (dest.exists()) dest.delete()
        tmp.renameTo(dest)
        return dest
    }
}
