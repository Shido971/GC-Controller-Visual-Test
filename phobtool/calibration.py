"""Suivi en direct de la calibration PhobGCC.

Reproduit la logique du firmware (common/stick.h, common/phobGCC.h, v0.29+) :

* Combo de départ (hors safe mode) : A+X+Y+L = stick analogique, A+X+Y+R = C-stick.
* Phase 1 – mesure, 32 étapes : étape paire = stick au neutre, étape impaire =
  stick poussé dans une encoche. Ordre défini par _calOrder. A (ou L/R) valide,
  Z annule, Start saute directement à la phase 2 (réutilise les points mémorisés).
* Phase 2 – ajustement des encoches (12 encoches, _notchAdjOrder) : X/Y tournent
  l'angle de l'encoche, B le réinitialise, A passe à la suivante. Les encoches
  tertiaires non mesurées sont sautées par le firmware.

Pendant toute la calibration le firmware affiche la position cible sur
*l'autre* stick. On s'en sert pour se resynchroniser : l'appli n'a pas besoin
de deviner, elle lit ce que la manette lui montre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .adapter import PadState

NO_OF_NOTCHES = 16
NO_OF_CAL_POINTS = 32
NO_OF_ADJ_NOTCHES = 12
CAL_ORDER = [0, 1, 8, 9, 16, 17, 24, 25, 4, 5, 12, 13, 20, 21, 28, 29,
             2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23, 26, 27, 30, 31]
NOTCH_ADJ_ORDER = [2, 6, 10, 14, 1, 3, 5, 7, 9, 11, 13, 15]
MAX_STICK_ANGLE = 0.4886921906  # 28°

NOTCH_NAMES = {
    0: "droite", 1: "encoche droite-haut (tertiaire)", 2: "diagonale haut-droite",
    3: "encoche haut-droite (tertiaire)", 4: "haut", 5: "encoche haut-gauche (tertiaire)",
    6: "diagonale haut-gauche", 7: "encoche gauche-haut (tertiaire)", 8: "gauche",
    9: "encoche gauche-bas (tertiaire)", 10: "diagonale bas-gauche",
    11: "encoche bas-gauche (tertiaire)", 12: "bas", 13: "encoche bas-droite (tertiaire)",
    14: "diagonale bas-droite", 15: "encoche droite-bas (tertiaire)",
}
ARROWS = {0: "→", 2: "↗", 4: "↑", 6: "↖", 8: "←", 10: "↙", 12: "↓", 14: "↘"}


def notch_angle(n: int) -> float:
    return n * math.pi / 8


def notch_target_xy(n: int) -> tuple[float, float]:
    """Position affichée par le firmware pour l'encoche n (calcStickValues)."""
    a = notch_angle(n)
    x = 100 * math.atan2(math.sin(MAX_STICK_ANGLE) * math.cos(a), math.cos(MAX_STICK_ANGLE)) / MAX_STICK_ANGLE
    y = 100 * math.atan2(math.sin(MAX_STICK_ANGLE) * math.sin(a), math.cos(MAX_STICK_ANGLE)) / MAX_STICK_ANGLE
    return x, y


def step_notch(step: int) -> Optional[int]:
    """Encoche visée à une étape (None = neutre)."""
    if 0 <= step < NO_OF_CAL_POINTS:
        p = CAL_ORDER[step]
        return p // 2 if p % 2 else None
    if NO_OF_CAL_POINTS <= step < NO_OF_CAL_POINTS + NO_OF_ADJ_NOTCHES:
        return NOTCH_ADJ_ORDER[step - NO_OF_CAL_POINTS]
    return None


def nearest_notch(x: float, y: float) -> int:
    a = math.atan2(y, x) % (2 * math.pi)
    return int(round(a / (math.pi / 8))) % NO_OF_NOTCHES


# étape de phase 1 où l'encoche n est mesurée
PHASE1_STEP_FOR_NOTCH = {CAL_ORDER[i] // 2: i for i in range(NO_OF_CAL_POINTS) if CAL_ORDER[i] % 2}
PHASE2_STEP_FOR_NOTCH = {n: NO_OF_CAL_POINTS + k for k, n in enumerate(NOTCH_ADJ_ORDER)}

IDLE, ARMED, FROZEN, MEASURE, ADJUST, DONE = "idle", "armed", "frozen", "measure", "adjust", "done"
TARGET_CENTER_RADIUS = 25     # en dessous : la cible affichée est le neutre
TARGET_NOTCH_RADIUS = 60      # au-dessus : la cible affichée est une encoche


@dataclass
class Guidance:
    state: str
    step: int
    title: str
    detail: str
    target_xy: Optional[tuple[float, float]]   # cible en unités firmware (±100)
    progress: float                            # 0..1


class CalibrationTracker:
    def __init__(self, stick: str = "A"):
        self.stick = stick           # "A" = stick analogique, "C" = C-stick
        self.state = IDLE
        self.step = -1
        self._prev_buttons: frozenset = frozenset()
        self._last_target_kind: Optional[str] = None   # "center" | "notch"
        self._target_xy: Optional[tuple[float, float]] = None
        self._frozen_frames = 0
        self._center_frames = 0

    # ------------------------------------------------------------------
    def arm(self, stick: str) -> None:
        self.stick = stick
        self.state = ARMED
        self.step = -1
        self._last_target_kind = None
        self._center_frames = 0

    def reset(self) -> None:
        self.state = IDLE
        self.step = -1

    @property
    def combo(self) -> tuple[str, ...]:
        return ("A", "X", "Y", "L") if self.stick == "A" else ("A", "X", "Y", "R")

    def _other_stick(self, pad: PadState) -> tuple[int, int]:
        return pad.c_xy if self.stick == "A" else pad.a_xy

    # ------------------------------------------------------------------
    def feed(self, pad: PadState) -> Guidance:
        held = pad.buttons
        down = held - self._prev_buttons
        self._prev_buttons = held

        if self.state == ARMED:
            if pad.pressed(*self.combo):
                self.state = FROZEN
                self._frozen_frames = 0
        elif self.state == FROZEN:
            # le firmware gèle les sticks ~2 s ; on attend que les boutons du combo soient relâchés
            self._frozen_frames += 1
            if not (held & set(self.combo)):
                self.state = MEASURE
                self.step = 0
                self._last_target_kind = "center"
        elif self.state in (MEASURE, ADJUST):
            self._track(pad, down)

        return self.guidance()

    def _track(self, pad: PadState, down: frozenset) -> None:
        ox, oy = self._other_stick(pad)
        r = math.hypot(ox, oy)
        kind = None
        if r < TARGET_CENTER_RADIUS:
            kind = "center"
        elif r > TARGET_NOTCH_RADIUS:
            kind = "notch"
        if kind:
            self._target_xy = (float(ox), float(oy))

        # indices fournis par les boutons
        if "S" in down and self.state == MEASURE:
            self.state = ADJUST
            self.step = NO_OF_CAL_POINTS
            self._last_target_kind = None
            return
        if "Z" in down:
            if self.state == MEASURE and self.step > 0:
                self.step = max(0, self.step - (2 if self.step % 2 == 0 else 3))
            elif self.state == ADJUST and self.step > NO_OF_CAL_POINTS:
                self.step -= 1
            self._last_target_kind = None
            return
        advanced = bool(down & {"A", "L", "R"})

        if self.state == MEASURE:
            if kind == "notch":
                n = nearest_notch(ox, oy)
                if self._last_target_kind == "notch" and self.step % 2 == 1 and advanced is False \
                        and PHASE1_STEP_FOR_NOTCH.get(n) != self.step:
                    # deux encoches de suite sans neutre : on est passé en phase 2
                    self.state = ADJUST
                    self.step = PHASE2_STEP_FOR_NOTCH.get(n, NO_OF_CAL_POINTS)
                elif self.step == NO_OF_CAL_POINTS - 1 and advanced:
                    self.state = ADJUST
                    self.step = PHASE2_STEP_FOR_NOTCH.get(n, NO_OF_CAL_POINTS)
                else:
                    self.step = PHASE1_STEP_FOR_NOTCH.get(n, self.step)
                self._last_target_kind = "notch"
            elif kind == "center":
                if self._last_target_kind == "notch" and self.step % 2 == 1:
                    self.step += 1
                self._last_target_kind = "center"
            if self.step >= NO_OF_CAL_POINTS:
                self.state = ADJUST
        elif self.state == ADJUST:
            if kind == "notch":
                self._center_frames = 0
                n = nearest_notch(ox, oy)
                if n in PHASE2_STEP_FOR_NOTCH:
                    self.step = PHASE2_STEP_FOR_NOTCH[n]
            elif kind == "center":
                # en phase 2 la cible n'est jamais au neutre : le firmware a terminé
                # (cas où les dernières encoches tertiaires ont été sautées)
                self._center_frames += 1
                if self._center_frames > 20:
                    self.state = DONE
                    return
            if advanced:
                last = self.step == NO_OF_CAL_POINTS + NO_OF_ADJ_NOTCHES - 1
                self.step += 1
                if last or self.step >= NO_OF_CAL_POINTS + NO_OF_ADJ_NOTCHES:
                    self.state = DONE

    # ------------------------------------------------------------------
    def guidance(self) -> Guidance:
        name = "stick analogique" if self.stick == "A" else "C-stick"
        other = "C-stick" if self.stick == "A" else "stick analogique"
        combo = "+".join(self.combo)
        if self.state == IDLE:
            return Guidance(IDLE, -1, "Prêt", "Choisis le stick à calibrer puis clique sur « Démarrer ».", None, 0.0)
        if self.state == ARMED:
            return Guidance(ARMED, -1, f"Lance la calibration du {name}",
                            f"Sur la manette, appuie en même temps sur {combo}.\n"
                            "Si rien ne se passe, la manette est en safe mode : maintiens A+X+Y+Start "
                            "quelques secondes pour le désactiver, puis recommence.", None, 0.0)
        if self.state == FROZEN:
            return Guidance(FROZEN, -1, "Calibration démarrée",
                            "Relâche tous les boutons et laisse le stick au neutre.", None, 0.0)
        if self.state == DONE:
            return Guidance(DONE, self.step, "Calibration terminée ✔",
                            "Le firmware a enregistré les points et les angles d'encoches. "
                            "Vérifie le résultat dans l'onglet test ou avec Visual Controller Test.", None, 1.0)

        notch = step_notch(self.step)
        total = NO_OF_CAL_POINTS + NO_OF_ADJ_NOTCHES
        prog = min(1.0, max(0.0, self.step / total))
        target = notch_target_xy(notch) if notch is not None else (0.0, 0.0)
        if self.state == MEASURE:
            if notch is None:
                title = f"Mesure {self.step + 1}/32 – neutre"
                detail = (f"Lâche le {name} pour qu'il revienne au centre, puis appuie sur A.\n"
                          "Z = annuler la dernière mesure · Start = sauter à l'ajustement des encoches.")
            else:
                arrow = ARROWS.get(notch, "")
                title = f"Mesure {self.step + 1}/32 – {NOTCH_NAMES[notch]} {arrow}"
                tert = notch % 2 == 1
                detail = (f"Pousse le {name} à fond dans l'encoche {NOTCH_NAMES[notch]} "
                          f"(cible affichée sur le {other}), maintiens-le et appuie sur A.")
                if tert:
                    detail += ("\nEncoche tertiaire : si ta gate n'en a pas, laisse le stick au neutre "
                               "et appuie sur A – elle sera ignorée.")
            return Guidance(MEASURE, self.step, title, detail, target, prog)

        k = self.step - NO_OF_CAL_POINTS + 1
        ideal = notch * 22.5 if notch is not None else 0.0
        title = f"Ajustement {k}/12 – {NOTCH_NAMES.get(notch, '?')} {ARROWS.get(notch, '')}"
        detail = (f"Bloque le {name} dans cette encoche. X/Y font tourner l'angle de sortie "
                  f"(objectif ≈ {ideal:.1f}°), B le remet à la valeur mesurée, A valide et passe à la suivante.")
        return Guidance(ADJUST, self.step, title, detail, target, prog)
