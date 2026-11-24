# PhobGCC Tool

Application graphique (Windows / Linux / macOS) pour :

1. **Mettre à jour une PhobGCC** avec la dernière release de
   [PhobGCC-SW](https://github.com/PhobGCC/PhobGCC-SW/releases), de façon guidée.
2. **Calibrer** les sticks en direct via l'adaptateur GameCube officiel : l'appli lit la cible
   que le firmware affiche sur l'autre stick et te guide étape par étape.
3. **Tester le snapback** comme l'oscilloscope de [GTS](https://github.com/greenwave-1/GTS) : courbe du lâcher,
   rebond côté opposé comparé à la zone neutre de Melee (±22), bilan par direction.
4. **Compiler et lancer Visual Controller Test en natif sur PC**
5. **Tout ça aussi sur Android** (dossier `android/`, voir plus bas), avec l'adaptateur officiel (WUP-028).

```
phobtool/            application Python (PySide6)
  releases.py        API GitHub, téléchargement, vérification SHA-256
  flasher.py         validation UF2 (RP2040), détection du lecteur RPI-RP2, copie ; Teensy via teensy_loader_cli
  adapter.py         lecture de l'adaptateur WUP-028 (pyusb/libusb)
  calibration.py     suivi de la calibration (logique reprise du firmware v0.29+)
  snapback.py        détection/mesure du snapback (logique reprise de GTS)
  vct.py             compilation CMake + lancement de VCT
  gui/               interface
vct-pc/              portage PC de Visual Controller Test
  compat/            grrlib.h, Wiiuse/wpad.h, fat.h, libogc → SDL2 + libusb
  src/               rendu SDL2, PAD_* via l'adaptateur, point d'entrée
  CMakeLists.txt     récupère les sources Wii d'origine et les compile SANS les modifier
tests/test_core.py   tests hors matériel (dont un simulateur de la calibration du firmware)
packaging/           règle udev, spec PyInstaller
.github/workflows/   build Windows (MSYS2) + Linux → exécutables prêts à l'emploi
```

## Lancer l'appli (depuis les sources)

```bash
python -m pip install -r requirements.txt
python run_phobtool.py            # ou : python -m phobtool
python run_phobtool.py --demo     # manette virtuelle, pour essayer sans matériel
```

## Pilote de l'adaptateur GameCube

- **Windows** : installe **WinUSB** avec [Zadig](https://zadig.akeo.ie/) sur « WUP-028 » (même manip que pour Dolphin).
- **Linux** : `sudo cp packaging/51-gcadapter.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules`, puis rebranche.
- Adaptateur en mode **Wii U / PC**, les deux câbles USB branchés (le noir alimente le rumble).

Un seul programme à la fois peut ouvrir l'adaptateur : l'appli le libère pendant que Visual Controller Test tourne.

## 1 · Mise à jour du firmware

- La liste vient de l'API GitHub (dernière réponse mise en cache pour le hors-ligne). La release la plus récente
  est présélectionnée, et ses notes de version sont affichées.
- **PhobGCC 2 (RP2040)** : téléchargement → vérification **SHA-256** (empreinte publiée par GitHub) → contrôle de
  la structure UF2 et de la famille RP2040 → l'appli attend le lecteur **RPI-RP2** (manette branchée en USB-C
  **en maintenant Start**, ou le bouton BOOTSEL du PCB) → copie → attente du redémarrage.
- Ensuite : **soft reset A+B+Z+Start**, comme le demandent les notes de version.
- **PhobGCC 1.x (Teensy)** : flash avec `teensy_loader_cli` s'il est dans le PATH. Sinon, l'appli télécharge le .hex
  et tu le flashes avec Teensy Loader. La v0.31 ne publie plus qu'un `.uf2`.

## 2 · Calibration guidée

« Démarrer » → combo **A+X+Y+L** (stick) ou **A+X+Y+R** (C-stick), hors safe mode (A+X+Y+Start maintenu pour le
basculer). Le firmware place la cible sur l'autre stick. L'appli la lit et affiche l'étape :

- **32 mesures** : neutre puis encoche, dans l'ordre du firmware. A valide, Z annule, Start passe directement à l'ajustement.
- **12 ajustements d'encoches** : X/Y tournent l'angle, B le réinitialise, A passe à la suivante. Les encoches
  tertiaires absentes de la gate sont sautées, comme dans le firmware.

Hors calibration, l'onglet sert de testeur : sticks avec traînée, angle, coordonnées Melee, gâchettes et boutons.

## 3 · Snapback

Même déclenchement que GTS : le stick doit dépasser ±64. La mesure démarre quand il revient de 15 unités vers le
centre, avec 25 ms d'historique. Elle s'arrête quand il est resté 25 ms au centre. L'appli affiche la courbe, le
rebond max côté opposé (✔ s'il reste dans ±22), le nombre de sorties de zone, le temps de stabilisation et le min/max
X/Y. Un bilan garde le pire rebond par direction.

**Limite :** l'adaptateur officiel envoie ~125 rapports/s, soit un point toutes les 8 ms. Un rebond très bref peut
passer entre deux points, alors que GTS sur console mesure à chaque poll. Un adaptateur overclocké à 1000 Hz donne une
courbe bien plus fidèle. La fréquence réelle est affichée dans l'onglet.

Correction côté PhobGCC : A+X+D-haut/D-bas (filtre axe X), A+Y+D-haut/D-bas (axe Y), + Z pour le C-stick.

## 4 · Visual Controller Test sur PC

Le `main.c` d'origine (Mr. Reaper, enrichi par Zarithya, dépôt `mardy/VisualControllerTest`) est compilé **tel quel**.
Une fine couche remplace GRRLIB par SDL2, et `PAD_*` par l'adaptateur via libusb (même protocole que Dolphin, rumble inclus).
Les écrans Wiimote/Classic/Guitare sont compilés mais inactifs : il n'y a pas de pile Bluetooth Wii sur PC.

Compilation manuelle :

```bash
# Linux : sudo apt install cmake libsdl2-dev libusb-1.0-0-dev
# Windows : MSYS2 MINGW64 → pacman -S mingw-w64-x86_64-{gcc,cmake,ninja,pkgconf,SDL2,libusb} git
cmake -S vct-pc -B vct-pc/build -DCMAKE_BUILD_TYPE=Release
cmake --build vct-pc/build
vct-pc/build/VisualControllerTest --help
```

Le bouton « Compiler / recompiler » de l'appli fait la même chose. Le champ « Révision » permet de suivre
une autre version des sources Wii (`main` pour la plus récente).

Options : `--fullscreen`, `--scale N`, `--no-sdl-pads`, `--demo`. Quitter : Start+B+X, Échap, ou fermer la fenêtre. F11 : plein écran.

## Appli Android (APK)

Le dossier `android/` contient une appli native en Kotlin, sans dépendance AndroidX, qui fait tout ce que fait la version PC :

| Onglet | Comment ça marche sur Android |
|---|---|
| Firmware | Releases GitHub, SHA-256, contrôle UF2. La PhobGCC 2 est flashée **directement en PICOBOOT** (le protocole de picotool) : il n'y a pas besoin que le téléphone monte le lecteur RPI-RP2. Chaque secteur est relu pour vérification. Teensy via le bootloader HalfKay. |
| Test / calibration | Même suivi de calibration que sur PC (lecture de la cible affichée par le firmware). |
| Snapback | Même détecteur que sur PC (méthode GTS), horodatage de chaque rapport USB. |
| Visual Controller Test | Le même `main.c` Wii, compilé avec SDL2 pour Android. L'appli lui transmet les rapports de l'adaptateur par JNI. |

Matériel : un adaptateur **OTG**. L'adaptateur GameCube fonctionne avec le câble noir seul ; le rumble demande un hub OTG alimenté.
L'appli s'ouvre automatiquement au branchement de l'adaptateur, d'une Phob 2 en BOOTSEL ou d'un Teensy en mode programmation.

**Obtenir l'APK** : pousse le dépôt sur GitHub, le job `android` du workflow produit `PhobGCCTool-android` (`app-release.apk`).
Sur le téléphone, autorise l'installation depuis cette source. L'APK est signé avec une clé de debug : il s'installe
directement, mais il n'est pas prévu pour le Play Store.

Build local (Android SDK + NDK installés) :

```bash
./android/fetch_deps.sh                  # SDL2 + sources Wii de VCT
gradle -p android testReleaseUnitTest assembleRelease
```

## Créer l'exe Windows

Le plus simple : télécharge l'artefact `PhobGCCTool-windows` dans l'onglet **Actions** du dépôt (exe prêt à l'emploi).

Pour le construire toi-même, place `VisualControllerTest.exe`, `SDL2.dll` et `libusb-1.0.dll` dans `bin/` (le job
`windows` du workflow les produit), puis double-clique sur **`build_windows.bat`** sur un PC Windows avec Python. Il produit
`dist\PhobGCCTool\PhobGCCTool.exe`, avec Visual Controller Test intégré. Le dossier `dist\PhobGCCTool` se copie
tel quel, sans rien installer d'autre (le pilote WinUSB de l'adaptateur reste nécessaire).

Autre option : pousse le dossier sur GitHub. Le workflow `.github/workflows/build.yml` produit `PhobGCCTool-windows`
et `PhobGCCTool-linux` dans l'onglet Actions.

## Tests

```bash
python tests/test_core.py                         # parsing, releases, UF2, calibration vs simulateur firmware
cmake --build vct-pc/build && (cd vct-pc/build && ctest)
```
