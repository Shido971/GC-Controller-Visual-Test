**PhobGCC Tool**

## Téléchargements
| Fichier | Pour |
|---|---|
| `PhobGCCTool-windows-….zip` | Windows 10/11 : décompresse, puis lance `PhobGCCTool.exe` |
| `PhobGCCTool-android-….apk` | Android 7+ : ouvre le fichier sur le téléphone et autorise l'installation |
| `PhobGCCTool-linux-….tar.gz` | Linux x86_64 : extrais, puis lance `PhobGCCTool/PhobGCCTool` |

## Fonctions
- Mise à jour du firmware PhobGCC depuis les releases officielles (SHA-256 vérifié)
- Calibration guidée en direct via l'adaptateur GameCube
- Test de snapback (méthode GTS)
- Visual Controller Test en natif (PC et Android)
- Mise à jour de l'appli directement depuis l'appli (PC et Android, onglet Aide)
- GTS (GCC Test Suite) en natif (PC et Android) : test manette, oscilloscopes, gâchettes, coordonnées Melee, gate…

## À savoir
- **Windows** : l'adaptateur GameCube a besoin du pilote **WinUSB** (installé avec Zadig, comme pour Dolphin).
- **Android** : un câble ou adaptateur **OTG** est nécessaire. L'APK est signé avec une clé de développement (installation directe, pas via le Play Store).
- Pas encore testé sur du matériel réel : tout retour est bienvenu dans les Issues.

## Licences
GTS (greenwave-1) est distribué sous licence **GPL-3.0** ; ses sources et celles du portage sont dans ce dépôt (`gts-pc/`).
