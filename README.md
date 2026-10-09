# SmartGrid — SolarPumpSizer

**Démo en ligne : https://smartgrid-imenelkhaldi.streamlit.app** *(lien actif après déploiement sur Streamlit Community Cloud)*

Application web de **dimensionnement de stations de pompage solaire hors réseau** (off-grid) :
générateur photovoltaïque, variateur de fréquence et moteur de pompe.

## Objectif pédagogique

- Dimensionner un générateur photovoltaïque : nombre de panneaux en série et de strings en parallèle.
- Vérifier la compatibilité panneaux / variateur / moteur en tenant compte de la **température** :
  tension de circuit ouvert à froid, tension MPP à chaud, courant, puissance crête.
- Comprendre l'effet de la température de cellule (NOCT), du gain bifacial et de l'irradiance.
- Lire une fiche technique constructeur : l'application extrait les caractéristiques des PDF
  importés (toutes marques), ou on les saisit à la main.
- Produire un rapport de dimensionnement (Word) avec schémas d'installation et de câblage.

## Public visé

- Étudiants de BTS (électrotechnique, CRSA), de STI2D (énergie et environnement) et de licence pro.
- Techniciens et formateurs en énergies renouvelables et pompage solaire.

## Technologies

- Python 3, [Streamlit](https://streamlit.io) pour l'interface web.
- NumPy et Matplotlib pour les calculs et les schémas, python-docx pour le rapport.
- pdfplumber, et Tesseract (OCR) pour les fiches techniques scannées, pour l'extraction des PDF.
- Développé par Imen MKAOUAR-ELKHALDI avec l'assistance de **Claude** (Anthropic).

## Lancer en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

L'OCR des PDF scannés nécessite en plus Tesseract et Poppler installés sur le poste
(`packages.txt` liste les paquets utilisés par Streamlit Community Cloud).

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | Interface Streamlit |
| `calculations.py` | Calculs de dimensionnement et vérifications |
| `diagrams.py` | Schémas d'installation et de câblage |
| `pdf_extractor.py` | Extraction des caractéristiques depuis les fiches techniques PDF |
| `report.py` | Génération du rapport Word |
