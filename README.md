# Olympe Dictee

Petite app Windows de dictee vocale avec correction IA, qui ecrit la ou est le
curseur dans n'importe quelle application.

## Ce que ça fait

- **Raccourci global** (defaut `Ctrl+Alt+Espace`) : appuie, parle, re-appuie →
  le texte est transcrit (Groq Whisper), **corrige/ponctue par l'IA**, puis
  colle la ou est ton curseur (Discord, navigateur, Word, Sheets...).
- **Panneau** (defaut `Ctrl+Alt+O`, ou clic sur l'icone pres de l'horloge) :
  - une zone ou la dictee ecrit aussi,
  - un champ **Contexte** (colle un lien / des infos pour aider l'IA),
  - boutons **Nettoyer / Reformuler pro / Raccourcir / Resume** + instruction libre,
  - **Copier** / **Inserer au curseur**.
- **Mettre a jour** : bouton integre, se met a jour tout seul (zero reinstallation).

## Reglages

Au premier lancement, colle ta **cle Groq** dans Reglages. Tout est stocke en
local (`%APPDATA%/OlympeDictee/settings.json`), aucun secret dans le binaire.

## Diagnostic

Logs : `%APPDATA%/OlympeDictee/logs/app.log` (a envoyer en cas de souci).

## Dev

- `pip install -r requirements.txt` puis `python run.py` (Windows).
- Build .exe : pousse sur `main` → GitHub Actions build + publie la release +
  met a jour `latest.json` (le manifeste d'auto-update).
- Pile : PySide6 (tray + panneau), sounddevice (micro), Groq (Whisper + LLM),
  keyboard (raccourcis globaux), pywin32 (presse-papiers), PyInstaller (exe).
