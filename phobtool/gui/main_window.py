"""Fenêtre principale de PhobGCC Tool."""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QSplitter, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .. import APP_NAME, flasher, releases, snapback, updater, vct
from ..adapter import AdapterReader, PadState
from ..calibration import ADJUST, DONE, MEASURE, CalibrationTracker, step_notch
from ..paths import firmware_cache_dir, vct_build_dir
from .snapback_view import SnapbackPlot
from .stick_view import StickView, TriggerBar

SHORTCUTS = [
    ("A+X+Y+Start (maintenir)", "Activer / désactiver le safe mode"),
    ("A+X+Y+L", "Calibrer le stick analogique"),
    ("A+X+Y+R", "Calibrer le C-stick"),
    ("A+B+Z+Start", "Soft reset (à faire après une mise à jour)"),
    ("A+B+Z+D-bas", "Hard reset (efface aussi la calibration)"),
    ("A+Z+D-haut", "Afficher la version du firmware"),
    ("Start au branchement", "Mode BOOTSEL (Phob 2) pour flasher"),
    ("Z au branchement", "PhobVision (sortie vidéo de la Phob 2)"),
]


class Bus(QObject):
    """Signaux émis depuis les threads de travail (connexion en file d'attente)."""
    pads = Signal(object, str)
    releases_loaded = Signal(object, str)
    log = Signal(str)
    progress = Signal(int, int)
    stage = Signal(str)
    flash_done = Signal(bool, str)
    update_checked = Signal(object, str, bool)   # info|None, erreur, manuel
    update_progress = Signal(int, int)
    update_ready = Signal(object, str)           # dossier extrait|None, erreur


def _mono() -> QFont:
    f = QFont("Monospace")
    f.setStyleHint(QFont.TypeWriter)
    return f


class MainWindow(QMainWindow):
    def __init__(self, demo_pad: bool = False):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {updater.current_label()}")
        self.resize(1080, 760)
        self.settings = QSettings("PhobGCCTool", "PhobGCCTool")
        self.bus = Bus()
        self.releases: list[releases.Release] = []
        self.pads: Optional[list[PadState]] = None
        self.tracker = CalibrationTracker()
        self.snap = snapback.SnapbackDetector()
        self.snap_rate = snapback.RateMeter()
        self.snap_results: list[snapback.SnapbackResult] = []
        self._last_render = 0.0
        self._flush_scheduled = False
        self._pending_g = None
        self._cancel = threading.Event()
        self._flash_thread: Optional[threading.Thread] = None
        self.vct_proc: Optional[QProcess] = None
        self.build_proc: Optional[QProcess] = None
        self._demo = demo_pad

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_firmware_tab(), "1 · Firmware")
        self.tabs.addTab(self._build_calibration_tab(), "2 · Calibration / test")
        self.tabs.addTab(self._build_snapback_tab(), "3 · Snapback")
        self.tabs.addTab(self._build_vct_tab(), "4 · VCT / GTS")
        self.tabs.addTab(self._build_help_tab(), "Aide")
        self.setCentralWidget(self.tabs)

        self.adapter_label = QLabel("Adaptateur : —")
        self.statusBar().addPermanentWidget(self.adapter_label)

        self.bus.pads.connect(self._on_pads)
        self.bus.releases_loaded.connect(self._on_releases)
        self.bus.log.connect(self._log)
        self.bus.progress.connect(self._on_progress)
        self.bus.stage.connect(self._on_stage)
        self.bus.flash_done.connect(self._on_flash_done)
        self.bus.update_checked.connect(self._on_update_checked)
        self.bus.update_progress.connect(self._on_update_progress)
        self.bus.update_ready.connect(self._on_update_ready)
        self._update_cancel = threading.Event()
        self._update_busy = False

        self.reader = AdapterReader(lambda pads, status: self.bus.pads.emit(pads, status))
        if demo_pad:
            self._demo_t0 = time.monotonic()
            self._demo_timer = QTimer(self)
            self._demo_timer.timeout.connect(self._demo_tick)
            self._demo_timer.start(16)
        else:
            self.reader.start()

        QTimer.singleShot(200, self.refresh_releases)
        if self.settings.value("update/auto", True, type=bool) and not demo_pad:
            QTimer.singleShot(2500, lambda: self.check_updates(manual=False))
        self._refresh_vct_status()

    # ================================================================ firmware
    def _build_firmware_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        top = QGroupBox("Version à installer")
        form = QFormLayout(top)
        self.board_combo = QComboBox()
        for key in (releases.BOARD_RP2040, releases.BOARD_TEENSY40, releases.BOARD_TEENSY32):
            self.board_combo.addItem(releases.BOARD_LABELS[key], key)
        idx = self.board_combo.findData(self.settings.value("board", releases.BOARD_RP2040))
        self.board_combo.setCurrentIndex(max(0, idx))
        self.board_combo.currentIndexChanged.connect(self._update_asset_label)

        row = QHBoxLayout()
        self.release_combo = QComboBox()
        self.release_combo.setMinimumWidth(260)
        self.release_combo.currentIndexChanged.connect(self._on_release_selected)
        self.prerelease_cb = QCheckBox("Inclure les pré-versions")
        self.prerelease_cb.toggled.connect(lambda _: self._on_releases(self.releases, ""))
        refresh = QPushButton("Actualiser depuis GitHub")
        refresh.clicked.connect(self.refresh_releases)
        row.addWidget(self.release_combo, 1)
        row.addWidget(self.prerelease_cb)
        row.addWidget(refresh)

        self.asset_label = QLabel("—")
        self.asset_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        local_row = QHBoxLayout()
        self.local_file = QLineEdit()
        self.local_file.setPlaceholderText("Optionnel : utiliser un fichier .uf2 / .hex local à la place")
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._browse_firmware)
        local_row.addWidget(self.local_file, 1)
        local_row.addWidget(browse)

        form.addRow("Carte :", self.board_combo)
        form.addRow("Release :", row)
        form.addRow("Fichier :", self.asset_label)
        form.addRow("Local :", local_row)
        lay.addWidget(top)

        split = QSplitter(Qt.Horizontal)
        notes_box = QGroupBox("Notes de version")
        nl = QVBoxLayout(notes_box)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        nl.addWidget(self.notes)
        split.addWidget(notes_box)

        flash_box = QGroupBox("Mise à jour")
        fl = QVBoxLayout(flash_box)
        self.stage_label = QLabel("Prêt.")
        self.stage_label.setWordWrap(True)
        self.stage_label.setMinimumHeight(110)
        self.stage_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.stage_label.setStyleSheet("font-size: 14px; padding: 8px; border-radius: 6px;"
                                       "background: rgba(143,123,234,0.15);")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        btns = QHBoxLayout()
        self.download_btn = QPushButton("Télécharger seulement")
        self.download_btn.clicked.connect(lambda: self.start_flash(download_only=True))
        self.flash_btn = QPushButton("Mettre à jour la manette")
        self.flash_btn.setDefault(True)
        self.flash_btn.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.flash_btn.clicked.connect(lambda: self.start_flash(download_only=False))
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel.set)
        open_cache = QPushButton("Dossier des firmwares")
        open_cache.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(firmware_cache_dir()))))
        btns.addWidget(self.download_btn)
        btns.addWidget(self.flash_btn)
        btns.addWidget(self.cancel_btn)
        btns.addStretch(1)
        btns.addWidget(open_cache)
        self.flash_log = QPlainTextEdit()
        self.flash_log.setReadOnly(True)
        self.flash_log.setFont(_mono())
        self.flash_log.setMaximumBlockCount(2000)
        fl.addWidget(self.stage_label)
        fl.addWidget(self.progress)
        fl.addLayout(btns)
        fl.addWidget(self.flash_log, 1)
        split.addWidget(flash_box)
        split.setSizes([420, 620])
        lay.addWidget(split, 1)
        return w

    def refresh_releases(self):
        self.notes.setPlainText("Chargement des releases depuis GitHub…")

        def job():
            try:
                rel = releases.fetch_releases()
                self.bus.releases_loaded.emit(rel, "")
            except Exception as e:  # réseau, quota API…
                self.bus.releases_loaded.emit([], str(e))
        threading.Thread(target=job, daemon=True).start()

    def _on_releases(self, rel, err: str):
        if err:
            self.notes.setPlainText(f"Impossible de joindre GitHub : {err}\n\n"
                                    "Tu peux toujours flasher un fichier local.")
        self.releases = rel or []
        prev = self.release_combo.currentData()
        self.release_combo.blockSignals(True)
        self.release_combo.clear()
        latest_marked = False
        for r in self.releases:
            if r.prerelease and not self.prerelease_cb.isChecked():
                continue
            label = f"{r.tag}  ({r.published_at})"
            if r.prerelease:
                label += "  [pré-version]"
            elif not latest_marked:
                label += "  ★ dernière"
                latest_marked = True
            self.release_combo.addItem(label, r.tag)
        i = self.release_combo.findData(prev)
        self.release_combo.setCurrentIndex(i if i >= 0 else 0)
        self.release_combo.blockSignals(False)
        self._on_release_selected()

    def current_release(self) -> Optional[releases.Release]:
        tag = self.release_combo.currentData()
        return next((r for r in self.releases if r.tag == tag), None)

    def _on_release_selected(self, *_):
        r = self.current_release()
        if r:
            self.notes.setMarkdown(f"# {r.name}\n*Publiée le {r.published_at}* — [voir sur GitHub]({r.html_url})\n\n{r.body}")
        self._update_asset_label()

    def _update_asset_label(self, *_):
        board = self.board_combo.currentData()
        self.settings.setValue("board", board)
        r = self.current_release()
        if not r:
            self.asset_label.setText("—")
            return
        a = r.firmware_for(board)
        if a:
            chk = "SHA-256 vérifié au téléchargement" if a.sha256 else "pas d'empreinte publiée"
            self.asset_label.setText(f"{a.name}  ·  {a.size / 1024:.0f} Ko  ·  {chk}")
        else:
            names = ", ".join(x.name for x in r.firmware_assets) or "aucun"
            self.asset_label.setText(f"Pas de fichier pour cette carte dans {r.tag} (disponibles : {names})")

    def _browse_firmware(self):
        f, _ = QFileDialog.getOpenFileName(self, "Firmware PhobGCC", str(Path.home()),
                                           "Firmware (*.uf2 *.hex);;Tous (*)")
        if f:
            self.local_file.setText(f)

    def _log(self, line: str):
        self.flash_log.appendPlainText(line)
        self.flash_log.moveCursor(QTextCursor.End)

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_stage(self, text: str):
        self.stage_label.setText(text)

    def _set_busy(self, busy: bool):
        self.flash_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.board_combo.setEnabled(not busy)
        self.release_combo.setEnabled(not busy)

    def start_flash(self, download_only: bool):
        board = self.board_combo.currentData()
        local = self.local_file.text().strip()
        release = self.current_release()
        asset = release.firmware_for(board) if release else None
        if not local and not asset:
            QMessageBox.warning(self, APP_NAME, "Aucun firmware disponible pour cette carte. "
                                "Choisis une autre release ou un fichier local.")
            return
        if local and board == releases.BOARD_RP2040 and not local.lower().endswith(".uf2"):
            QMessageBox.warning(self, APP_NAME, "La PhobGCC 2 attend un fichier .uf2.")
            return
        self._cancel.clear()
        self._set_busy(True)
        self.flash_log.clear()
        self._flash_thread = threading.Thread(
            target=self._flash_job, args=(board, local, release, asset, download_only), daemon=True)
        self._flash_thread.start()

    def _flash_job(self, board, local, release, asset, download_only):
        b = self.bus
        try:
            if local:
                fw = Path(local)
                b.log.emit(f"Fichier local : {fw}")
            else:
                b.stage.emit(f"<b>1/4 · Téléchargement</b><br>{asset.name} ({release.tag})")
                b.log.emit(f"GET {asset.url}")
                fw = releases.download_asset(asset, release.tag, progress=b.progress.emit,
                                             cancelled=self._cancel.is_set)
                b.log.emit(f"Enregistré : {fw}")
                if asset.sha256:
                    b.log.emit(f"SHA-256 OK : {asset.sha256}")
            if board == releases.BOARD_RP2040:
                info = flasher.validate_uf2(fw)
                b.log.emit(f"UF2 valide : {info.blocks} blocs, {info.payload_bytes / 1024:.0f} Ko pour RP2040")
            if download_only:
                b.flash_done.emit(True, f"Firmware prêt : {fw}")
                return

            if board != releases.BOARD_RP2040:
                b.stage.emit("<b>Flash Teensy</b><br>Branche la manette en USB, puis appuie sur le "
                             "bouton du Teensy si le chargeur te le demande.")
                flasher.flash_teensy(fw, board, b.log.emit)
                b.flash_done.emit(True, "Teensy programmé. Fais un soft reset : A+B+Z+Start.")
                return

            drive = next(iter(flasher.find_rp2_drives()), None)
            if not drive:
                b.stage.emit(
                    "<b>2/4 · Passe la manette en mode BOOTSEL</b><ol>"
                    "<li>Débranche la manette (console et USB).</li>"
                    "<li><b>Maintiens Start</b> (ou le bouton BOOTSEL du PCB).</li>"
                    "<li>Branche le câble USB-C de la PhobGCC sur le PC, puis relâche.</li></ol>"
                    "Un lecteur <b>RPI-RP2</b> doit apparaître — je le détecte tout seul…")
                b.progress.emit(0, 0)
                drive = flasher.wait_for_rp2_drive(timeout=600, cancelled=self._cancel.is_set)
                if not drive:
                    raise InterruptedError("annulé" if self._cancel.is_set() else "lecteur RPI-RP2 non détecté")
            b.log.emit(f"Lecteur BOOTSEL trouvé : {drive}")
            b.stage.emit(f"<b>3/4 · Écriture du firmware</b><br>sur {drive} — ne débranche pas la manette.")
            flasher.flash_uf2(fw, drive, progress=b.progress.emit)
            b.log.emit("Copie terminée, attente du redémarrage…")
            b.stage.emit("<b>4/4 · Redémarrage de la manette…</b>")
            gone = flasher.wait_for_drive_gone(drive)
            b.log.emit("La manette a redémarré." if gone else
                       "Le lecteur est toujours visible : débranche/rebranche la manette.")
            b.flash_done.emit(True,
                              "<b>Mise à jour terminée ✔</b><br>Sur la console (ou via l'adaptateur), fais un "
                              "<b>soft reset : A+B+Z+Start</b>. Si les sticks se comportent bizarrement, "
                              "refais la calibration (onglet 2). Lis aussi les notes de version.")
        except InterruptedError as e:
            b.flash_done.emit(False, f"Interrompu : {e}")
        except Exception as e:
            b.flash_done.emit(False, f"Erreur : {e}")

    def _on_flash_done(self, ok: bool, msg: str):
        self._set_busy(False)
        if self.progress.maximum() == 0:
            self.progress.setMaximum(1)
        self.stage_label.setText(msg if ok else f"<span style='color:#ff6b6b'>{msg}</span>")
        self._log(("✔ " if ok else "✘ ") + msg.replace("<br>", " ").replace("<b>", "").replace("</b>", ""))

    # ============================================================= calibration
    def _build_calibration_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)

        left = QVBoxLayout()
        ctl = QGroupBox("Calibration guidée")
        cl = QGridLayout(ctl)
        self.port_combo = QComboBox()
        self.port_combo.addItem("Auto (1er port branché)", -1)
        for i in range(4):
            self.port_combo.addItem(f"Port {i + 1}", i)
        self.stick_a = QRadioButton("Stick analogique")
        self.stick_c = QRadioButton("C-stick")
        self.stick_a.setChecked(True)
        grp = QButtonGroup(w)
        grp.addButton(self.stick_a)
        grp.addButton(self.stick_c)
        self.cal_start = QPushButton("Démarrer")
        self.cal_start.setStyleSheet("font-weight: bold;")
        self.cal_start.clicked.connect(self._cal_start)
        self.cal_stop = QPushButton("Arrêter le suivi")
        self.cal_stop.clicked.connect(self._cal_stop)
        cl.addWidget(QLabel("Port :"), 0, 0)
        cl.addWidget(self.port_combo, 0, 1, 1, 2)
        cl.addWidget(self.stick_a, 1, 1)
        cl.addWidget(self.stick_c, 1, 2)
        cl.addWidget(self.cal_start, 2, 1)
        cl.addWidget(self.cal_stop, 2, 2)
        left.addWidget(ctl)

        self.guide_title = QLabel("Prêt")
        f = self.guide_title.font()
        f.setPointSize(f.pointSize() + 5)
        f.setBold(True)
        self.guide_title.setFont(f)
        self.guide_title.setWordWrap(True)
        self.guide_detail = QLabel("Choisis le stick à calibrer puis clique sur « Démarrer ».")
        self.guide_detail.setWordWrap(True)
        self.guide_detail.setAlignment(Qt.AlignTop)
        self.guide_detail.setMinimumHeight(90)
        self.cal_progress = QProgressBar()
        self.cal_progress.setRange(0, 44)
        gbox = QGroupBox("Étape en cours")
        gl = QVBoxLayout(gbox)
        gl.addWidget(self.guide_title)
        gl.addWidget(self.guide_detail)
        gl.addWidget(self.cal_progress)
        left.addWidget(gbox)

        sc = QGroupBox("Raccourcis PhobGCC")
        sl = QFormLayout(sc)
        for combo, desc in SHORTCUTS:
            k = QLabel(f"<b>{combo}</b>")
            d = QLabel(desc)
            d.setWordWrap(True)
            sl.addRow(k, d)
        left.addWidget(sc)
        left.addStretch(1)

        right = QVBoxLayout()
        sticks = QHBoxLayout()
        self.view_a = StickView("Stick analogique", "#b9a6ff")
        self.view_c = StickView("C-stick", "#ffd34d")
        sticks.addWidget(self.view_a, 1)
        sticks.addWidget(self.view_c, 1)
        self.trig_l = TriggerBar("L")
        self.trig_r = TriggerBar("R")
        sticks.insertWidget(0, self.trig_l)
        sticks.addWidget(self.trig_r)
        right.addLayout(sticks, 1)

        btn_row = QHBoxLayout()
        self.btn_labels = {}
        for name in ["A", "B", "X", "Y", "Z", "L", "R", "S", "Du", "Dd", "Dl", "Dr"]:
            text = {"S": "Start", "Du": "↑", "Dd": "↓", "Dl": "←", "Dr": "→"}.get(name, name)
            lab = QLabel(text)
            lab.setAlignment(Qt.AlignCenter)
            lab.setMinimumWidth(36)
            lab.setFrameShape(QFrame.StyledPanel)
            self.btn_labels[name] = lab
            btn_row.addWidget(lab)
        right.addLayout(btn_row)
        self.pad_info = QLabel("—")
        self.pad_info.setAlignment(Qt.AlignCenter)
        right.addWidget(self.pad_info)
        clear = QPushButton("Effacer les traînées")
        clear.clicked.connect(lambda: (self.view_a.clear_trail(), self.view_c.clear_trail()))
        right.addWidget(clear, 0, Qt.AlignRight)

        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(400)
        lay.addWidget(lw)
        rw = QWidget()
        rw.setLayout(right)
        lay.addWidget(rw, 1)
        return w

    def _cal_start(self):
        self.tracker.arm("A" if self.stick_a.isChecked() else "C")
        self.view_a.clear_trail()
        self.view_c.clear_trail()
        if not self.reader.running and not self._demo:
            self.reader.start()
        self._render_guidance(self.tracker.guidance())

    def _cal_stop(self):
        self.tracker.reset()
        self._render_guidance(self.tracker.guidance())

    def _selected_pad(self, combo=None) -> Optional[tuple[int, PadState]]:
        if not self.pads:
            return None
        want = (combo or self.port_combo).currentData()
        if want is not None and want >= 0:
            return (want, self.pads[want]) if self.pads[want].connected else None
        for i, p in enumerate(self.pads):
            if p.connected:
                return i, p
        return None

    def _on_pads(self, pads, status: str):
        if pads is None:
            self.pads = None
            self.adapter_label.setText(f"Adaptateur : {status}")
            self.pad_info.setText(status)
            return
        self.pads = pads
        self._feed_snapback(pads)
        # suivi de calibration à chaque rapport, affichage limité à ~60 i/s
        sel = self._selected_pad()
        g = self.tracker.feed(sel[1]) if sel else None
        self._pending_g = g
        now = time.perf_counter()
        if now - self._last_render < 0.015:
            if not self._flush_scheduled:
                self._flush_scheduled = True
                QTimer.singleShot(16, self._flush_render)
            return
        self._render_now()

    def _flush_render(self):
        self._flush_scheduled = False
        if self.pads:
            self._render_now()

    def _render_now(self):
        pads, g = self.pads, self._pending_g
        self._last_render = time.perf_counter()
        n = sum(p.connected for p in pads)
        rate = self.snap_rate.hz
        rate_txt = f" · {rate:.0f} Hz" if rate else ""
        self.adapter_label.setText(f"Adaptateur : connecté · {n} manette(s){rate_txt}")
        sel = self._selected_pad()
        if not sel or g is None:
            self.pad_info.setText("Aucune manette sur le port choisi")
            self.view_a.set_state(None)
            self.view_c.set_state(None)
            return
        port, pad = sel
        self._render_pad(port, pad, g)

    def _render_pad(self, port: int, pad: PadState, g):
        a, c = pad.a_xy, pad.c_xy
        target = g.target_xy if g.state in (MEASURE, ADJUST) else None
        notch = step_notch(g.step) if g.state in (MEASURE, ADJUST) else None
        if self.tracker.stick == "A" and target is not None:
            self.view_a.set_state(a, target, notch, "← stick en calibration")
            self.view_c.set_state(c, None, None, "cible affichée par le firmware")
        elif target is not None:
            self.view_c.set_state(c, target, notch, "← stick en calibration")
            self.view_a.set_state(a, None, None, "cible affichée par le firmware")
        else:
            ma, mc = pad.melee("A"), pad.melee("C")
            self.view_a.set_state(a, None, None, f"Melee {ma[0]:+.4f}, {ma[1]:+.4f}")
            self.view_c.set_state(c, None, None, f"Melee {mc[0]:+.4f}, {mc[1]:+.4f}")
        self.trig_l.set_value(pad.l, "L" in pad.buttons)
        self.trig_r.set_value(pad.r, "R" in pad.buttons)
        for name, lab in self.btn_labels.items():
            on = name in pad.buttons
            lab.setStyleSheet("background:#8f7bea; color:white; font-weight:bold; border-radius:4px;"
                              if on else "")
        kind = "WaveBird" if pad.wireless else "filaire"
        self.pad_info.setText(f"Port {port + 1} · manette {kind}")
        self._render_guidance(g)

    def _render_guidance(self, g):
        self.guide_title.setText(g.title)
        self.guide_detail.setText(g.detail)
        self.cal_progress.setValue(int(round(g.progress * 44)))
        color = "#5fd38d" if g.state == DONE else ""
        self.guide_title.setStyleSheet(f"color:{color}" if color else "")

    def _demo_tick(self):
        """Manette virtuelle pour essayer l'interface sans matériel (--demo)."""
        if self.tabs.currentIndex() == 2:
            self._demo_snapback()
            return
        t = time.monotonic() - self._demo_t0
        ax = int(128 + 100 * math.cos(t * 1.5))
        ay = int(128 + 100 * math.sin(t * 1.5))
        cx = int(128 + 70 * math.cos(t * 0.7 + 1))
        cy = int(128 + 70 * math.sin(t * 0.9))
        btn = {"A"} if int(t * 2) % 3 == 0 else set()
        pad = PadState(True, False, frozenset(btn), ax, ay, cx, cy,
                       int(127 + 127 * math.sin(t)), int(127 - 127 * math.sin(t)))
        self.bus.pads.emit([pad, PadState(), PadState(), PadState()], "démo")

    def _demo_snapback(self):
        """Lâchers de stick simulés à 1000 Hz (bons et mauvais, 4 directions)."""
        now = time.perf_counter()
        if not getattr(self, "_demo_seq", None):
            seq, t = [], now
            for start, axis, ov in ((100, "x", 0.45), (-98, "x", 0.12), (96, "y", 0.2), (-95, "y", 0.4)):
                part = snapback.simulate_release(start=start, axis=axis, overshoot=ov, hold_ms=300,
                                                 after_ms=500, t0=t)
                seq += part
                t = part[-1].t + 0.001
            self._demo_seq = seq
            self._demo_i = 0
        while self._demo_i < len(self._demo_seq) and self._demo_seq[self._demo_i].t <= now:
            s = self._demo_seq[self._demo_i]
            self._demo_i += 1
            pad = PadState(True, False, frozenset(), s.x + 128, s.y + 128, 128, 128, 0, 0, s.t)
            self.bus.pads.emit([pad, PadState(), PadState(), PadState()], "démo")
        if self._demo_i >= len(self._demo_seq):
            self._demo_seq = None

    # ================================================================ snapback
    SNAP_DIRS = ("droite", "gauche", "haut", "bas")

    def _build_snapback_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)

        left = QVBoxLayout()
        ctl = QGroupBox("Test de snapback")
        cl = QGridLayout(ctl)
        self.snap_port = QComboBox()
        self.snap_port.addItem("Auto (1er port branché)", -1)
        for i in range(4):
            self.snap_port.addItem(f"Port {i + 1}", i)
        self.snap_stick_a = QRadioButton("Stick analogique")
        self.snap_stick_c = QRadioButton("C-stick")
        self.snap_stick_a.setChecked(True)
        grp = QButtonGroup(w)
        grp.addButton(self.snap_stick_a)
        grp.addButton(self.snap_stick_c)
        self.snap_stick_a.toggled.connect(self._snap_reset)
        reset = QPushButton("Remettre à zéro")
        reset.clicked.connect(self._snap_reset)
        cl.addWidget(QLabel("Port :"), 0, 0)
        cl.addWidget(self.snap_port, 0, 1, 1, 2)
        cl.addWidget(self.snap_stick_a, 1, 1)
        cl.addWidget(self.snap_stick_c, 1, 2)
        cl.addWidget(reset, 2, 2)
        left.addWidget(ctl)

        self.snap_state = QLabel()
        f = self.snap_state.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        self.snap_state.setFont(f)
        self.snap_state.setWordWrap(True)
        left.addWidget(self.snap_state)

        how = QLabel("Pousse le stick <b>à fond</b> dans une direction, maintiens-le, puis <b>lâche-le d'un coup</b> "
                     "(fais-le glisser hors du pouce). Teste droite, gauche, haut et bas plusieurs fois. "
                     "Un rebond qui sort de <b>±22</b> du côté opposé peut être lu par Melee comme un input "
                     "(dashback, tilt involontaire…).")
        how.setWordWrap(True)
        left.addWidget(how)

        summ = QGroupBox("Bilan par direction (pire rebond)")
        sg = QGridLayout(summ)
        self.snap_dir_labels = {}
        for i, d in enumerate(self.SNAP_DIRS):
            name = QLabel(f"<b>{d.capitalize()}</b>")
            val = QLabel("—")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sg.addWidget(name, i, 0)
            sg.addWidget(val, i, 1)
            self.snap_dir_labels[d] = val
        left.addWidget(summ)

        self.snap_rate_label = QLabel("Fréquence de l'adaptateur : —")
        self.snap_rate_label.setWordWrap(True)
        left.addWidget(self.snap_rate_label)

        tips = QGroupBox("Si ça rebondit trop (filtre snapback PhobGCC)")
        tl = QVBoxLayout(tips)
        tip = QLabel("Stick : <b>A+X+D-haut / D-bas</b> (axe X), <b>A+Y+D-haut / D-bas</b> (axe Y).<br>"
                     "C-stick : même combo <b>+ Z</b>.<br>"
                     "D-haut renforce le filtre, D-bas l'allège (0 = désactivé, 4 = défaut). "
                     "Pendant le réglage, la valeur s'affiche sur l'autre stick. Refais le test après chaque cran : "
                     "trop de filtrage ajoute de la latence.")
        tip.setWordWrap(True)
        tl.addWidget(tip)
        left.addWidget(tips)
        left.addStretch(1)

        right = QVBoxLayout()
        self.snap_plot = SnapbackPlot()
        right.addWidget(self.snap_plot, 1)
        self.snap_verdict = QLabel("")
        self.snap_verdict.setWordWrap(True)
        self.snap_verdict.setTextFormat(Qt.RichText)
        self.snap_verdict.setMinimumHeight(52)
        right.addWidget(self.snap_verdict)
        self.snap_list = QListWidget()
        self.snap_list.setMaximumHeight(150)
        self.snap_list.currentRowChanged.connect(self._snap_show_row)
        right.addWidget(QLabel("Historique (clique pour réafficher) :"))
        right.addWidget(self.snap_list)

        lw = QWidget()
        lw.setLayout(left)
        lw.setMaximumWidth(380)
        lay.addWidget(lw)
        rw = QWidget()
        rw.setLayout(right)
        lay.addWidget(rw, 1)
        self._snap_update_state()
        return w

    def _snap_reset(self, *_):
        self.snap.reset()
        self.snap_results.clear()
        self.snap_list.clear()
        self.snap_plot.set_result(None)
        self.snap_verdict.setText("")
        for lab in self.snap_dir_labels.values():
            lab.setText("—")
            lab.setStyleSheet("")
        self._snap_update_state()

    def _snap_update_state(self):
        st = self.snap.state
        txt = {"waiting": "En attente : pousse le stick à fond…",
               "armed": "Prêt : lâche le stick d'un coup !",
               "recording": "Mesure en cours…"}[st]
        self.snap_state.setText(txt)
        self.snap_state.setStyleSheet("color:#ffd34d" if st == "armed" else "")

    def _feed_snapback(self, pads):
        sel = self._selected_pad(self.snap_port)
        if not sel:
            return
        pad = sel[1]
        t = pad.t or time.perf_counter()
        self.snap_rate.tick(t)
        x, y = pad.a_xy if self.snap_stick_a.isChecked() else pad.c_xy
        before = self.snap.state
        res = self.snap.feed(t, x, y)
        if res:
            self._snap_add(res)
        if self.snap.state != before:
            self._snap_update_state()

    def _snap_add(self, r):
        self.snap_results.append(r)
        mark = "✔" if r.passed else "✘"
        item = QListWidgetItem(f"{mark}  {len(self.snap_results):3d} · {r.direction:<7} rebond {r.overshoot:+4d}"
                               f" · stabilisé en {r.settle_ms:4.0f} ms")
        self.snap_list.addItem(item)
        self.snap_list.blockSignals(True)
        self.snap_list.setCurrentRow(self.snap_list.count() - 1)
        self.snap_list.blockSignals(False)
        self._snap_show(r)
        # bilan par direction
        for d in self.SNAP_DIRS:
            rs = [x for x in self.snap_results if x.direction == d]
            if not rs:
                continue
            worst = max(rs, key=lambda x: abs(x.overshoot))
            fails = sum(not x.passed for x in rs)
            lab = self.snap_dir_labels[d]
            lab.setText(f"{worst.overshoot:+d}  ({len(rs)} essai{'s' if len(rs) > 1 else ''}, {fails} hors zone)")
            lab.setStyleSheet("color:#5fd38d; font-weight:bold" if fails == 0 else "color:#ff6b6b; font-weight:bold")
        hz = self.snap_rate.hz
        if hz:
            warn = ""
            if hz < 500:
                warn = (f"<br><span style='color:#ffb347'>Une mesure toutes les {1000 / hz:.0f} ms : un rebond plus court "
                        "peut passer entre deux mesures (GTS sur console mesure à chaque poll). "
                        "Un adaptateur overclocké à 1000 Hz donne une courbe plus fidèle.</span>")
            self.snap_rate_label.setText(f"Fréquence de l'adaptateur : <b>{hz:.0f} Hz</b>{warn}")

    def _snap_show_row(self, row: int):
        if 0 <= row < len(self.snap_results):
            self._snap_show(self.snap_results[row])

    def _snap_show(self, r):
        self.snap_plot.set_result(r)
        col = "#5fd38d" if r.passed else "#ff6b6b"
        verdict = ("OK : le rebond reste dans la zone morte de Melee" if r.passed else
                   "Snapback : le rebond sort de la zone morte (±22)")
        hl_x = "<b>" if r.axis == "x" else ""
        hl_y = "<b>" if r.axis == "y" else ""
        self.snap_verdict.setText(
            f"<span style='color:{col}; font-size:15px; font-weight:bold'>{verdict}</span><br>"
            f"Lâcher vers la <b>{r.direction}</b> depuis {r.start_value:+d} · rebond max côté opposé "
            f"<b>{r.overshoot:+d}</b> · {r.crossings} sortie(s) de zone · stabilisé en {r.settle_ms:.0f} ms<br>"
            f"{hl_x}X min/max ({r.min_x:+d}, {r.max_x:+d}){'</b>' if hl_x else ''}  |  "
            f"{hl_y}Y min/max ({r.min_y:+d}, {r.max_y:+d}){'</b>' if hl_y else ''}  ·  "
            f"{len(r.samples)} mesures, une toutes les {r.sample_period_ms:.1f} ms")

    # ===================================================================== VCT
    def _build_vct_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        intro = QLabel(
            "Portages PC natifs de <b>Visual Controller Test</b> (Mr. Reaper / Zarithya) et de <b>GTS</b> "
            "(GCC Test Suite, greenwave-1 – l'alternative libre à SmashScope). Les sources d'origine sont "
            "recompilées sans modification avec une couche SDL2 + libusb qui lit l'<b>adaptateur GameCube "
            "officiel</b> (WUP-028) ; GTS reçoit chaque rapport de l'adaptateur pour ses oscilloscopes.<br>"
            "Quitter : Start+B+X (VCT), maintenir Start dans le menu (GTS), Échap ou fermer la fenêtre. "
            "F11 : plein écran. GTS est distribué sous licence GPL-3.0.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        st = QGroupBox("État")
        sl = QFormLayout(st)
        self.vct_status = QLabel("—")
        self.vct_status.setWordWrap(True)
        self.vct_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.tool_status = QLabel("—")
        self.tool_status.setWordWrap(True)
        self.gts_status = QLabel("—")
        self.gts_status.setWordWrap(True)
        self.gts_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sl.addRow("VCT :", self.vct_status)
        sl.addRow("GTS :", self.gts_status)
        sl.addRow("Outils :", self.tool_status)
        lay.addWidget(st)

        opts = QGroupBox("Lancement")
        ol = QHBoxLayout(opts)
        self.vct_full = QCheckBox("Plein écran")
        self.vct_full.setChecked(self.settings.value("vct_full", False, type=bool))
        self.vct_scale = QDoubleSpinBox()
        self.vct_scale.setRange(1.0, 4.0)
        self.vct_scale.setSingleStep(0.25)
        self.vct_scale.setValue(float(self.settings.value("vct_scale", 1.5)))
        self.vct_scale.setPrefix("échelle ×")
        self.vct_sdl = QCheckBox("Autres manettes si l'adaptateur est absent")
        self.vct_sdl.setChecked(self.settings.value("vct_sdl", True, type=bool))
        self.vct_launch = QPushButton("▶ Visual Controller Test")
        self.vct_launch.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.vct_launch.clicked.connect(lambda: self.launch_tool("vct"))
        self.gts_screen = QComboBox()
        for label, key in vct.GTS_SCREENS:
            self.gts_screen.addItem(label, key)
        self.gts_launch = QPushButton("▶ GTS")
        self.gts_launch.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.gts_launch.clicked.connect(lambda: self.launch_tool("gts"))
        self.vct_kill = QPushButton("Fermer")
        self.vct_kill.setEnabled(False)
        self.vct_kill.clicked.connect(lambda: self.vct_proc and self.vct_proc.terminate())
        ol.addWidget(self.vct_full)
        ol.addWidget(self.vct_scale)
        ol.addWidget(self.vct_sdl)
        ol.addStretch(1)
        ol.addWidget(self.vct_launch)
        ol.addWidget(self.gts_screen)
        ol.addWidget(self.gts_launch)
        ol.addWidget(self.vct_kill)
        lay.addWidget(opts)

        bld = QGroupBox("Compilation")
        bl = QGridLayout(bld)
        self.vct_repo = QLineEdit(self.settings.value("vct_repo", vct.DEFAULT_UPSTREAM_REPO))
        self.vct_ref = QLineEdit(self.settings.value("vct_ref", vct.DEFAULT_UPSTREAM_REF))
        self.vct_ref.setToolTip("Commit, tag ou branche des sources Wii (ex. « main » pour la dernière version)")
        self.vct_local = QLineEdit(self.settings.value("vct_local", ""))
        self.vct_local.setPlaceholderText("Optionnel : dossier local des sources VisualControllerTest")
        self.vct_exe_override = QLineEdit(self.settings.value("vct_exe", ""))
        self.vct_exe_override.setPlaceholderText("Optionnel : chemin d'un exécutable déjà compilé")
        self.vct_exe_override.editingFinished.connect(self._refresh_vct_status)
        self.vct_build = QPushButton("Compiler / recompiler")
        self.vct_build.clicked.connect(self.build_vct)
        open_build = QPushButton("Dossier de build")
        open_build.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(vct_build_dir()))))
        bl.addWidget(QLabel("Dépôt upstream :"), 0, 0)
        bl.addWidget(self.vct_repo, 0, 1, 1, 3)
        bl.addWidget(QLabel("Révision :"), 1, 0)
        bl.addWidget(self.vct_ref, 1, 1, 1, 3)
        bl.addWidget(QLabel("Sources locales :"), 2, 0)
        bl.addWidget(self.vct_local, 2, 1, 1, 3)
        bl.addWidget(QLabel("Exécutable :"), 3, 0)
        bl.addWidget(self.vct_exe_override, 3, 1, 1, 3)
        bl.addWidget(self.vct_build, 4, 2)
        bl.addWidget(open_build, 4, 3)
        lay.addWidget(bld)

        self.vct_log = QPlainTextEdit()
        self.vct_log.setReadOnly(True)
        self.vct_log.setFont(_mono())
        self.vct_log.setMaximumBlockCount(5000)
        lay.addWidget(self.vct_log, 1)
        return w

    def _refresh_vct_status(self):
        missing = ("<span style='color:#ffb347'>Pas encore compilé</span> — "
                   "clique sur « Compiler / recompiler ».")
        exe = vct.find_vct_exe(self.vct_exe_override.text().strip() or None)
        self.vct_status.setText(f"<span style='color:#5fd38d'>✔</span> {exe}" if exe else missing)
        gexe = vct.find_gts_exe()
        self.gts_status.setText(f"<span style='color:#5fd38d'>✔</span> {gexe}" if gexe else missing)
        ok, msg = vct.toolchain_status()
        self.tool_status.setText(msg)
        idle = self.vct_proc is None
        self.vct_launch.setEnabled(exe is not None and idle)
        self.gts_launch.setEnabled(gexe is not None and idle)
        self.gts_screen.setEnabled(idle)

    def _vct_log(self, text: str):
        self.vct_log.appendPlainText(text.rstrip("\n"))
        self.vct_log.moveCursor(QTextCursor.End)

    def build_vct(self):
        ok, msg = vct.toolchain_status()
        if not ok:
            QMessageBox.warning(self, APP_NAME, msg)
            return
        for key, edit in (("vct_repo", self.vct_repo), ("vct_ref", self.vct_ref), ("vct_local", self.vct_local)):
            self.settings.setValue(key, edit.text().strip())
        steps = [
            vct.configure_command(self.vct_repo.text().strip() or vct.DEFAULT_UPSTREAM_REPO,
                                  self.vct_ref.text().strip() or vct.DEFAULT_UPSTREAM_REF,
                                  self.vct_local.text().strip() or None),
            vct.build_command(),
            vct.gts_configure_command(),
            vct.gts_build_command(),
        ]
        self.vct_build.setEnabled(False)
        self.vct_log.clear()
        self._run_steps(steps)

    def _run_steps(self, steps: list[list[str]]):
        if not steps:
            self._vct_log("\n✔ Compilation terminée.")
            self.vct_build.setEnabled(True)
            self._refresh_vct_status()
            return
        cmd = steps[0]
        self._vct_log("$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self._vct_log(bytes(proc.readAllStandardOutput()).decode(errors="replace")))

        def finished(code, _status):
            self.build_proc = None
            if code != 0:
                self._vct_log(f"\n✘ Échec (code {code}). Vérifie que SDL2, libusb et un compilateur C sont installés.")
                self.vct_build.setEnabled(True)
                return
            self._run_steps(steps[1:])
        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda e: self._vct_log(f"✘ Impossible de lancer {cmd[0]} ({e})"))
        self.build_proc = proc
        proc.start(cmd[0], cmd[1:])

    def launch_vct(self):
        self.launch_tool("vct")

    def launch_tool(self, tool: str):
        if tool == "gts":
            exe, name = vct.find_gts_exe(), "GTS"
        else:
            exe, name = vct.find_vct_exe(self.vct_exe_override.text().strip() or None), "Visual Controller Test"
        if not exe:
            self._refresh_vct_status()
            return
        self.settings.setValue("vct_full", self.vct_full.isChecked())
        self.settings.setValue("vct_scale", self.vct_scale.value())
        self.settings.setValue("vct_sdl", self.vct_sdl.isChecked())
        self.settings.setValue("vct_exe", self.vct_exe_override.text().strip())
        # un seul programme peut réclamer l'adaptateur : on le libère
        self.reader.stop()
        self.adapter_label.setText(f"Adaptateur : prêté à {name}")
        args = vct.launch_args(self.vct_full.isChecked(), self.vct_scale.value(), self.vct_sdl.isChecked())
        if tool == "gts" and self.gts_screen.currentData():
            args += ["--menu", self.gts_screen.currentData()]
        self._tool_name = name
        self._vct_log(f"$ {exe} {' '.join(args)}")
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.setWorkingDirectory(str(exe.parent))
        proc.readyReadStandardOutput.connect(
            lambda: self._vct_log(bytes(proc.readAllStandardOutput()).decode(errors="replace")))
        proc.finished.connect(self._vct_finished)
        proc.errorOccurred.connect(lambda e: self._vct_log(f"✘ Lancement impossible ({e})"))
        self.vct_proc = proc
        self.vct_launch.setEnabled(False)
        self.gts_launch.setEnabled(False)
        self.vct_kill.setEnabled(True)
        proc.start(str(exe), args)

    def _vct_finished(self, code, _status):
        self._vct_log(f"{getattr(self, '_tool_name', 'Programme')} fermé (code {code}).")
        self.vct_proc = None
        self.vct_kill.setEnabled(False)
        self._refresh_vct_status()
        if not self._demo:
            self.reader.start()

    # ==================================================================== help
    def _build_help_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        box = QGroupBox("Mises à jour de PhobGCC Tool")
        bl = QVBoxLayout(box)
        row = QHBoxLayout()
        self.upd_label = QLabel(f"Version installée : <b>{updater.current_label()}</b>")
        self.upd_label.setTextFormat(Qt.RichText)
        row.addWidget(self.upd_label, 1)
        self.upd_auto = QCheckBox("Vérifier au démarrage")
        self.upd_auto.setChecked(self.settings.value("update/auto", True, type=bool))
        self.upd_auto.toggled.connect(lambda on: self.settings.setValue("update/auto", on))
        row.addWidget(self.upd_auto)
        self.upd_btn = QPushButton("Rechercher une mise à jour")
        self.upd_btn.clicked.connect(lambda: self.check_updates(manual=True))
        row.addWidget(self.upd_btn)
        bl.addLayout(row)
        self.upd_status = QLabel("")
        self.upd_status.setWordWrap(True)
        self.upd_status.setOpenExternalLinks(True)
        bl.addWidget(self.upd_status)
        self.upd_bar = QProgressBar()
        self.upd_bar.setVisible(False)
        bl.addWidget(self.upd_bar)
        lay.addWidget(box)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml(HELP_HTML)
        lay.addWidget(tb, 1)
        return w

    # ================================================================ updates
    def check_updates(self, manual: bool = True):
        if self._update_busy:
            return
        self._update_busy = True
        self.upd_btn.setEnabled(False)
        self.upd_status.setText("Recherche d'une mise à jour…")

        def job():
            try:
                self.bus.update_checked.emit(updater.check(), "", manual)
            except Exception as e:  # réseau absent, GitHub injoignable…
                self.bus.update_checked.emit(None, str(e), manual)
        threading.Thread(target=job, daemon=True).start()

    def _on_update_checked(self, info, err: str, manual: bool):
        self._update_busy = False
        self.upd_btn.setEnabled(True)
        link = f"<a href='{updater.RELEASE_PAGE}'>page des téléchargements</a>"
        if err:
            self.upd_status.setText(f"Impossible de vérifier les mises à jour : {err}")
            return
        if info is None:
            self.upd_status.setText("✔ PhobGCC Tool est à jour.")
            if manual:
                QMessageBox.information(self, "Mise à jour", "Tu as déjà la dernière version.")
            return
        ok, why = updater.can_self_update()
        self.upd_status.setText(f"Nouvelle version disponible : <b>{info.label}</b> — {link}")
        if not ok or not info.asset_url:
            if manual or updater.is_packaged():
                QMessageBox.information(self, "Mise à jour disponible",
                    f"Une nouvelle version est disponible ({info.label}).\n\n"
                    f"Installation automatique impossible : {why or 'pas de fichier pour ce système'}.")
            return
        r = QMessageBox.question(self, "Mise à jour disponible",
            f"Une nouvelle version de PhobGCC Tool est disponible ({info.label}).\n"
            f"Version installée : {updater.current_label()}.\n\n"
            "La télécharger et l'installer maintenant ? L'appli redémarrera toute seule.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self._start_update(info)

    def _start_update(self, info):
        if self._flash_thread and self._flash_thread.is_alive():
            QMessageBox.warning(self, "Mise à jour", "Attends la fin de la mise à jour du firmware.")
            return
        self._update_busy = True
        self._update_cancel.clear()
        self.upd_btn.setEnabled(False)
        self.upd_bar.setVisible(True)
        self.upd_bar.setValue(0)
        self.upd_status.setText(f"Téléchargement de {info.asset_name}…")
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

        def job():
            try:
                arc = updater.download(info, lambda d, t: self.bus.update_progress.emit(d, t),
                                       self._update_cancel.is_set)
                self.bus.update_progress.emit(-1, 0)
                self.bus.update_ready.emit(updater.extract(arc), "")
            except Exception as e:
                self.bus.update_ready.emit(None, str(e))
        threading.Thread(target=job, daemon=True).start()

    def _on_update_progress(self, done: int, total: int):
        if done < 0:
            self.upd_bar.setRange(0, 0)
            self.upd_status.setText("Préparation des fichiers…")
            return
        if total > 0:
            self.upd_bar.setRange(0, 1000)
            self.upd_bar.setValue(int(done * 1000 / total))
        self.upd_status.setText(f"Téléchargement… {done / 1e6:.1f} / {total / 1e6:.1f} Mo")

    def _on_update_ready(self, root, err: str):
        self._update_busy = False
        self.upd_btn.setEnabled(True)
        self.upd_bar.setVisible(False)
        self.upd_bar.setRange(0, 1000)
        if root is None:
            self.upd_status.setText(f"Échec de la mise à jour : {err}")
            QMessageBox.warning(self, "Mise à jour", f"La mise à jour a échoué :\n{err}")
            return
        try:
            updater.launch_installer(root)
        except Exception as e:
            self.upd_status.setText(f"Échec de la mise à jour : {e}")
            return
        self.upd_status.setText("Installation… PhobGCC Tool va redémarrer.")
        self._closing_for_update = True
        QTimer.singleShot(300, self.close)

    # ================================================================= closing
    def closeEvent(self, ev):
        self._cancel.set()
        self._update_cancel.set()
        self.reader.stop()
        if self.vct_proc:
            self.vct_proc.terminate()
            self.vct_proc.waitForFinished(2000)
        super().closeEvent(ev)


HELP_HTML = """
<h2>Matériel nécessaire</h2>
<ul>
<li><b>Mise à jour PhobGCC 2</b> : un câble USB-C branché directement sur le PCB de la Phob.</li>
<li><b>Calibration / test / Visual Controller Test</b> : l'adaptateur GameCube officiel Nintendo
(WUP-028, Wii U / Switch) ou un clone compatible, en mode <b>Wii U/PC</b> (interrupteur côté PC),
les deux câbles USB branchés (le noir sert au rumble).</li>
</ul>
<h2>Pilote de l'adaptateur</h2>
<p><b>Windows</b> : comme pour Dolphin, installe le pilote <b>WinUSB</b> avec
<a href="https://zadig.akeo.ie/">Zadig</a> (Options → List All Devices → « WUP-028 » → WinUSB → Replace Driver).
<br><b>Linux</b> : copie <code>packaging/51-gcadapter.rules</code> dans <code>/etc/udev/rules.d/</code>,
puis <code>sudo udevadm control --reload-rules</code> et rebranche l'adaptateur.
<br><b>macOS</b> : aucun pilote requis.</p>
<p>Un seul programme à la fois peut utiliser l'adaptateur : l'outil le libère automatiquement quand il lance
Visual Controller Test, mais ferme Dolphin avant d'utiliser l'onglet calibration.</p>
<h2>Mettre à jour une PhobGCC 2</h2>
<ol><li>Choisis la release (la plus récente est sélectionnée), clique « Mettre à jour la manette ».</li>
<li>Débranche la manette, maintiens <b>Start</b> (ou le bouton BOOTSEL du PCB) et branche l'USB-C :
un lecteur <b>RPI-RP2</b> apparaît, l'outil y copie le .uf2 tout seul.</li>
<li>La manette redémarre. Fais un <b>soft reset (A+B+Z+Start)</b>, comme le demandent les notes de version.</li></ol>
<p>Le fichier est vérifié (empreinte SHA-256 publiée par GitHub + structure UF2 / famille RP2040) avant d'être écrit.</p>
<h2>Tester le snapback</h2>
<p>Même principe que l'oscilloscope de GTS : pousse le stick à fond (au-delà de ±64), maintiens, puis lâche.
La mesure démarre quand le stick revient de 15 unités vers le centre (avec 25 ms d'historique) et s'arrête quand il
est resté 25 ms au centre. Le rebond du côté opposé doit rester entre <b>-22 et +22</b>, la zone neutre de Melee.
La précision dépend de la fréquence de l'adaptateur, affichée dans l'onglet (125 Hz d'origine, 1000 Hz si overclocké).</p>
<h2>Calibrer</h2>
<p>Branche la manette sur l'adaptateur, choisis le stick, clique « Démarrer » puis fais le combo indiqué
(hors safe mode). Le firmware affiche la position à viser sur l'autre stick : l'outil la lit et te guide
étape par étape (32 mesures puis 12 ajustements d'encoches).</p>
<h2>Liens</h2>
<ul><li><a href="https://github.com/PhobGCC/PhobGCC-SW">PhobGCC-SW</a> (firmware, guides de calibration)</li>
<li><a href="https://github.com/mardy/VisualControllerTest">Visual Controller Test</a> (sources Wii)</li></ul>
"""
