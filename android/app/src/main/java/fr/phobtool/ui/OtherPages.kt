package fr.phobtool.ui

import android.app.Activity
import android.content.Intent
import android.view.View
import android.widget.CheckBox
import android.widget.ScrollView
import fr.phobtool.vct.GtsActivity
import fr.phobtool.vct.VctActivity

class VctPage(private val act: Activity, private val beforeLaunch: () -> Unit) : Page {
    override val view: View = ScrollView(act).apply {
        val root = act.vbox(12)
        addView(root)
        val c = act.card("Visual Controller Test")
        c.add(act.html("Portage natif de <b>Visual Controller Test</b> (Mr. Reaper / Zarithya). Le <tt>main.c</tt> Wii " +
            "d'origine est compilé sans modification avec SDL2 ; l'appli lui transmet les rapports de " +
            "l'<b>adaptateur GameCube officiel</b>.<br><br>Quitter : <b>Start+B+X</b> sur la manette ou le bouton retour.", 14f))
        c.add(act.button("▶  Lancer Visual Controller Test", primary = true) {
            beforeLaunch()
            act.startActivity(Intent(act, VctActivity::class.java))
        }, top = 12)
        root.add(c)
        root.gap()
        val g = act.card("GTS – GCC Test Suite")
        g.add(act.html("Portage natif de <b>GTS</b> (greenwave-1), l'alternative libre à SmashScope : test manette, " +
            "oscilloscopes (snapback, dashback…), gâchettes, visualiseur de coordonnées Melee, tracé 2D, " +
            "chronométrage des boutons et visualiseur de gate. Mêmes écrans que sur console.<br><br>" +
            "Quitter : maintenir <b>Start</b> dans le menu principal, ou le bouton retour. " +
            "La précision des oscilloscopes dépend de la fréquence de l'adaptateur.", 14f))
        g.add(act.button("▶  Lancer GTS", primary = true) {
            beforeLaunch()
            act.startActivity(Intent(act, GtsActivity::class.java))
        }, top = 12)
        root.add(g)
        root.add(act.text("Le programme s'ouvre en paysage. L'adaptateur lui est prêté pendant l'utilisation puis rendu à l'appli. " +
            "GTS est distribué sous licence GPL-3.0.", 12f, color = C.DIM), top = 8)
    }
}

class HelpPage(act: Activity, onDemo: (Boolean) -> Unit) : Page {
    override val view: View = ScrollView(act).apply {
        val root = act.vbox(12)
        addView(root)
        val c = act.card()
        c.add(act.html(HELP, 14f))
        root.add(c)
        root.gap()
        val d = act.card("Mode démo")
        d.add(CheckBox(act).apply {
            text = "Manette virtuelle (pour essayer l'appli sans matériel)"
            setTextColor(C.TEXT)
            setOnCheckedChangeListener { _, on -> onDemo(on) }
        })
        root.add(d)
    }

    companion object {
        const val HELP = """
<h3>Matériel</h3>
• Un câble ou adaptateur <b>USB OTG</b> (USB-C → USB-A femelle).<br>
• <b>Mise à jour PhobGCC 2</b> : le câble USB-C branché directement sur le PCB de la Phob.<br>
• <b>Test, calibration, snapback, VCT</b> : l'adaptateur GameCube officiel (WUP-028) ou un clone compatible,
interrupteur en position <b>Wii U / PC</b>. Le câble noir suffit pour les données ; le gris (alimentation du rumble)
nécessite un hub OTG alimenté.<br>
• Si l'adaptateur n'est pas détecté, le téléphone n'alimente peut-être pas assez : essaie un hub OTG alimenté.
<h3>Mettre à jour une PhobGCC 2</h3>
1. Choisis la release (la plus récente est sélectionnée) et appuie sur « Mettre à jour ».<br>
2. Débranche la manette, <b>maintiens Start</b> (ou le bouton BOOTSEL du PCB) et branche l'USB-C : l'appli détecte
le bootloader du RP2040 et écrit le firmware directement (protocole PICOBOOT, comme picotool), puis relit chaque
secteur pour vérifier.<br>
3. La manette redémarre. Fais un <b>soft reset (A+B+Z+Start)</b>.<br>
Le fichier est contrôlé avant écriture : empreinte SHA-256 publiée par GitHub, structure UF2 et famille RP2040.
<h3>PhobGCC 1.x (Teensy)</h3>
Choisis le bon modèle (4.0 ou 3.2) ; l'appli refuse un .hex qui ne rentre pas dans sa mémoire. Branche le Teensy
et appuie sur son bouton de programmation quand l'appli le demande.
<h3>Calibrer</h3>
Branche la manette sur l'adaptateur, choisis le stick, « Démarrer », puis fais le combo indiqué (hors safe mode).
Le firmware affiche la cible sur l'autre stick : l'appli la lit et te guide étape par étape (32 mesures puis
12 ajustements d'encoches).
<h3>Snapback</h3>
Même principe que l'oscilloscope de GTS. La précision dépend de la fréquence de l'adaptateur (125 Hz d'origine,
1000 Hz si overclocké), affichée dans l'onglet.
<h3>Liens</h3>
<a href="https://github.com/PhobGCC/PhobGCC-SW">PhobGCC-SW</a> ·
<a href="https://github.com/greenwave-1/GTS">GTS</a> ·
<a href="https://github.com/mardy/VisualControllerTest">Visual Controller Test</a>
"""
    }
}
