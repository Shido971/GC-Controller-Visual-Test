package fr.phobtool

import fr.phobtool.core.Cal
import fr.phobtool.core.CalState
import fr.phobtool.core.CalibrationTracker
import fr.phobtool.core.PadState
import fr.phobtool.core.RateMeter
import fr.phobtool.core.SnapbackDetector
import fr.phobtool.core.SnapbackResult
import fr.phobtool.fw.Board
import fr.phobtool.fw.FirmwareException
import fr.phobtool.fw.IntelHexImage
import fr.phobtool.fw.PicobootProto
import fr.phobtool.fw.TeensyModel
import fr.phobtool.fw.Uf2Image
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/** Tests JVM de la logique (sans matériel). Mêmes scénarios que tests/test_core.py. */
class LogicTest {
    private fun expect(c: Boolean, msg: () -> String = { "échec" }) { if (!c) throw AssertionError(msg()) }

    // ------------------------------------------------------------ adaptateur
    @Test fun parseReport() {
        val r = ByteArray(37); r[0] = 0x21
        byteArrayOf(0x14, 0x01, 0x09, 0xFF.toByte(), 0x80.toByte(), 0x80.toByte(), 0x00, 200.toByte(), 3).copyInto(r, 1)
        byteArrayOf(0x20, 0x80.toByte(), 0x02, 0x80.toByte(), 0x80.toByte(), 0x80.toByte(), 0x80.toByte(), 0, 0).copyInto(r, 19)
        val p = PadState.parseReport(r)!!
        expect(p[0].connected && !p[0].wireless)
        expect(p[0].buttons == setOf("A", "S", "L")) { "${p[0].buttons}" }
        expect(p[0].aX == 127 && p[0].aY == 0 && p[0].cY == -128)
        expect(!p[1].connected)
        expect(p[2].wireless && p[2].buttons == setOf("Du", "Z"))
        r[0] = 0x22
        expect(PadState.parseReport(r) == null)
    }

    // ----------------------------------------------------------- calibration
    /** Machine d'états de calibration du firmware PhobGCC (phobGCC.h / stick.h). */
    private class FirmwareSim(val stick: Char, val inactive: Set<Int> = emptySet()) {
        var step = -1
        var undoOk = false
        fun start() { step = 0 }
        private fun skipInactive(dir: Int) {
            while (step in 32 until 44 && Cal.NOTCH_ADJ_ORDER[step - 32] in inactive) step += dir
        }
        fun advance() {
            step++; undoOk = step >= 2 && step != 32; skipInactive(1)
            if (step >= 44) step = -1
        }
        fun undo() {
            if (!undoOk) return
            val s = step
            step = when {
                s % 2 == 0 && s < 32 && s != 0 -> s - 2
                s % 2 == 1 && s < 32 && s != 0 -> maxOf(s - 3, 0)
                s > 32 -> s - 1
                else -> s
            }
            skipInactive(-1)
        }
        fun skip() { if (step in 0 until 32) { step = 32; skipInactive(1) } }
        fun pad(buttons: Set<String> = emptySet()): PadState {
            var x = 0.0; var y = 0.0
            if (step in 0 until 32) {
                val p = Cal.CAL_ORDER[step]
                if (p % 2 == 1) Cal.notchTarget(p / 2).let { x = it.first; y = it.second }
            } else if (step >= 32) {
                val (a, b) = Cal.notchTarget(Cal.NOTCH_ADJ_ORDER[step - 32])
                x = a * cos(0.05) - b * sin(0.05); y = a * sin(0.05) + b * cos(0.05)
            }
            val ox = x.roundToInt() + 128; val oy = y.roundToInt() + 128
            return if (stick == 'A') PadState(true, false, buttons, 128, 128, ox, oy)
            else PadState(true, false, buttons, ox, oy, 128, 128)
        }
    }

    private fun startCal(stick: Char, inactive: Set<Int> = emptySet()): Pair<FirmwareSim, CalibrationTracker> {
        val sim = FirmwareSim(stick, inactive)
        val tr = CalibrationTracker(); tr.arm(stick)
        val combo = setOf("A", "X", "Y", if (stick == 'A') "L" else "R")
        repeat(5) { tr.feed(sim.pad(combo)) }
        sim.start()
        repeat(5) { tr.feed(sim.pad()) }
        expect(tr.state == CalState.MEASURE && tr.step == 0) { "${tr.state} ${tr.step}" }
        return sim to tr
    }

    private fun run(sim: FirmwareSim, tr: CalibrationTracker, script: List<String>) {
        for (act in script) {
            for (f in 0 until 3) {
                tr.feed(sim.pad(setOf(act)))
                if (f == 0) when (act) { "A" -> sim.advance(); "Z" -> sim.undo(); "S" -> sim.skip() }
            }
            repeat(3) { tr.feed(sim.pad()) }
            // fin du firmware : vérifiée par l'appelant (le suivi attend >20 trames de cible au neutre)
            if (sim.step != -1) expect(sim.step == tr.step) { "firmware ${sim.step} / suivi ${tr.step} (${tr.state}) après $act" }
        }
    }

    @Test fun calibrationFullA() { val (s, t) = startCal('A'); run(s, t, List(44) { "A" }); expect(t.state == CalState.DONE) }
    @Test fun calibrationFullC() { val (s, t) = startCal('C'); run(s, t, List(44) { "A" }); expect(t.state == CalState.DONE) }

    @Test fun calibrationUndoSkip() {
        val (s, t) = startCal('A')
        run(s, t, List(7) { "A" } + "Z" + List(4) { "A" } + listOf("Z", "Z") + List(3) { "A" } + "S" + List(3) { "A" } + "Z" + List(10) { "A" })
        expect(t.state == CalState.DONE)
    }

    @Test fun calibrationOctagonalGate() {
        val (s, t) = startCal('A', setOf(1, 3, 5, 7, 9, 11, 13, 15))
        run(s, t, List(35) { "A" })
        expect(t.state == CalState.ADJUST && Cal.stepNotch(t.step) == 14)
        run(s, t, listOf("A"))
        repeat(30) { t.feed(s.pad()) }
        expect(t.state == CalState.DONE)
    }

    // -------------------------------------------------------------- snapback
    private fun feedAll(samples: List<fr.phobtool.core.Sample>): Pair<SnapbackDetector, List<SnapbackResult>> {
        val d = SnapbackDetector()
        val out = samples.mapNotNull { d.feed(it.t, it.x, it.y) }
        return d to out
    }

    @Test fun snapbackBad() {
        val (d, res) = feedAll(SnapbackDetector.simulateRelease(start = 100.0, overshoot = 0.45))
        expect(res.size == 1)
        val r = res[0]
        expect(r.axis == 'x' && r.direction == "droite" && r.overshoot < -22 && !r.passed && r.crossings >= 1)
        expect(r.samplePeriodMs in 0.9..1.1 && r.samples[0].t <= r.t0 - 0.02)
        expect(d.state == "waiting")
    }

    @Test fun snapbackGoodAndDirections() {
        var res = feedAll(SnapbackDetector.simulateRelease(start = -100.0, overshoot = 0.1)).second
        expect(res.isNotEmpty() && res[0].direction == "gauche" && res[0].passed && res[0].overshoot > 0)
        res = feedAll(SnapbackDetector.simulateRelease(start = 95.0, axis = 'y', overshoot = 0.15)).second
        expect(res.isNotEmpty() && res[0].axis == 'y' && res[0].direction == "haut" && res[0].passed)
    }

    @Test fun snapbackNeeds64AndHeldElsewhereCancels() {
        expect(feedAll(SnapbackDetector.simulateRelease(start = 50.0, overshoot = 0.5)).second.isEmpty())
        val d = SnapbackDetector()
        var t = 0.0
        for (v in List(20) { 100 } + listOf(80, 60) + List(300) { 60 }) { expect(d.feed(t, v, 0) == null); t += 0.001 }
        expect(d.state != "recording")
    }

    @Test fun snapbackLowRate() {
        val res = feedAll(SnapbackDetector.simulateRelease(start = 100.0, overshoot = 0.45, rateHz = 125.0, afterMs = 200.0)).second
        expect(res.size == 1 && res[0].samplePeriodMs in 7.5..8.5)
        val m = RateMeter(); for (i in 0 until 100) m.tick(i / 125.0)
        expect(m.hz in 124.0..126.0)
    }

    // ------------------------------------------------------------------ UF2
    private fun uf2(pages: List<Long>, family: Long = Uf2Image.RP2040_FAMILY): ByteArray {
        val bb = ByteBuffer.allocate(512 * pages.size).order(ByteOrder.LITTLE_ENDIAN)
        pages.forEachIndexed { i, addr ->
            bb.putInt(Uf2Image.MAGIC0.toInt()); bb.putInt(Uf2Image.MAGIC1.toInt()); bb.putInt(Uf2Image.FLAG_FAMILY_ID.toInt())
            bb.putInt(addr.toInt()); bb.putInt(256); bb.putInt(i); bb.putInt(pages.size); bb.putInt(family.toInt())
            repeat(476) { bb.put((i + 1).toByte()) }
            bb.putInt(Uf2Image.MAGIC_END.toInt())
        }
        return bb.array()
    }

    @Test fun uf2ParseAndSectors() {
        val img = Uf2Image.parse(uf2(listOf(0x10000000L, 0x10000100L, 0x10001000L)))
        expect(img.blocks == 3 && img.payloadBytes == 768)
        val sec = img.sectors()
        expect(sec.size == 2 && sec[0].first == 0x10000000L && sec[1].first == 0x10001000L)
        expect(sec[0].second[0] == 1.toByte() && sec[0].second[256] == 2.toByte() && sec[0].second[512] == 0xFF.toByte())
        for (bad in listOf(uf2(listOf(0x10000000L), family = 0x12345678L), uf2(listOf(0x10000000L)).copyOf(700),
                uf2(listOf(0x20000000L)))) {
            try { Uf2Image.parse(bad); expect(false) { "aurait dû échouer" } } catch (_: FirmwareException) {}
        }
    }

    @Test fun picobootCommandLayout() {
        val c = PicobootProto.command(7, PicobootProto.PC_WRITE, PicobootProto.u32s(0x10001000L, 4096), 4096)
        val b = ByteBuffer.wrap(c).order(ByteOrder.LITTLE_ENDIAN)
        expect(c.size == 32)
        expect(b.getInt(0).toLong() and 0xFFFFFFFFL == PicobootProto.MAGIC)
        expect(b.getInt(4) == 7 && c[8] == 0x05.toByte() && c[9] == 8.toByte() && b.getShort(10) == 0.toShort())
        expect(b.getInt(12) == 4096 && b.getInt(16) == 0x10001000 && b.getInt(20) == 4096)
        val r = PicobootProto.command(1, PicobootProto.PC_REBOOT, PicobootProto.u32s(0, PicobootProto.SRAM_END_RP2040, 500), 0)
        expect(r[9] == 12.toByte() && ByteBuffer.wrap(r).order(ByteOrder.LITTLE_ENDIAN).getInt(20) == 0x20042000)
    }

    // ---------------------------------------------------------------- Teensy
    private fun hexLine(type: Int, addr: Int, data: ByteArray): String {
        val b = byteArrayOf(data.size.toByte(), (addr shr 8).toByte(), addr.toByte(), type.toByte()) + data
        val sum = (-(b.sumOf { it.toInt() and 0xFF })) and 0xFF
        return ":" + (b + sum.toByte()).joinToString("") { "%02X".format(it) }
    }

    @Test fun intelHexTeensy4Offset() {
        val text = listOf(
            hexLine(4, 0, byteArrayOf(0x60, 0x00)),
            hexLine(0, 0x0000, ByteArray(16) { it.toByte() }),
            hexLine(0, 0x1400, ByteArray(4) { 0x11 }),
            hexLine(1, 0, ByteArray(0))).joinToString("\n")
        val img = IntelHexImage.parse(text, TeensyModel.TEENSY40)
        expect(img.byteCount == 20 && img.image[5] == 5.toByte() && img.image[0x1400] == 0x11.toByte())
        val blocks = img.blocks()
        expect(blocks.size == 2) { "${blocks.size} blocs" }
        expect(blocks[1][0] == 0x00.toByte() && blocks[1][1] == 0x14.toByte() && blocks[1][64] == 0x11.toByte())
        expect(blocks[0].size == 1024 + 64)
        val boot = img.bootPacket()
        expect(boot[0] == 0xFF.toByte() && boot[2] == 0xFF.toByte() && boot[3] == 0.toByte())
        try {
            IntelHexImage.parse(listOf(hexLine(4, 0, byteArrayOf(0x00, 0x10)), hexLine(0, 0, ByteArray(4)),
                hexLine(1, 0, ByteArray(0))).joinToString("\n"), TeensyModel.TEENSY32)
            expect(false) { "adresse hors mémoire non détectée" }
        } catch (_: FirmwareException) {}
        try { IntelHexImage.parse(":0400000001020304F0\n", TeensyModel.TEENSY40); expect(false) } catch (_: FirmwareException) {}
    }

    @Test fun boardClassify() {
        expect(Board.classify("phobgcc_rp2040_v0.31.uf2") == Board.RP2040)
        expect(Board.classify("PhobGCC_Teensy4_0_v0.28.hex") == Board.TEENSY40)
        expect(Board.classify("PhobGCC_Teensy3_2_v0.28.hex") == Board.TEENSY32)
        expect(Board.classify("notes.txt") == Board.UNKNOWN)
    }
}
