"""Olympe Dictee - app Windows en arriere-plan.

- Raccourci global : dicter la ou est le curseur (transcription + correction IA).
- Panneau : dicter dans une zone, donner du contexte, reformuler/raccourcir/
  resumer, copier/inserer.
- Bouton "Mettre a jour" : self-update depuis GitHub (aucune reinstallation).
"""
from __future__ import annotations
import logging
import platform
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal, Qt, QRunnable, QThreadPool, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QBrush
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLineEdit, QLabel, QDialog, QFormLayout,
    QComboBox, QCheckBox, QMessageBox, QProgressDialog, QProgressBar,
)

from . import config as cfg_mod
from . import audio, inject, groq_client, updater, hotkeys
from .logging_setup import init_logs
from .version import __version__, APP_NOM

log = logging.getLogger("main")


# ----------------------------------------------------------------------------
# Taches asynchrones (reseau) -> resultat livre sur le thread principal.
# ----------------------------------------------------------------------------
class SignauxTache(QObject):
    ok = Signal(object)
    err = Signal(str)


class Tache(QRunnable):
    def __init__(self, fn, *a, **k):
        super().__init__()
        self.fn, self.a, self.k = fn, a, k
        self.signaux = SignauxTache()

    def run(self):
        try:
            self.signaux.ok.emit(self.fn(*self.a, **self.k))
        except Exception as e:
            log.exception("Tache echouee: %s", e)
            self.signaux.err.emit(str(e))


# ⚠ On garde une reference vivante aux taches en cours : sinon le wrapper Python
# (et son QObject de signaux) est garbage-collecte des que lancer() retourne, et
# l'emit part dans le vide -> aucun callback n'est appele. (piege PySide6 classique)
_TACHES_VIVANTES = set()


def lancer(fn, on_ok, on_err, *a, **k):
    t = Tache(fn, *a, **k)
    _TACHES_VIVANTES.add(t)

    def _fini(*_):
        _TACHES_VIVANTES.discard(t)

    t.signaux.ok.connect(on_ok)
    t.signaux.err.connect(on_err)
    t.signaux.ok.connect(_fini)
    t.signaux.err.connect(_fini)
    QThreadPool.globalInstance().start(t)


# ----------------------------------------------------------------------------
# Pont : les callbacks de raccourcis (thread "keyboard") emettent ces signaux,
# recus sur le thread principal (connexion queued automatique).
# ----------------------------------------------------------------------------
class Pont(QObject):
    dictee_curseur = Signal()
    bascule_panneau = Signal()


def _icone(couleur: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(couleur)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(8, 8, 48, 48)
    # petit "micro" blanc
    p.setBrush(QBrush(QColor("white")))
    p.drawRoundedRect(27, 18, 10, 22, 5, 5)
    p.drawRect(31, 40, 2, 8)
    p.drawRect(24, 46, 16, 3)
    p.end()
    return QIcon(pm)


def _beep(ok: bool, actif: bool):
    if not actif:
        return
    try:
        import winsound
        winsound.Beep(880 if ok else 440, 120)
    except Exception:
        pass


class Reglages(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Reglages - " + APP_NOM)
        self.setMinimumWidth(460)
        f = QFormLayout(self)

        self.cle = QLineEdit(cfg.get("groq_api_key", ""))
        self.cle.setEchoMode(QLineEdit.Password)
        self.cle.setPlaceholderText("gsk_...")
        f.addRow("Cle Groq :", self.cle)

        self.modele = QComboBox()
        self.modele.addItems(["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"])
        self.modele.setCurrentText(cfg.get("modele_texte", "openai/gpt-oss-120b"))
        f.addRow("Modele texte :", self.modele)

        self.micro = QComboBox()
        self.micro.addItem("Micro par defaut", "")
        for idx, nom in audio.lister_entrees():
            self.micro.addItem(nom, str(idx))
        cur = str(cfg.get("peripherique_entree", ""))
        pos = self.micro.findData(cur)
        self.micro.setCurrentIndex(pos if pos >= 0 else 0)
        f.addRow("Micro :", self.micro)

        self.rc_dictee = QLineEdit(cfg.get("raccourci_dictee", "ctrl+alt+space"))
        f.addRow("Raccourci dictee :", self.rc_dictee)
        self.rc_panneau = QLineEdit(cfg.get("raccourci_panneau", "ctrl+alt+o"))
        f.addRow("Raccourci panneau :", self.rc_panneau)

        self.auto_inser = QCheckBox("Coller automatiquement au curseur apres dictee")
        self.auto_inser.setChecked(bool(cfg.get("inserer_automatiquement", True)))
        f.addRow(self.auto_inser)
        self.beep = QCheckBox("Petit son au debut/fin d'enregistrement")
        self.beep.setChecked(bool(cfg.get("beep", True)))
        f.addRow(self.beep)

        lh = QHBoxLayout()
        ok = QPushButton("Enregistrer")
        ok.clicked.connect(self.accept)
        an = QPushButton("Annuler")
        an.clicked.connect(self.reject)
        lh.addStretch(1)
        lh.addWidget(an)
        lh.addWidget(ok)
        f.addRow(lh)

    def valeurs(self) -> dict:
        self.cfg["groq_api_key"] = self.cle.text().strip()
        self.cfg["modele_texte"] = self.modele.currentText()
        self.cfg["peripherique_entree"] = self.micro.currentData() or ""
        self.cfg["raccourci_dictee"] = self.rc_dictee.text().strip() or "ctrl+alt+space"
        self.cfg["raccourci_panneau"] = self.rc_panneau.text().strip() or "ctrl+alt+o"
        self.cfg["inserer_automatiquement"] = self.auto_inser.isChecked()
        self.cfg["beep"] = self.beep.isChecked()
        return self.cfg


def _section(txt: str) -> QLabel:
    lab = QLabel(txt)
    lab.setObjectName("section")
    return lab


class Panneau(QWidget):
    def __init__(self, appli: "AppDictee"):
        super().__init__()
        self.appli = appli
        self.setWindowTitle(APP_NOM)
        self.resize(600, 600)
        self.setMinimumSize(480, 520)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 14)
        v.setSpacing(11)

        # En-tete
        titre = QLabel("Olympe Dictee")
        titre.setObjectName("titre")
        v.addWidget(titre)
        sous = QLabel("Dictee vocale + correction IA")
        sous.setObjectName("sous")
        v.addWidget(sous)
        v.addSpacing(6)

        # Zone de travail
        tete = QHBoxLayout()
        tete.addWidget(_section("Zone de travail"))
        tete.addStretch(1)
        self.lbl_etat = QLabel("")
        self.lbl_etat.setObjectName("sous")
        tete.addWidget(self.lbl_etat)
        v.addLayout(tete)

        self.zone = QPlainTextEdit()
        self.zone.setPlaceholderText("Clique sur 'Dicter ici' et parle, ou colle du texte...")
        v.addWidget(self.zone, 1)

        self.btn_dicter = QPushButton("  Dicter ici")
        self.btn_dicter.setObjectName("primaire")
        self.btn_dicter.setMinimumHeight(40)
        self.btn_dicter.clicked.connect(self.appli.toggle_dictee_panneau)
        v.addWidget(self.btn_dicter)

        # Indicateur de niveau de voix
        self.vumetre = QProgressBar()
        self.vumetre.setRange(0, 100)
        self.vumetre.setTextVisible(False)
        self.vumetre.setFixedHeight(7)
        self.vumetre.setValue(0)
        v.addWidget(self.vumetre)

        # Contexte
        v.addWidget(_section("Contexte (optionnel)"))
        self.contexte = QPlainTextEdit()
        self.contexte.setPlaceholderText("Colle un lien, des infos... pour aider l'IA")
        self.contexte.setFixedHeight(56)
        v.addWidget(self.contexte)

        # Transformations
        v.addWidget(_section("Transformer"))
        g = QHBoxLayout()
        g.setSpacing(8)
        for libelle, action in [("Nettoyer", "nettoyer"), ("Reformuler pro", "reformuler_pro"),
                                ("Raccourcir", "raccourcir"), ("Resume", "resume")]:
            b = QPushButton(libelle)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, a=action: self.appli.transformer_zone(a))
            g.addWidget(b)
        v.addLayout(g)

        gl = QHBoxLayout()
        gl.setSpacing(8)
        self.instr = QLineEdit()
        self.instr.setPlaceholderText("Instruction libre (ex : traduis en anglais)...")
        bl = QPushButton("Appliquer")
        bl.clicked.connect(lambda: self.appli.transformer_zone("libre", self.instr.text()))
        gl.addWidget(self.instr, 1)
        gl.addWidget(bl)
        v.addLayout(gl)

        v.addSpacing(4)
        # Actions sortie
        b = QHBoxLayout()
        b.setSpacing(8)
        bc = QPushButton("Copier")
        bc.clicked.connect(self.copier)
        bi = QPushButton("Inserer au curseur")
        bi.setObjectName("primaire")
        bi.clicked.connect(self.inserer_au_curseur)
        b.addWidget(bc)
        b.addWidget(bi)
        b.addStretch(1)
        bd = QPushButton("Diagnostic")
        bd.clicked.connect(self.appli.diagnostic)
        br = QPushButton("Reglages")
        br.clicked.connect(self.appli.ouvrir_reglages)
        bm = QPushButton("Mettre a jour")
        bm.clicked.connect(self.appli.mettre_a_jour)
        b.addWidget(bd)
        b.addWidget(br)
        b.addWidget(bm)
        v.addLayout(b)

        self.lbl_statut = QLabel("Pret - v" + __version__)
        self.lbl_statut.setObjectName("statut")
        v.addWidget(self.lbl_statut)

    def set_rec(self, on: bool):
        self.btn_dicter.setObjectName("rec" if on else "primaire")
        self.btn_dicter.setText("  Arreter" if on else "  Dicter ici")
        # reapplique la feuille de style a ce bouton
        self.btn_dicter.style().unpolish(self.btn_dicter)
        self.btn_dicter.style().polish(self.btn_dicter)

    def copier(self):
        inject._ecrire_presse_papiers(self.zone.toPlainText())
        self.statut("Texte copie dans le presse-papiers.")

    def inserer_au_curseur(self):
        texte = self.zone.toPlainText()
        if not texte.strip():
            return
        self.hide()  # laisse le focus revenir a l'appli precedente
        QTimer.singleShot(350, lambda: inject.coller_au_curseur(texte))
        self.statut("Insere au curseur.")

    def statut(self, s: str):
        self.lbl_statut.setText(s)

    def closeEvent(self, e):
        # Fermer le panneau ne quitte pas l'app : on le masque.
        e.ignore()
        self.hide()


class Overlay(QWidget):
    """Petite fenetre flottante pendant la dictee au curseur : montre que ca ecoute."""
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("overlayBox")
        self.setStyleSheet(
            "#overlayBox{background:#0c1420;border:1px solid #33c5f4;border-radius:12px;}")
        self.setFixedWidth(260)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(7)
        self.lbl = QLabel("Micro ouvert - parle, re-appuie pour ecrire")
        self.lbl.setStyleSheet("color:#cfe3f2;font-size:11px;background:transparent;border:none;")
        v.addWidget(self.lbl)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        v.addWidget(self.bar)

    def placer(self):
        try:
            g = QApplication.primaryScreen().availableGeometry()
            self.adjustSize()
            self.move(g.center().x() - self.width() // 2, g.top() + 46)
        except Exception:
            pass


class AppDictee(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = cfg_mod.charger()
        self.enregistreur = audio.Enregistreur()
        self.mode = None  # None | "curseur" | "panneau"

        self.icone_idle = _icone("#2E9FCE")
        self.icone_rec = _icone("#E53935")

        self.tray = QSystemTrayIcon(self.icone_idle)
        self.tray.setToolTip(APP_NOM)
        menu = QMenu()
        a_pan = QAction("Ouvrir le panneau", self); a_pan.triggered.connect(self.afficher_panneau)
        a_reg = QAction("Reglages", self); a_reg.triggered.connect(self.ouvrir_reglages)
        a_maj = QAction("Mettre a jour", self); a_maj.triggered.connect(self.mettre_a_jour)
        a_quit = QAction("Quitter", self); a_quit.triggered.connect(self.quitter)
        for a in (a_pan, a_reg, a_maj):
            menu.addAction(a)
        menu.addSeparator(); menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clic)
        self.tray.show()

        self.panneau = Panneau(self)
        self.overlay = Overlay()
        self.timer_niveau = QTimer()
        self.timer_niveau.setInterval(60)
        self.timer_niveau.timeout.connect(self._maj_niveau)

        self.gest = hotkeys.GestionnaireRaccourcis()
        self.app.installNativeEventFilter(self.gest)
        self.gest.active.connect(self._raccourci_active)
        self._id_dictee = None
        self._id_panneau = None
        self._enregistrer_raccourcis()

        if not self.cfg.get("groq_api_key"):
            QTimer.singleShot(400, self._premier_lancement)
        elif self.cfg.get("verifier_maj_au_demarrage", True):
            QTimer.singleShot(2500, lambda: self.mettre_a_jour(silencieux=True))

    # --- raccourcis globaux (natifs Windows) --------------------------------
    def _enregistrer_raccourcis(self):
        self.gest.tout_retirer()
        self._id_dictee = self.gest.enregistrer(self.cfg["raccourci_dictee"])
        self._id_panneau = self.gest.enregistrer(self.cfg["raccourci_panneau"])
        if not self._id_dictee or not self._id_panneau:
            self.tray.showMessage(
                APP_NOM,
                "Un raccourci n'a pas pu etre enregistre (deja pris par une autre "
                "appli ?). Change-le dans Reglages.", self.icone_idle, 6000)
        else:
            self.tray.showMessage(
                APP_NOM,
                "Raccourcis actifs : %s = dicter, %s = panneau." %
                (self.cfg["raccourci_dictee"], self.cfg["raccourci_panneau"]),
                self.icone_idle, 4000)

    def _raccourci_active(self, hk_id: int):
        if hk_id == self._id_dictee:
            self.toggle_dictee_curseur()
        elif hk_id == self._id_panneau:
            self.bascule_panneau()

    # --- diagnostic (fait parler l'app, visible a l'ecran) ------------------
    def diagnostic(self):
        self.afficher_panneau()
        lignes = [
            "=== DIAGNOSTIC Olympe Dictee v%s ===" % __version__,
            "Systeme    : %s" % platform.platform(),
            "Cle Groq   : %s" % ("presente" if self.cfg.get("groq_api_key") else "ABSENTE (-> Reglages)"),
            "Modele     : %s" % self.cfg.get("modele_texte"),
            "Raccourcis : dictee=%s (id=%s), panneau=%s (id=%s)" % (
                self.cfg.get("raccourci_dictee"), self._id_dictee,
                self.cfg.get("raccourci_panneau"), self._id_panneau),
        ]
        try:
            mics = audio.lister_entrees()
            lignes.append("Micros (%d) : %s" % (len(mics), ", ".join(n for _, n in mics[:6]) or "aucun"))
        except Exception as e:
            lignes.append("Micros     : erreur %s" % e)
        if not self._id_dictee or not self._id_panneau:
            lignes.append(">> ATTENTION : un raccourci global n'est PAS enregistre "
                          "(deja pris par une autre appli ? change-le dans Reglages).")
        lignes.append(">> Test de transformation IA en cours...")
        self.panneau.zone.setPlainText("\n".join(lignes))
        self.panneau.statut("Diagnostic...")

        def test():
            t0 = time.time()
            out = groq_client.transformer(
                "ceci est un test de diagnostic avec une fote", "nettoyer",
                self.cfg.get("groq_api_key", ""), self.cfg.get("modele_texte"))
            return (time.time() - t0, out)

        def ok(r):
            dt, out = r
            txt = self.panneau.zone.toPlainText().replace(
                ">> Test de transformation IA en cours...",
                ">> Test IA OK en %.1fs : \"%s\"\n>> Tout fonctionne cote IA." % (dt, out))
            self.panneau.zone.setPlainText(txt)
            self.panneau.statut("Diagnostic termine.")

        def err(msg):
            txt = self.panneau.zone.toPlainText().replace(
                ">> Test de transformation IA en cours...",
                ">> Test IA ECHEC : %s\n>> (cle Groq ? connexion internet ?)" % msg)
            self.panneau.zone.setPlainText(txt)
            self.panneau.statut("Diagnostic : erreur.")

        lancer(test, ok, err)

    # --- dictee au curseur --------------------------------------------------
    def toggle_dictee_curseur(self):
        if self.enregistreur.en_cours and self.mode == "curseur":
            self._arreter_et_traiter(cible="curseur")
        elif not self.enregistreur.en_cours:
            self._demarrer("curseur")

    def toggle_dictee_panneau(self):
        if self.enregistreur.en_cours and self.mode == "panneau":
            self._arreter_et_traiter(cible="panneau")
        elif not self.enregistreur.en_cours:
            self._demarrer("panneau")
            self.panneau.set_rec(True)
            self.panneau.lbl_etat.setText("Enregistrement...")

    def _demarrer(self, mode):
        if not self.cfg.get("groq_api_key"):
            self._premier_lancement()
            return
        try:
            self.enregistreur.demarrer(self.cfg.get("peripherique_entree", ""))
        except Exception as e:
            self._erreur("Micro indisponible : " + str(e))
            return
        self.mode = mode
        self.tray.setIcon(self.icone_rec)
        self.tray.setToolTip(APP_NOM + " - enregistrement...")
        _beep(True, self.cfg.get("beep", True))
        self.timer_niveau.start()
        if mode == "curseur":
            self.overlay.placer()
            self.overlay.show()

    def _maj_niveau(self):
        niv = int(self.enregistreur.niveau() * 100)
        self.panneau.vumetre.setValue(niv)
        self.overlay.bar.setValue(niv)

    def _arreter_et_traiter(self, cible):
        wav = self.enregistreur.arreter()
        self.mode = None
        self.timer_niveau.stop()
        self.panneau.vumetre.setValue(0)
        self.overlay.hide()
        self.tray.setIcon(self.icone_idle)
        self.tray.setToolTip(APP_NOM)
        _beep(False, self.cfg.get("beep", True))
        if cible == "panneau":
            self.panneau.set_rec(False)
            self.panneau.lbl_etat.setText("Transcription..." if wav else "Rien capte.")
        if not wav:
            return

        def pipeline():
            t = groq_client.transcrire(wav, self.cfg["groq_api_key"],
                                       self.cfg["modele_stt"], self.cfg.get("langue", "fr"))
            t = groq_client.transformer(t, "nettoyer", self.cfg["groq_api_key"],
                                        self.cfg["modele_texte"])
            return t

        if cible == "curseur":
            self.tray.setToolTip(APP_NOM + " - transcription...")
            lancer(pipeline, self._dictee_curseur_prete, self._erreur)
        else:
            lancer(pipeline, self._dictee_panneau_prete, self._erreur)

    def _dictee_curseur_prete(self, texte: str):
        self.tray.setToolTip(APP_NOM)
        if not texte:
            self.tray.showMessage(APP_NOM, "Rien entendu. Verifie le micro (Reglages).",
                                  self.icone_idle, 3000)
            return
        if self.cfg.get("inserer_automatiquement", True):
            inject.coller_au_curseur(texte)
        else:
            inject._ecrire_presse_papiers(texte)
            self.tray.showMessage(APP_NOM, "Texte copie (colle avec Ctrl+V).",
                                  self.icone_idle, 2500)

    def _dictee_panneau_prete(self, texte: str):
        self.panneau.lbl_etat.setText("")
        if not texte:
            self.panneau.statut("Rien entendu. Verifie le micro (Reglages).")
            return
        cur = self.panneau.zone.toPlainText()
        self.panneau.zone.setPlainText((cur + (" " if cur and not cur.endswith("\n") else "") + texte).strip())
        self.afficher_panneau()

    # --- transformations panneau -------------------------------------------
    def transformer_zone(self, action: str, instr: str = ""):
        texte = self.panneau.zone.toPlainText().strip()
        if not texte:
            return
        if not self.cfg.get("groq_api_key"):
            self._premier_lancement()
            return
        ctx = self.panneau.contexte.toPlainText()
        self.panneau.statut("Traitement...")
        lancer(groq_client.transformer,
               lambda out: self._zone_transformee(out),
               self._erreur,
               texte, action, self.cfg["groq_api_key"], self.cfg["modele_texte"],
               ctx, instr)

    def _zone_transformee(self, out: str):
        if out:
            self.panneau.zone.setPlainText(out)
        self.panneau.statut("Fait.")

    # --- panneau / tray -----------------------------------------------------
    def afficher_panneau(self):
        self.panneau.show()
        self.panneau.raise_()
        self.panneau.activateWindow()

    def bascule_panneau(self):
        if self.panneau.isVisible():
            self.panneau.hide()
        else:
            self.afficher_panneau()

    def _tray_clic(self, raison):
        if raison == QSystemTrayIcon.Trigger:
            self.bascule_panneau()

    # --- reglages / maj / erreurs ------------------------------------------
    def ouvrir_reglages(self):
        d = Reglages(dict(self.cfg))
        if d.exec() == QDialog.Accepted:
            self.cfg = d.valeurs()
            cfg_mod.enregistrer(self.cfg)
            self._enregistrer_raccourcis()
            self.tray.showMessage(APP_NOM, "Reglages enregistres.", self.icone_idle, 2000)

    def _premier_lancement(self):
        QMessageBox.information(None, APP_NOM,
            "Bienvenue. Colle ta cle Groq dans les reglages pour commencer.")
        self.ouvrir_reglages()

    def mettre_a_jour(self, silencieux: bool = False):
        url = self.cfg.get("url_manifeste_maj", "")
        log.info("Verification MAJ (silencieux=%s) depuis %s", silencieux, url)

        def on_ok(man):
            if not man:
                if not silencieux:
                    QMessageBox.information(None, APP_NOM, "Tu as deja la derniere version (v%s)." % __version__)
                return
            rep = QMessageBox.question(None, APP_NOM,
                "Nouvelle version %s disponible.\n\n%s\n\nMettre a jour maintenant ?"
                % (man.get("version"), man.get("notes", "")[:300]))
            if rep != QMessageBox.Yes:
                return
            self._telecharger_maj(man)

        def on_err(msg):
            if not silencieux:
                QMessageBox.warning(None, APP_NOM, "Verification impossible : " + msg)

        lancer(updater.verifier, on_ok, on_err, url)

    def _telecharger_maj(self, man):
        # Barre indeterminee (0,0) : pas de mise a jour cross-thread de la valeur.
        dlg = QProgressDialog("Telechargement de la mise a jour...", None, 0, 0)
        dlg.setWindowTitle(APP_NOM)
        dlg.setAutoClose(False)
        dlg.setCancelButton(None)
        dlg.show()

        def on_ok(_):
            dlg.close()
            self.quitter()  # l'updater remplace l'exe puis relance

        def on_err(msg):
            dlg.close()
            QMessageBox.warning(None, APP_NOM, "Mise a jour impossible : " + msg)

        lancer(updater.telecharger_et_installer, on_ok, on_err, man, None)

    def _erreur(self, msg: str):
        self.tray.setIcon(self.icone_idle)
        self.tray.setToolTip(APP_NOM)
        self.panneau.statut("Erreur : " + msg)
        self.tray.showMessage(APP_NOM, msg, self.icone_idle, 4000)
        log.error("Erreur remontee a l'utilisateur: %s", msg)

    def quitter(self):
        try:
            self.gest.tout_retirer()
        except Exception:
            pass
        self.tray.hide()
        self.app.quit()


def main():
    init_logs()
    # Instance unique (evite 2 jeux de raccourcis).
    try:
        import tempfile, os
        verrou = os.path.join(tempfile.gettempdir(), "olympe_dictee.lock")
        f = open(verrou, "w")
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                log.info("Deja en cours d'execution, on quitte.")
                return
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NOM)
    app.setQuitOnLastWindowClosed(False)
    from . import theme
    app.setStyleSheet(theme.QSS)
    _ = AppDictee(app)
    log.info("App demarree, en attente.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
