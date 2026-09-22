# ⚡ Torrent Studio

<p align="center">
  <img src="web/favicon.png" alt="Torrent Studio Logo" width="96" height="96" style="border-radius: 20px;">
</p>

<p align="center">
  <strong>Client BitTorrent moderne, ultra-intuitif et autonome avec interface Web sombre & exécutable Windows standalone.</strong>
</p>

<p align="center">
  <a href="https://github.com/je-tu-il/Torrent-Studio/releases/latest">
    <img src="https://img.shields.io/github/v/release/je-tu-il/Torrent-Studio?style=for-the-badge&color=10b981&label=Release" alt="Dernière Release">
  </a>
  <img src="https://img.shields.io/badge/Plateforme-Windows%2010%20%2F%2011-blue?style=for-the-badge&logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Licence-MIT-purple?style=for-the-badge" alt="Licence MIT">
</p>

<p align="center">
  <a href="https://github.com/je-tu-il/Torrent-Studio/releases/latest">
    <b>📥 Télécharger TorrentStudio.exe (Dernière version Windows)</b>
  </a>
</p>

---

## ✨ Fonctionnalités Clés

- 🧲 **Import Magnet instantané par `Ctrl+V`** : Appuyez simplement sur `Ctrl+V` n'importe où sur l'application pour détecter automatiquement un lien magnet, basculer sur l'onglet d'ajout et pré-remplir le champ.
- 📂 **Glisser-Déposer global (Drag & Drop)** : Déposez n'importe quel fichier `.torrent` directement sur la fenêtre du navigateur pour le charger.
- 📁 **Sélecteur de dossiers rapide en 1 clic** : Boutons d'accès direct pour vos dossiers fréquents (*Téléchargements*, *Bureau*, *Vidéos*, *Dossier Projet*, et vos lecteurs *C:\\*, *E:\\*, etc.) ainsi qu'un sélecteur natif Windows de dossiers au premier plan.
- 🌱 **Contrôle précis du Seeding** : 
  - Seeding désactivé par défaut dès qu'un téléchargement s'achève (`auto_seed = False`) pour préserver votre bande passante.
  - Bouton interactif individuel permettant de réactiver le partage d'un torrent spécifique à tout moment.
- 📊 **Monitoring en temps réel** : Vitesse de téléchargement et d'envoi, pourcentage de progression, nombre de seeds et de pairs dans l'essaim, estimation du temps restant (ETA) et ratio.
- 📦 **Créateur de fichier `.torrent`** : Créez vos propres fichiers `.torrent` à partir d'un fichier ou d'un dossier avec personnalisation des pièces, commentaires et trackers.
- 📜 **Historique des torrents** : Journalisation automatique des torrents achevés ou supprimés, avec relance en 1 clic via leur magnet.
- 🌙 **Interface Web Dark Mode** : Design soigné, responsive et élégant, inspiré des meilleurs clients BitTorrent modernes.
- 🛡️ **Mono-instance & Zéro console parasite** : Détection automatique des instances actives (évite les doublons) et fonctionnement discret en arrière-plan sans fenêtre de commande noire.

---

## 🚀 Utilisation

### Option 1 : Exécutable Standalone Windows (Recommandé)
1. Rendez-vous sur la page des [Releases](https://github.com/je-tu-il/Torrent-Studio/releases/latest).
2. Téléchargez **`TorrentStudio.exe`**.
3. Double-cliquez sur `TorrentStudio.exe` : le serveur démarre discrètement en arrière-plan et votre navigateur s'ouvre automatiquement sur l'interface !
*(Aucune installation de Python requise, zéro dépendance externe).*

### Option 2 : Lancement depuis les sources Python
Si vous souhaitez exécuter ou modifier le code source :

1. **Cloner le dépôt** :
   ```bash
   git clone https://github.com/je-tu-il/Torrent-Studio.git
   cd Torrent-Studio
   ```

2. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

3. **Lancer l'application** :
   - Via le lanceur discret Windows : double-cliquez sur **`run.bat`**.
   - Ou en ligne de commande :
     ```bash
     python app.py
     ```

---

## 🛠️ Compilation de l'exécutable (.exe)

Pour générer vous-même l'exécutable standalone `TorrentStudio.exe` :

```bash
build.bat
```
ou via PyInstaller directement :
```bash
pyinstaller TorrentStudio.spec
```
L'exécutable autonome est produit dans le dossier `dist/` (ou `release/`).

---

## 📁 Structure du Projet

```text
Torrent-Studio/
├── app.py                # Serveur FastAPI, routes REST et intégration Windows
├── torrent_manager.py    # Moteur BitTorrent (session libtorrent, DHT, auto-seed)
├── run.bat               # Lanceur discret sans fenêtre noire
├── build.bat             # Script de compilation PyInstaller standalone
├── TorrentStudio.spec    # Configuration PyInstaller
├── requirements.txt      # Dépendances Python
├── web/
│   ├── index.html        # Interface Single Page Application complète
│   ├── favicon.ico       # Icônes multi-résolutions
│   ├── favicon.png
│   └── favicon.svg
└── release/
    └── TorrentStudio.exe # Exécutable Windows standalone prêt à l'emploi
```

---

## 📄 Licence

Ce projet est distribué sous la licence **MIT**. Consultez le fichier [LICENSE](LICENSE) pour plus d'informations.
