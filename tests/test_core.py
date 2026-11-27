"""Tests hors matériel : parsing adaptateur, releases, UF2, suivi de calibration."""
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phobtool import adapter, calibration as cal, flasher, releases  # noqa: E402


# --------------------------------------------------------------------- adapter
def test_parse_report():
    r = bytearray(37)
    r[0] = 0x21
    r[1:10] = bytes([0x14, 0x01, 0x09, 0xFF, 0x80, 0x80, 0x00, 200, 3])
    r[19:28] = bytes([0x20, 0x80, 0x02, 0x80, 0x80, 0x80, 0x80, 0, 0])
    pads = adapter.parse_report(bytes(r))
    assert pads[0].connected and not pads[0].wireless
    assert pads[0].buttons == {"A", "S", "L"}
    assert pads[0].a_xy == (127, 0) and pads[0].c_xy == (0, -128)
    assert not pads[1].connected
    assert pads[2].wireless and pads[2].buttons == {"Du", "Z"}
    assert adapter.parse_report(b"\x22" + bytes(36)) is None


# -------------------------------------------------------------------- releases
def test_parse_releases_and_classify():
    data = [{
        "tag_name": "v0.31", "name": "v0.31", "published_at": "2025-11-16T00:39:27Z",
        "prerelease": False, "draft": False, "body": "notes", "html_url": "u",
        "assets": [
            {"name": "phobgcc_rp2040_v0.31.uf2", "browser_download_url": "x", "size": 359000,
             "digest": "sha256:090aa94640321e6490ca55593170aa84c482c96cc0e698371b1373661bafaee0"},
            {"name": "PhobGCC_Teensy4_0_v0.31.hex", "browser_download_url": "y", "size": 1},
            {"name": "PhobGCC_Teensy3_2_v0.31.hex", "browser_download_url": "z", "size": 1},
        ]},
        {"tag_name": "draft", "draft": True, "assets": []}]
    rel = releases.parse_releases(data)
    assert len(rel) == 1
    r = rel[0]
    assert r.firmware_for(releases.BOARD_RP2040).sha256.startswith("090aa946")
    assert r.firmware_for(releases.BOARD_TEENSY40).name.startswith("PhobGCC_Teensy4")
    assert r.firmware_for(releases.BOARD_TEENSY32).name.startswith("PhobGCC_Teensy3")
    assert r.published_at == "2025-11-16"


# ------------------------------------------------------------------------- uf2
def make_uf2(n=4, family=flasher.RP2040_FAMILY_ID):
    out = b""
    for i in range(n):
        hdr = struct.pack("<8I", flasher.UF2_MAGIC_START0, flasher.UF2_MAGIC_START1,
                          flasher.UF2_FLAG_FAMILY_ID, 0x10000000 + 256 * i, 256, i, n, family)
        out += hdr + bytes(476) + struct.pack("<I", flasher.UF2_MAGIC_END)
    return out


def test_uf2_validation(tmp_path):
    good = tmp_path / "ok.uf2"
    good.write_bytes(make_uf2())
    info = flasher.validate_uf2(good)
    assert info.blocks == 4 and info.payload_bytes == 1024 and info.start_addr == 0x10000000
    bad = tmp_path / "bad.uf2"
    bad.write_bytes(make_uf2(family=0x12345678))
    try:
        flasher.validate_uf2(bad)
        assert False
    except flasher.FirmwareError:
        pass
    trunc = tmp_path / "t.uf2"
    trunc.write_bytes(make_uf2()[:700])
    try:
        flasher.validate_uf2(trunc)
        assert False
    except flasher.FirmwareError:
        pass


def test_rp2_drive_detection(tmp_path):
    (tmp_path / "INFO_UF2.TXT").write_text("UF2 Bootloader v3.0\nModel: Raspberry Pi RP2\nBoard-ID: RPI-RP2\n")
    assert flasher.is_rp2_bootloader(tmp_path)
    fw = tmp_path / "fw.uf2"
    fw.write_bytes(make_uf2())
    dest = tmp_path / "drive"
    dest.mkdir()
    flasher.flash_uf2(fw, dest)
    assert (dest / "fw.uf2").read_bytes() == fw.read_bytes()


# ----------------------------------------------------------------- calibration
class FirmwareSim:
    """Machine d'états de calibration du firmware PhobGCC (phobGCC.h / stick.h)."""

    def __init__(self, stick="A", inactive=()):
        self.stick = stick
        self.step = -1
        self.inactive = set(inactive)   # encoches tertiaires non mesurées
        self.undo_ok = False

    def start(self):
        self.step = 0

    def _skip_inactive(self, direction):
        while (cal.NO_OF_CAL_POINTS <= self.step < cal.NO_OF_CAL_POINTS + cal.NO_OF_ADJ_NOTCHES
               and cal.NOTCH_ADJ_ORDER[self.step - cal.NO_OF_CAL_POINTS] in self.inactive):
            self.step += direction

    def advance(self):
        self.step += 1
        self.undo_ok = self.step >= 2 and self.step != 32
        self._skip_inactive(+1)
        if self.step >= cal.NO_OF_CAL_POINTS + cal.NO_OF_ADJ_NOTCHES:
            self.step = -1

    def undo(self):
        if not self.undo_ok:
            return
        s = self.step
        if s % 2 == 0 and s < 32 and s != 0:
            s -= 2
        elif s % 2 == 1 and s < 32 and s != 0:
            s = max(s - 3, 0)
        elif s > 32:
            s -= 1
        self.step = s
        self._skip_inactive(-1)

    def skip(self):
        if 0 <= self.step < 32:
            self.step = 32
            self._skip_inactive(+1)

    def pad(self, buttons=()):
        """Rapport adaptateur : la cible est affichée sur l'autre stick."""
        x = y = 0.0
        if 0 <= self.step < 32:
            p = cal.CAL_ORDER[self.step]
            if p % 2:
                x, y = cal.notch_target_xy(p // 2)
        elif self.step >= 32:
            x, y = cal.notch_target_xy(cal.NOTCH_ADJ_ORDER[self.step - 32])
            # angle mesuré légèrement différent de l'idéal
            x, y = x * math.cos(0.05) - y * math.sin(0.05), x * math.sin(0.05) + y * math.cos(0.05)
        ox, oy = int(round(x)) + 128, int(round(y)) + 128
        kw = dict(connected=True, buttons=frozenset(buttons))
        if self.stick == "A":
            return adapter.PadState(cx=ox, cy=oy, ax=128, ay=128, **kw)
        return adapter.PadState(ax=ox, ay=oy, cx=128, cy=128, **kw)


def run(sim, tr, script):
    """script : liste d'actions 'A', 'Z', 'S'. Chaque pression = 3 trames appuyé + 3 relâché.
    Le firmware réagit à la trame suivante (la cible change une trame après l'appui)."""
    trace = []
    for act in script:
        for f in range(3):
            pad = sim.pad({act})
            g = tr.feed(pad)
            if f == 0:
                {"A": sim.advance, "Z": sim.undo, "S": sim.skip}[act]()
        for _ in range(3):
            g = tr.feed(sim.pad())
        trace.append((sim.step, tr.step, tr.state))
    return trace


FROZEN_PAD = adapter.PadState(connected=True, ax=255, ay=255, cx=255, cy=255, l=59, r=59)


def enter_calibration(tr, sim, combo_stick, hold_after=0):
    """Comme sur la vraie manette : A+X+Y d'abord, puis L ou R. Dès que le combo est complet le firmware
    gèle sa sortie (4 axes à 255, aucun bouton) pendant 2 s : le combo complet n'apparaît jamais."""
    for _ in range(20):
        tr.feed(sim.pad({"A", "X", "Y"}))
    sim.stick = combo_stick
    sim.start()
    for _ in range(250):                     # 2 s à 125 Hz
        tr.feed(FROZEN_PAD)
    for _ in range(hold_after):
        tr.feed(sim.pad())


def start(stick="A", inactive=()):
    sim = FirmwareSim(stick, inactive)
    tr = cal.CalibrationTracker()
    tr.arm(stick)
    enter_calibration(tr, sim, stick, hold_after=5)
    assert tr.state == cal.MEASURE and tr.step == 0, (tr.state, tr.step)
    return sim, tr


def check(trace):
    for fw, tk, state in trace:
        if fw == -1:
            assert state == cal.DONE, (fw, tk, state)
        else:
            assert fw == tk, trace


def test_full_calibration_a_stick():
    sim, tr = start("A")
    check(run(sim, tr, ["A"] * 44))
    assert tr.state == cal.DONE


def test_full_calibration_c_stick():
    sim, tr = start("C")
    check(run(sim, tr, ["A"] * 44))
    assert tr.state == cal.DONE


def test_no_freeze_means_no_calibration():
    """Safe mode ou manette d'origine : combo tenu, la manette ne gèle rien -> l'appli ne suit rien."""
    sim = FirmwareSim("C")
    tr = cal.CalibrationTracker()
    tr.arm("C")
    for _ in range(200):                     # combo complet tenu 1,6 s, sticks libres
        g = tr.feed(sim.pad({"A", "X", "Y", "R"}))
    assert tr.state == cal.ARMED and tr.error and "safe mode" in g.detail
    for _ in range(300):                     # l'utilisateur bouge le stick principal : rien ne doit avancer
        tr.feed(adapter.PadState(connected=True, ax=128 + 90, ay=128 + 40))
    assert tr.state == cal.ARMED and tr.step == -1
    # nouvel essai, cette fois la manette réagit
    enter_calibration(tr, sim, "C", hold_after=5)
    assert tr.state == cal.MEASURE and tr.step == 0 and tr.error is None
    check(run(sim, tr, ["A"] * 44))
    assert tr.state == cal.DONE


def test_freeze_without_combo_is_ignored():
    """Un gel dû à un autre réglage (pas de A+X+Y juste avant) ne démarre pas le suivi."""
    tr = cal.CalibrationTracker()
    tr.arm("A")
    for _ in range(250):
        tr.feed(FROZEN_PAD)
    assert tr.state == cal.ARMED


def test_wrong_stick_combo_is_followed():
    """Appli réglée sur C-stick mais combo A+X+Y+L : la manette calibre le stick analogique, l'appli suit."""
    sim = FirmwareSim("A")
    tr = cal.CalibrationTracker()
    tr.arm("C")
    for _ in range(20):
        tr.feed(sim.pad({"A", "X", "Y"}))
    for _ in range(3):
        tr.feed(sim.pad({"A", "X", "Y", "L"}))   # L vu juste avant le gel
    sim.start()
    for _ in range(250):
        g = tr.feed(FROZEN_PAD)
    assert tr.state == cal.FROZEN and tr.stick == "A" and "stick analogique" in g.detail
    for _ in range(5):
        tr.feed(sim.pad())
    check(run(sim, tr, ["A"] * 44))
    assert tr.state == cal.DONE


def test_timestamps_drive_timeout():
    """Avec horodatage réel (adaptateur 1000 Hz) le délai de confirmation suit le temps, pas les trames."""
    sim = FirmwareSim("C")
    tr = cal.CalibrationTracker()
    tr.arm("C")
    for i in range(400):                     # 0,4 s à 1000 Hz : pas encore d'erreur
        p = sim.pad({"A", "X", "Y", "R"})
        p.t = 10.0 + i / 1000
        tr.feed(p)
    assert tr.error is None
    for i in range(400, 800):
        p = sim.pad({"A", "X", "Y", "R"})
        p.t = 10.0 + i / 1000
        tr.feed(p)
    assert tr.error


def test_undo_and_skip():
    sim, tr = start("A")
    check(run(sim, tr, ["A"] * 7 + ["Z"] + ["A"] * 4 + ["Z", "Z"] + ["A"] * 3 + ["S"] + ["A"] * 3 + ["Z"] + ["A"] * 10))
    assert tr.state == cal.DONE


def test_inactive_tertiary_notches_are_skipped():
    # gate octogonale : aucune encoche tertiaire mesurée
    sim, tr = start("A", inactive={1, 3, 5, 7, 9, 11, 13, 15})
    # 32 mesures + 3 encoches diagonales ajustées
    trace = run(sim, tr, ["A"] * 35)
    check(trace)
    assert tr.state == cal.ADJUST and cal.step_notch(tr.step) == 14
    # l'appui suivant est le dernier : le firmware quitte, la cible revient au neutre
    run(sim, tr, ["A"] * 1)
    assert sim.step == -1
    for _ in range(30):
        tr.feed(sim.pad())
    assert tr.state == cal.DONE


def test_guidance_texts():
    sim, tr = start("A")
    g = tr.guidance()
    assert "neutre" in g.title
    run(sim, tr, ["A"])
    g = tr.guidance()
    assert "droite" in g.title and g.target_xy[0] > 90


# -------------------------------------------------------------------- snapback
from phobtool import snapback as sb  # noqa: E402


def _run(samples):
    det = sb.SnapbackDetector()
    out = []
    for s in samples:
        r = det.feed(s.t, s.x, s.y)
        if r:
            out.append(r)
    return det, out


def test_snapback_bad_release_detected():
    det, res = _run(sb.simulate_release(start=100, overshoot=0.45))
    assert len(res) == 1
    r = res[0]
    assert r.axis == "x" and r.direction == "droite"
    assert r.overshoot < -22 and not r.passed
    assert r.crossings >= 1
    assert 0.9 < r.sample_period_ms < 1.1
    # ~25 ms d'historique avant le lâcher
    assert r.samples[0].t <= r.t0 - 0.02
    assert det.state == "waiting"


def test_snapback_good_release_and_directions():
    _, res = _run(sb.simulate_release(start=-100, overshoot=0.1))
    assert res and res[0].direction == "gauche" and res[0].passed
    assert res[0].overshoot > 0  # côté opposé = positif
    _, res = _run(sb.simulate_release(start=95, axis="y", overshoot=0.15))
    assert res and res[0].axis == "y" and res[0].direction == "haut" and res[0].passed


def test_snapback_needs_64_and_held_elsewhere_cancels():
    # jamais au-delà de 64 : pas de mesure
    _, res = _run(sb.simulate_release(start=50, overshoot=0.5))
    assert res == []
    # retour partiel puis maintien à 60 : mesure annulée
    det = sb.SnapbackDetector()
    t = 0.0
    for v in [100] * 20 + [80, 60] + [60] * 300:
        assert det.feed(t, v, 0) is None
        t += 0.001
    assert det.state != "recording"


def test_snapback_low_rate_adapter():
    # adaptateur à 125 Hz : la mesure reste possible, la période est rapportée
    _, res = _run(sb.simulate_release(start=100, overshoot=0.45, rate_hz=125, after_ms=200))
    assert len(res) == 1 and 7.5 < res[0].sample_period_ms < 8.5
    m = sb.RateMeter()
    for i in range(100):
        m.tick(i / 125)
    assert 124 < m.hz < 126



def test_updater_version_json():
    from phobtool import updater
    d = {"build": 12, "sha": "abc1234def", "date": "2026-11-25",
         "assets": {"windows": {"name": "w.zip", "url": "https://x/w.zip"}, "linux": {"name": "l.tgz", "url": "u"}}}
    i = updater.parse_version_json(d, "windows")
    assert i.build == 12 and i.asset_name == "w.zip" and "abc1234" in i.label
    assert updater.parse_version_json(d, None).asset_url is None
    s = updater._windows_script(updater.Path("C:/t/new/PhobGCCTool"), updater.Path("C:/App"), "PhobGCCTool.exe", 4242)
    assert '" 4242 "' in s and "/MIR" in s and 'start "" "C:' in s


def test_updater_rejects_bad_zip(tmp=None):
    import tempfile, zipfile
    from phobtool import updater
    d = updater.Path(tempfile.mkdtemp())
    z = d / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../evil.txt", "x")
    try:
        updater.extract(z)
    except RuntimeError:
        return
    raise AssertionError("archive dangereuse acceptée")


if __name__ == "__main__":
    import tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print("OK", name)
