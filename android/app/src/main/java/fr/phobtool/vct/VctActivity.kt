package fr.phobtool.vct

import android.os.Bundle
import android.os.Process
import fr.phobtool.usb.GcAdapter
import org.libsdl.app.SDLActivity

/** Pont JNI vers la couche PAD_* partagée (vct-pc/src/pad_pc.c, vct_jni.c). */
object VctBridge {
    /** rapport brut de 37 octets (ou null si l'adaptateur a disparu) ; renvoie le masque de rumble */
    @JvmStatic external fun nativeReport(data: ByteArray?): Int
}

/**
 * Programme SDL2 (VCT ou GTS) lancé dans son propre processus : SDL repart d'un état propre
 * à chaque lancement, et ce processus ouvre lui-même l'adaptateur pendant la partie.
 */
abstract class SdlToolActivity : SDLActivity() {
    private var adapter: GcAdapter? = null
    protected abstract val nativeLib: String

    override fun getLibraries(): Array<String> = arrayOf("SDL2", nativeLib)
    override fun getArguments(): Array<String> = arrayOf("--scale", "1")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (SDLActivity.mBrokenLibraries) return
        val a = GcAdapter(this)
        a.addListener { pads, _, raw ->
            val mask = VctBridge.nativeReport(if (pads != null) raw else null)
            a.setRumbleMask(mask)
        }
        a.start()
        adapter = a
    }

    override fun onDestroy() {
        adapter?.stop()
        adapter = null
        super.onDestroy()
        // l'état statique de SDL ne se réinitialise pas : on termine le processus
        Process.killProcess(Process.myPid())
    }
}

/** Visual Controller Test (processus ":vct"). */
class VctActivity : SdlToolActivity() {
    override val nativeLib = "vct"
}

/** GTS - GCC Test Suite (processus ":gts"). */
class GtsActivity : SdlToolActivity() {
    override val nativeLib = "gts"
}
