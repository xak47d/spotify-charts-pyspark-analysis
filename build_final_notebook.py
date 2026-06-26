from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "notebooks" / "Actividad5_VisualizacionResultados_Equipo51.ipynb"
OUTPUT = ROOT / "notebooks" / "ProyectoFinal_Equipo51.ipynb"


def source(cell) -> str:
    return "".join(cell["source"])


base = nbformat.read(SOURCE, as_version=4)

title = new_markdown_cell(
    """# Proyecto final — Clasificación de la visibilidad competitiva de artistas en Spotify Charts

**Curso:** Análisis de grandes volúmenes de datos
**Equipo:** 51
**Autores:** Fernando Arango Gaviria (A01797660), Jose Luis Armenta Mandujano (A01796933), Demenard Gardy Armand (A01797139) y Ricardo Ismael Vega Aguilar (A01796617)
**Dataset:** Spotify Charts Daily Updated (`charts_artists_daily.csv`)
**Tecnología principal:** PySpark

## Resumen del proyecto

Este notebook integra las etapas desarrolladas durante el curso para estudiar una tarea de aprendizaje aplicada a grandes volúmenes de datos: clasificar cada observación diaria de un artista como `Top` (`rank <= 50`) o `Estable` (`rank > 50`). La población se caracteriza por antigüedad, alcance geográfico y posición competitiva; después se construye una muestra estratificada proporcional cercana a 200,000 registros.

El modelo principal es un `RandomForestClassifier`. Se realiza una búsqueda ligera de hiperparámetros, se selecciona la configuración con mejor AUC-ROC y F1 ponderado, y se estima su estabilidad mediante validación cruzada estratificada de cinco pliegues. Como análisis complementario, `KMeans` identifica perfiles latentes de permanencia, alcance y posición. El objetivo es explicativo: reconocer patrones asociados con la visibilidad competitiva, no pronosticar posiciones futuras."""
)

imports = new_code_cell(
    """from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from pyspark.sql import SparkSession, functions as F, Window
from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, VectorAssembler, StandardScaler
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import (
    MulticlassClassificationEvaluator,
    BinaryClassificationEvaluator,
    ClusteringEvaluator,
)
from pyspark.ml.functions import vector_to_array

try:
    from sklearn.metrics import roc_curve, auc
except Exception:
    roc_curve = None
    auc = None

SEED = 42
TARGET_N = 200_000
K_FOLDS = 5
HYPERPARAMETERS = [
    {'numTrees': 50, 'maxDepth': 6},
    {'numTrees': 50, 'maxDepth': 8},
    {'numTrees': 100, 'maxDepth': 6},
    {'numTrees': 100, 'maxDepth': 8},
]

sns.set_theme(style='whitegrid', palette='deep')
plt.rcParams['figure.dpi'] = 120"""
)

setup = new_code_cell(
    """spark = (
    SparkSession.builder
    .appName('ProyectoFinal_Equipo51')
    .master('local[*]')
    .config('spark.sql.shuffle.partitions', '64')
    .config('spark.driver.memory', '8g')
    .config('spark.sql.execution.arrow.pyspark.enabled', 'true')
    .getOrCreate()
)
spark.sparkContext.setLogLevel('ERROR')

BASE_DIR = Path.cwd()
if (BASE_DIR / 'spotify_project').exists():
    PROJECT_DIR = BASE_DIR / 'spotify_project'
elif BASE_DIR.name == 'spotify_project':
    PROJECT_DIR = BASE_DIR
else:
    PROJECT_DIR = BASE_DIR.parent if BASE_DIR.parent.name == 'spotify_project' else BASE_DIR

RAW_PATH = PROJECT_DIR / 'raw' / 'charts_artists_daily.csv'
REPORT_DIR = PROJECT_DIR / 'report'
ASSET_DIR = REPORT_DIR / 'assets'
REPORT_DIR.mkdir(exist_ok=True)
ASSET_DIR.mkdir(exist_ok=True)

assert RAW_PATH.exists(), f'No se encontró el dataset: {RAW_PATH}'
print(f'Spark: {spark.version}')
print(f'Proyecto: {PROJECT_DIR}')
print(f'Dataset: {RAW_PATH}')
print(f'Salidas del reporte: {REPORT_DIR}')"""
)

audit_md = new_markdown_cell(
    """## 1. Lectura, auditoría y delimitación de la población

La unidad de análisis es un registro artista-país-fecha. Se inspeccionan esquema, volumen, cobertura temporal, nulos críticos y duplicados exactos. Venezuela se excluye porque el trabajo exploratorio previo identificó un patrón de carga anómalo. La ventana de aprendizaje comienza el 21 de octubre de 2022, después de un año de historial, para que la distinción `Nuevo`/`Veterano` no clasifique artificialmente a todos los artistas como nuevos."""
)

raw_cell = base.cells[4]
raw_cell.source = source(raw_cell) + """

n_original = raw.count()
date_bounds = raw.agg(F.min('date').alias('min_date'), F.max('date').alias('max_date')).first()
null_audit = raw.select([
    F.count(F.when(F.col(c).isNull(), c)).alias(c)
    for c in ['date', 'country', 'rank', 'artist_uri', 'days_on_chart']
]).toPandas()
duplicate_count = raw.groupBy('date', 'country', 'rank', 'artist_uri', 'days_on_chart').count().filter(F.col('count') > 1).count()

print(f'Cobertura temporal: {date_bounds.min_date} a {date_bounds.max_date}')
print('Nulos críticos:')
print(null_audit.to_string(index=False))
print(f'Grupos de duplicados exactos en variables clave: {duplicate_count:,}')"""

population_md = new_markdown_cell(
    """## 2. Caracterización, particionamiento y muestra representativa

La población evaluable se caracteriza mediante tres ejes:

- `artist_tenure`: `Veterano` cuando el historial máximo supera 365 días; `Nuevo` en caso contrario.
- `artist_scope`: `Global` cuando el artista aparece en más de 10 países; `Local` en caso contrario.
- `rank_tier`: `Top` para posiciones 1–50 y `Estable` para posiciones 51–200.

Las combinaciones generan ocho estratos. Se aplica muestreo aleatorio estratificado proporcional sin reemplazo, con asignación `n_i = n(N_i/N)`. Esto conserva la heterogeneidad observada y evita que los perfiles mayoritarios borren casos menos frecuentes."""
)

population_cell = base.cells[5]
strata_cell = base.cells[6]
strata_cell.source = source(strata_cell) + """

sample_strata = M.groupBy('partition_id').count().orderBy('partition_id').toPandas()
sample_strata['prop_M'] = sample_strata['count'] / sample_strata['count'].sum()
strata_compare = (
    strata_pd[['partition_id', 'count', 'probability']]
    .rename(columns={'count': 'count_P', 'probability': 'prop_P'})
    .merge(sample_strata.rename(columns={'count': 'count_M'}), on='partition_id')
)
strata_compare['abs_diff_pct'] = (strata_compare['prop_P'] - strata_compare['prop_M']).abs() * 100
print('\\nComparación de proporciones P vs M:')
print(strata_compare.round(4).to_string(index=False))

assert strata_pd['partition_id'].nunique() == 8, 'La población no contiene los ocho estratos esperados.'
assert sample_strata['partition_id'].nunique() == 8, 'La muestra no contiene los ocho estratos esperados.'
assert abs(n_M - TARGET_N) / TARGET_N < 0.03, 'El tamaño muestral se aleja más de 3% del objetivo.'"""

clean_cell = base.cells[7]
clean_cell.source = source(clean_cell) + """

assert n_M_clean == n_M, 'La limpieza mínima eliminó registros; revisar campos críticos.'
assert M_clean.select('id').distinct().count() == n_M_clean, 'Los identificadores no son únicos.'"""

fold_md = base.cells[8]
fold_cell = base.cells[9]
fold_integrity = base.cells[10]
fold_integrity.source = source(fold_integrity) + """
assert int(fold_counts['count'].max() - fold_counts['count'].min()) <= 10, 'Los folds no están balanceados.'"""

features_md = new_markdown_cell(
    """## 3. Preparación de variables y control de fuga de información

Las variables predictoras describen permanencia, alcance y contexto del mercado. `rank` se excluye de manera explícita porque la etiqueta `rank_tier` se deriva directamente de esa variable; incluirla produciría fuga de información y métricas artificialmente altas. Las categorías se indexan dentro de un pipeline reproducible y las mismas transformaciones se utilizan en todos los experimentos."""
)

features_cell = base.cells[11]
features_cell.source = source(features_cell) + """

assert 'rank' not in feature_cols, 'Fuga de información: rank no puede ser predictor.'
assert set(feature_cols) == {
    'days_on_chart', 'max_days_on_chart', 'country_count_by_artist',
    'country_idx', 'tenure_idx', 'scope_idx'
}"""

tuning_md = new_markdown_cell(
    """## 4. Selección de métricas y ajuste de hiperparámetros

La configuración se selecciona con un fold fijo de validación (`fold 0`) y los cuatro folds restantes para entrenamiento. Se comparan cuatro combinaciones de `numTrees` y `maxDepth`. El criterio principal es AUC-ROC, porque mide separación entre clases a diferentes umbrales; F1 ponderado funciona como desempate. También se reportan accuracy, precisión y recall ponderados para evitar una lectura basada en una sola métrica."""
)

evaluation_helpers = new_code_cell(
    """evaluators = {
    'accuracy': MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='accuracy'),
    'f1_weighted': MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='f1'),
    'precision_weighted': MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='weightedPrecision'),
    'recall_weighted': MulticlassClassificationEvaluator(labelCol='label', predictionCol='prediction', metricName='weightedRecall'),
    'auc_roc': BinaryClassificationEvaluator(labelCol='label', rawPredictionCol='rawPrediction', metricName='areaUnderROC'),
}

def add_class_weights(train_df):
    label_counts = {row['label']: row['count'] for row in train_df.groupBy('label').count().collect()}
    n_tr = sum(label_counts.values())
    n_cls = len(label_counts)
    class_weight = {label: n_tr / (n_cls * count) for label, count in label_counts.items()}
    weight_expr = None
    for label, weight in class_weight.items():
        condition = F.col('label') == F.lit(label)
        weight_expr = F.when(condition, F.lit(weight)) if weight_expr is None else weight_expr.when(condition, F.lit(weight))
    return train_df.withColumn('weight', weight_expr.otherwise(F.lit(1.0))), class_weight

def evaluate_predictions(pred_df):
    return {name: evaluator.evaluate(pred_df) for name, evaluator in evaluators.items()}

def compute_confusion(pred_df, fold_id):
    return (
        pred_df.groupBy('label', 'prediction').count()
        .withColumn('fold_id', F.lit(fold_id))
        .toPandas()
    )"""
)

tuning_code = new_code_cell(
    """tune_train = M_features.filter(F.col('fold_id') != 0).cache()
tune_valid = M_features.filter(F.col('fold_id') == 0).cache()
tune_train_w, tuning_weights = add_class_weights(tune_train)
tune_train_w = tune_train_w.cache()

tuning_rows = []
for params in HYPERPARAMETERS:
    print(f"Probando numTrees={params['numTrees']}, maxDepth={params['maxDepth']}")
    candidate = RandomForestClassifier(
        featuresCol='features',
        labelCol='label',
        weightCol='weight',
        numTrees=params['numTrees'],
        maxDepth=params['maxDepth'],
        maxBins=128,
        seed=SEED,
    )
    candidate_model = candidate.fit(tune_train_w)
    candidate_pred = candidate_model.transform(tune_valid).cache()
    row = {**params, **evaluate_predictions(candidate_pred)}
    tuning_rows.append(row)
    print({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()})
    candidate_pred.unpersist()

tuning_results = pd.DataFrame(tuning_rows).sort_values(
    ['auc_roc', 'f1_weighted', 'numTrees', 'maxDepth'],
    ascending=[False, False, True, True],
).reset_index(drop=True)
best_params = {
    'numTrees': int(tuning_results.iloc[0]['numTrees']),
    'maxDepth': int(tuning_results.iloc[0]['maxDepth']),
}
print('\\nResultados del ajuste:')
print(tuning_results.round(4).to_string(index=False))
print('\\nConfiguración seleccionada:', best_params)

tune_train_w.unpersist()
tune_train.unpersist()
tune_valid.unpersist()"""
)

cv_md = new_markdown_cell(
    """## 5. Experimentación con validación cruzada

La configuración seleccionada se entrena cinco veces. En cada iteración, cuatro folds forman el entrenamiento y el fold restante funciona como prueba. Los pesos de clase se recalculan en cada entrenamiento. Se conservan métricas, probabilidades, matrices de confusión e importancia de variables para medir desempeño y variabilidad."""
)

old_experiment = source(base.cells[13])
loop_start = old_experiment.index("fold_metric_rows = []")
cv_code_text = old_experiment[loop_start:]
cv_code_text = cv_code_text.replace("numTrees=100,", "numTrees=best_params['numTrees'],")
cv_code_text = cv_code_text.replace("maxDepth=8,", "maxDepth=best_params['maxDepth'],")
cv_code_text = cv_code_text.replace(
    "fold_metric_rows = []\n",
    "fold_metric_rows = []\nbaseline_metric_rows = []\n",
)
cv_code_text = cv_code_text.replace(
    "train_w, class_weight = add_class_weights(train_df)\n    train_w = train_w.cache()\n",
    """train_w, class_weight = add_class_weights(train_df)
    train_w = train_w.cache()

    majority_label = train_df.groupBy('label').count().orderBy(F.desc('count')).first()['label']
    baseline_pred = test_df.withColumn('prediction', F.lit(float(majority_label)))
    baseline_metrics = {
        name: evaluator.evaluate(baseline_pred)
        for name, evaluator in evaluators.items()
        if name != 'auc_roc'
    }
    baseline_metrics.update({
        'auc_roc': 0.5,
        'fold_id': fold_id,
        'majority_label': float(majority_label),
    })
    baseline_metric_rows.append(baseline_metrics)
""",
)
cv_code_text = cv_code_text.replace(
    "feature_importance_all = pd.DataFrame(feature_importance_rows)\n",
    """feature_importance_all = pd.DataFrame(feature_importance_rows)
baseline_metrics = pd.DataFrame(baseline_metric_rows).sort_values('fold_id')

oof_confusion = (
    confusion_all.groupby(['label', 'prediction'], as_index=False)['count'].sum()
)
per_class_rows = []
for label, class_name in label_names.items():
    tp = int(oof_confusion.loc[
        (oof_confusion['label'] == label) & (oof_confusion['prediction'] == label),
        'count',
    ].sum())
    fp = int(oof_confusion.loc[
        (oof_confusion['label'] != label) & (oof_confusion['prediction'] == label),
        'count',
    ].sum())
    fn = int(oof_confusion.loc[
        (oof_confusion['label'] == label) & (oof_confusion['prediction'] != label),
        'count',
    ].sum())
    support = tp + fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / support if support else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    per_class_rows.append({
        'label': float(label),
        'class': class_name,
        'support': support,
        'precision': precision,
        'recall': recall,
        'f1': f1,
    })
per_class_metrics = pd.DataFrame(per_class_rows).sort_values('label')
""",
)
cv_code_text = cv_code_text.replace(
    "print(cv_metrics[['fold_id', 'n_train', 'n_test', *metric_cols]].round(4).to_string(index=False))",
    """print(cv_metrics[['fold_id', 'n_train', 'n_test', *metric_cols]].round(4).to_string(index=False))
print('\\nLínea base mayoritaria por fold:')
print(baseline_metrics[['fold_id', 'majority_label', *metric_cols]].round(4).to_string(index=False))
print('\\nMétricas out-of-fold por clase:')
print(per_class_metrics.round(4).to_string(index=False))""",
)
cv_code = new_code_cell(cv_code_text)

summary_code = base.cells[14]
summary_code.source = source(summary_code) + """

baseline_summary = (
    baseline_metrics[metric_cols]
    .agg(['mean', 'std'])
    .T.reset_index()
    .rename(columns={'index': 'metric', 'mean': 'baseline_mean', 'std': 'baseline_std'})
)
model_summary_precise = (
    cv_metrics[metric_cols]
    .agg(['mean', 'std', 'min', 'max'])
    .T.reset_index()
    .rename(columns={'index': 'metric'})
)
model_vs_baseline = model_summary_precise.merge(baseline_summary, on='metric')
model_vs_baseline['delta_model_minus_baseline'] = (
    model_vs_baseline['mean'] - model_vs_baseline['baseline_mean']
)
print('\\nComparación Random Forest contra línea base mayoritaria:')
print(model_vs_baseline[
    ['metric', 'mean', 'baseline_mean', 'delta_model_minus_baseline']
].round(4).to_string(index=False))

print(
    f"\\nFold oficial con mejor generalización: {best_fold} "
    "(criterio único: mayor AUC-ROC; F1 ponderado como desempate)."
)"""
results_md = base.cells[15]

plot_metrics = base.cells[16]
plot_metrics.source = source(plot_metrics).replace(
    "plt.tight_layout()\nplt.show()",
    "plt.tight_layout()\nfig.savefig(ASSET_DIR / '01_metricas_por_fold.png', bbox_inches='tight')\nplt.show()",
)

plot_variability = base.cells[17]
plot_variability.source = source(plot_variability).replace(
    "plt.tight_layout()\nplt.show()",
    "plt.tight_layout()\nfig.savefig(ASSET_DIR / '02_variabilidad_metricas.png', bbox_inches='tight')\nplt.show()",
)

plot_roc = base.cells[18]
plot_roc.source = source(plot_roc).replace(
    "plt.tight_layout()\nplt.show()",
    "plt.tight_layout()\nfig.savefig(ASSET_DIR / '03_curvas_roc.png', bbox_inches='tight')\nplt.show()",
)

plot_confusion = base.cells[19]
plot_confusion.source = source(plot_confusion).replace(
    "plt.tight_layout()\nplt.show()",
    "plt.tight_layout()\nfig.savefig(ASSET_DIR / '04_matriz_confusion.png', bbox_inches='tight')\nplt.show()",
)

plot_importance = base.cells[20]
plot_importance.source = source(plot_importance).replace(
    "plt.tight_layout()\nplt.show()",
    "plt.tight_layout()\nfig.savefig(ASSET_DIR / '05_importancia_variables.png', bbox_inches='tight')\nplt.show()",
)

plot_classes = base.cells[21]
plot_classes.source = source(plot_classes).replace(
    "plt.tight_layout()\nplt.show()",
    "plt.tight_layout()\nfig.savefig(ASSET_DIR / '06_distribucion_clases_folds.png', bbox_inches='tight')\nplt.show()",
)

kmeans_md = new_markdown_cell(
    """## 6. Modelo complementario no supervisado

`KMeans` no intenta predecir la etiqueta. Su función es explorar si permanencia, alcance y posición forman perfiles naturales. Las variables numéricas se estandarizan para evitar que una escala domine la distancia. Se comparan valores de `k` entre 2 y 6; Silhouette es el criterio principal y la inertia se reporta como apoyo. A diferencia del modelo supervisado, aquí `rank` sí puede emplearse porque no se está prediciendo `rank_tier`."""
)

kmeans_prepare = new_code_cell(
    """numeric_cols = ['days_on_chart', 'max_days_on_chart', 'country_count_by_artist', 'rank']
unsup_assembler = VectorAssembler(inputCols=numeric_cols, outputCol='raw_features')
scaler = StandardScaler(inputCol='raw_features', outputCol='features_scaled', withMean=True, withStd=True)
unsup_pipeline = Pipeline(stages=[unsup_assembler, scaler])
unsup_model = unsup_pipeline.fit(M_clean)
M_scaled = (
    unsup_model.transform(M_clean)
    .select('features_scaled', 'partition_id', *numeric_cols)
    .cache()
)
print(f'Registros para KMeans: {M_scaled.count():,}')"""
)

kmeans_search = new_code_cell(
    """cluster_evaluator = ClusteringEvaluator(
    featuresCol='features_scaled',
    metricName='silhouette',
    distanceMeasure='squaredEuclidean',
)
cluster_rows = []
for k in range(2, 7):
    km = KMeans(featuresCol='features_scaled', k=k, seed=SEED, maxIter=30)
    model_k = km.fit(M_scaled)
    pred_k = model_k.transform(M_scaled)
    cluster_rows.append({
        'k': k,
        'inertia': float(model_k.summary.trainingCost),
        'silhouette': float(cluster_evaluator.evaluate(pred_k)),
    })

k_results = pd.DataFrame(cluster_rows)
best_k = int(k_results.loc[k_results['silhouette'].idxmax(), 'k'])
print(k_results.round(4).to_string(index=False))
print(f'k seleccionado por Silhouette: {best_k}')

fig, axes = plt.subplots(1, 2, figsize=(10, 4))
sns.lineplot(data=k_results, x='k', y='inertia', marker='o', ax=axes[0])
axes[0].set_title('Inertia por k')
axes[0].set_xlabel('k')
axes[0].set_ylabel('Training cost')
sns.lineplot(data=k_results, x='k', y='silhouette', marker='o', ax=axes[1])
axes[1].set_title('Silhouette por k')
axes[1].set_xlabel('k')
axes[1].set_ylabel('Silhouette')
plt.tight_layout()
fig.savefig(ASSET_DIR / '07_seleccion_kmeans.png', bbox_inches='tight')
plt.show()"""
)

kmeans_final = new_code_cell(
    """kmeans_model = KMeans(
    featuresCol='features_scaled',
    k=best_k,
    seed=SEED,
    maxIter=50,
).fit(M_scaled)
clusters = kmeans_model.transform(M_scaled).cache()
silhouette_final = float(cluster_evaluator.evaluate(clusters))
inertia_final = float(kmeans_model.summary.trainingCost)

cluster_sizes = clusters.groupBy('prediction').count().orderBy('prediction').toPandas()
cluster_sizes['pct'] = cluster_sizes['count'] / cluster_sizes['count'].sum() * 100

scaler_model = unsup_model.stages[1]
means = scaler_model.mean.toArray()
stds = scaler_model.std.toArray()
centers_original = np.array(kmeans_model.clusterCenters()) * stds + means
centers_df = pd.DataFrame(centers_original, columns=numeric_cols)
centers_df.index.name = 'cluster'
centers_df = centers_df.reset_index().merge(
    cluster_sizes.rename(columns={'prediction': 'cluster'}),
    on='cluster',
)

cluster_partition = (
    clusters.groupBy('prediction', 'partition_id').count().toPandas()
    .pivot(index='prediction', columns='partition_id', values='count')
    .fillna(0).astype(int).sort_index()
)
cluster_partition_pct = cluster_partition.div(cluster_partition.sum(axis=1), axis=0) * 100

fig, ax = plt.subplots(figsize=(11, 4))
sns.heatmap(cluster_partition_pct, annot=True, fmt='.1f', cmap='YlGnBu', ax=ax, cbar_kws={'label': '% dentro del cluster'})
ax.set_title(f'Composición de clusters por estrato (k={best_k})')
ax.set_xlabel('Estrato')
ax.set_ylabel('Cluster')
plt.tight_layout()
fig.savefig(ASSET_DIR / '08_composicion_clusters.png', bbox_inches='tight')
plt.show()

print(f'Silhouette final: {silhouette_final:.4f}')
print(f'Inertia final: {inertia_final:,.0f}')
print('\\nTamaños de cluster:')
print(cluster_sizes.round(2).to_string(index=False))
print('\\nCentroides en escala original:')
print(centers_df.round(2).to_string(index=False))"""
)

discussion = new_markdown_cell(
    """## 7. Discusión, conclusiones y trabajo futuro

La construcción estratificada de `M` conserva los ocho perfiles definidos por antigüedad, alcance y visibilidad competitiva. La asignación cíclica dentro de cada estrato produce folds prácticamente iguales y evita que la evaluación dependa de una partición accidental. El control de fuga es central: `rank` se utiliza para construir la etiqueta, pero se excluye del bosque aleatorio.

El ajuste de hiperparámetros permite seleccionar una complejidad sustentada por resultados de validación. La lectura principal combina AUC-ROC, F1 ponderado y su desviación entre folds. Una desviación baja indica que el patrón aprendido es estable. La matriz de confusión muestra qué clase concentra los errores y la importancia de variables permite interpretar qué señales de trayectoria y alcance contribuyen a la clasificación.

La comparación contra la línea base mayoritaria es indispensable. Como la clase `Estable` domina la muestra, predecir siempre esa clase puede obtener una accuracy competitiva sin recuperar ningún caso `Top`. Por eso, si Random Forest sacrifica ligeramente accuracy pero mejora F1 y logra recall útil para `Top`, el resultado debe interpretarse como un intercambio deliberado entre desempeño global y recuperación de la clase minoritaria, no como una victoria en todas las métricas.

KMeans complementa la clasificación al descubrir perfiles sin usar etiquetas. Silhouette evalúa separación y cohesión, mientras que los centroides traducen cada cluster a escalas comprensibles. La coincidencia parcial entre clusters y estratos confirma que la estructura del mercado no depende de una sola variable, aunque las agrupaciones no deben interpretarse como segmentos causales.

### Limitaciones

- La tarea es explicativa y contemporánea; no constituye un pronóstico temporal.
- Los registros de un mismo artista pueden aparecer en distintos folds, por lo que la validación mide generalización entre observaciones, no necesariamente hacia artistas nunca vistos.
- País se codifica como categoría indexada; una representación futura podría incorporar región, tamaño de mercado o variables temporales.
- El muestreo reduce costo computacional, pero no sustituye una infraestructura distribuida cuando se desea entrenar sobre la población completa.

### Conclusiones

El proyecto demuestra un flujo reproducible de aprendizaje sobre millones de registros: auditoría, delimitación de población, muestreo representativo, preparación sin fuga, ajuste de hiperparámetros, validación cruzada, visualización e interpretación. El bosque aleatorio proporciona una separación útil entre observaciones `Top` y `Estable`, y la baja variabilidad entre folds permite juzgar su estabilidad. El análisis no supervisado añade una lectura complementaria de perfiles de permanencia y alcance.

### Trabajo futuro

Se recomienda implementar una división temporal, agrupar folds por artista para medir generalización a entidades no vistas, comparar con Gradient-Boosted Trees o regresión logística, y agregar variables históricas que sólo utilicen información disponible antes de cada fecha."""
)

exports = new_code_cell(
    """REPORT_DIR.mkdir(exist_ok=True)
ASSET_DIR.mkdir(exist_ok=True)

strata_compare.to_csv(REPORT_DIR / 'tabla_estratos.csv', index=False)
fold_counts.to_csv(REPORT_DIR / 'tabla_folds.csv', index=False)
tuning_results.to_csv(REPORT_DIR / 'tabla_hiperparametros.csv', index=False)
cv_metrics.to_csv(REPORT_DIR / 'tabla_metricas_folds.csv', index=False)
baseline_metrics.to_csv(REPORT_DIR / 'tabla_linea_base_folds.csv', index=False)
model_vs_baseline.to_csv(REPORT_DIR / 'tabla_modelo_vs_linea_base.csv', index=False)
per_class_metrics.to_csv(REPORT_DIR / 'tabla_metricas_por_clase.csv', index=False)
summary_stats.to_csv(REPORT_DIR / 'tabla_resumen_metricas.csv', index=False)
best_confusion.to_csv(REPORT_DIR / 'tabla_matriz_confusion.csv')
feature_importance_summary.to_csv(REPORT_DIR / 'tabla_importancia_variables.csv', index=False)
k_results.to_csv(REPORT_DIR / 'tabla_kmeans.csv', index=False)
cluster_sizes.to_csv(REPORT_DIR / 'tabla_tamanos_clusters.csv', index=False)
centers_df.to_csv(REPORT_DIR / 'tabla_centroides_clusters.csv', index=False)

final_metrics = {
    'dataset': {
        'original_records': int(n_original),
        'date_min': str(date_bounds.min_date),
        'date_max': str(date_bounds.max_date),
        'filtered_records': int(n_total),
        'excluded_country': 'VE',
        'evaluation_start': '2022-10-21',
    },
    'sample': {
        'target': TARGET_N,
        'actual': int(n_M),
        'clean': int(n_M_clean),
        'strata': int(strata_pd['partition_id'].nunique()),
        'max_population_sample_difference_pct': float(strata_compare['abs_diff_pct'].max()),
    },
    'folds': {
        'count': K_FOLDS,
        'minimum_size': int(fold_counts['count'].min()),
        'maximum_size': int(fold_counts['count'].max()),
    },
    'random_forest': {
        'selected_numTrees': int(best_params['numTrees']),
        'selected_maxDepth': int(best_params['maxDepth']),
        'best_fold': int(best_fold),
        'best_fold_selection_rule': 'AUC-ROC descending, weighted F1 descending as tie-breaker',
        'metrics_mean': {m: float(cv_metrics[m].mean()) for m in metric_cols},
        'metrics_std': {m: float(cv_metrics[m].std(ddof=1)) for m in metric_cols},
        'baseline_mean': {m: float(baseline_metrics[m].mean()) for m in metric_cols},
        'model_minus_baseline': {
            m: float(cv_metrics[m].mean() - baseline_metrics[m].mean())
            for m in metric_cols
        },
        'per_class': {
            row['class']: {
                'support': int(row['support']),
                'precision': float(row['precision']),
                'recall': float(row['recall']),
                'f1': float(row['f1']),
            }
            for row in per_class_rows
        },
    },
    'kmeans': {
        'best_k': int(best_k),
        'silhouette': silhouette_final,
        'inertia': inertia_final,
    },
    'integrity': {
        'all_eight_strata': bool(strata_pd['partition_id'].nunique() == 8 and sample_strata['partition_id'].nunique() == 8),
        'five_balanced_folds': bool(int(fold_counts['count'].max() - fold_counts['count'].min()) <= 10),
        'unique_ids': bool(M_clean.select('id').distinct().count() == n_M_clean),
        'rank_excluded_from_supervised_features': bool('rank' not in feature_cols),
    },
}

with open(REPORT_DIR / 'final_metrics.json', 'w', encoding='utf-8') as handle:
    json.dump(final_metrics, handle, ensure_ascii=False, indent=2)

print(json.dumps(final_metrics, ensure_ascii=False, indent=2))"""
)

rubric = new_markdown_cell(
    """## 8. Reproducibilidad y comprobación de la rúbrica

### Reproducción

1. Colocar `charts_artists_daily.csv` dentro de `spotify_project/raw/`.
2. Usar Java 17 y el kernel `pyspark-notebook`.
3. Ejecutar el notebook completo desde la raíz del proyecto.
4. Verificar que `report/final_metrics.json`, las tablas CSV y las ocho figuras sean generadas.

Comando utilizado:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
jupyter nbconvert --to notebook --execute --inplace \
notebooks/ProyectoFinal_Equipo51.ipynb \
--ExecutePreprocessor.kernel_name=pyspark-notebook \
--ExecutePreprocessor.timeout=3600
```

### Evidencia de cumplimiento

| Requisito | Evidencia |
|---|---|
| Lectura del dataset original | Sección 1, esquema y auditoría |
| Caracterización y muestra | Sección 2, ocho estratos y comparación P vs M |
| Preparación de datos | Sección 3, pipeline y exclusión de `rank` |
| Métricas e hiperparámetros | Sección 4, cuatro configuraciones comparadas |
| Modelos de aprendizaje | Secciones 5 y 6, Random Forest y KMeans |
| Experimentación y resultados | Cinco folds, métricas, ROC, matriz de confusión y clustering |
| Discusión y conclusiones | Sección 7 |
| Código documentado y organizado | Secciones numeradas, assertions y exportación reproducible |"""
)

stop = new_code_cell("M_scaled.unpersist()\nclusters.unpersist()\nspark.stop()\nprint('Ejecución finalizada correctamente.')")

cells = [
    title,
    imports,
    setup,
    audit_md,
    raw_cell,
    population_md,
    population_cell,
    strata_cell,
    clean_cell,
    fold_md,
    fold_cell,
    fold_integrity,
    features_md,
    features_cell,
    tuning_md,
    evaluation_helpers,
    tuning_code,
    cv_md,
    cv_code,
    summary_code,
    results_md,
    plot_metrics,
    plot_variability,
    plot_roc,
    plot_confusion,
    plot_importance,
    plot_classes,
    kmeans_md,
    kmeans_prepare,
    kmeans_search,
    kmeans_final,
    discussion,
    exports,
    rubric,
    stop,
]

notebook = new_notebook(cells=cells, metadata=base.metadata)
for cell in notebook.cells:
    if cell.cell_type == "code":
        cell.execution_count = None
        cell.outputs = []

nbformat.write(notebook, OUTPUT)
print(f"Creado: {OUTPUT}")
