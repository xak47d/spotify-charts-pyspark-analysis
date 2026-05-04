# Spotify Charts PySpark Analysis

Analisis exploratorio e interpretativo de charts de Spotify usando PySpark, con foco en insights sobre artistas y albumes.

## Alcance

El notebook principal trabaja con:

- `charts_artists_daily.csv`
- `charts_albums_weekly.csv`

Y busca responder preguntas como:

- que tan concentrado esta el liderazgo del chart en pocos artistas
- que tan estable es el Top 10
- que mercados muestran mayor recambio
- que sellos dominan el chart de albumes
- que tan rapido entran los albumes al chart tras su lanzamiento

## Estructura

```text
spotify_project/
├── notebooks/
│   ├── 01_dataset_audit.py
│   └── spotify_charts_full_analysis.ipynb
├── outputs/
│   └── *.png
└── README.md
```

## Requisitos

- Python 3.14+
- Java 17
- PySpark
- pandas
- matplotlib
- seaborn

## Instalacion

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

En macOS, para PySpark:

```bash
export JAVA_HOME="$("/usr/libexec/java_home" -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
```

## Datos

Los archivos fuente no se incluyen directamente dentro del historial git del repositorio porque GitHub normal no maneja bien archivos tan grandes.

Dataset de referencia:

- [Spotify Charts Daily Updated on Kaggle](https://www.kaggle.com/datasets/gonzalopezgil/spotify-charts-daily-updated)

Datasets usados en este proyecto:

- [Release assets: data-assets-v1](https://github.com/xak47d/spotify-charts-pyspark-analysis/releases/tag/data-assets-v1)

Ese release contiene:

- `charts_artists_daily.csv.gz`
- `charts_albums_weekly.csv.gz`

Descarga y descomprime esos archivos dentro de `raw/` antes de ejecutar el notebook.

## Ejecucion

Abre `notebooks/spotify_charts_full_analysis.ipynb` con el entorno `.venv` y ejecútalo de arriba hacia abajo.

El notebook usa PySpark para los agregados grandes y solo convierte a pandas resultados ya resumidos para las graficas.
