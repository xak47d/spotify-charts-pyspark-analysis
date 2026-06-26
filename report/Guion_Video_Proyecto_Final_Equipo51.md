# Guion de video — Proyecto Final Equipo 51

**Duración objetivo:** 8 minutos 40 segundos
**Título:** Clasificación de la visibilidad competitiva de artistas en Spotify Charts mediante aprendizaje distribuido

## Diapositiva 1 — Presentación

**Tiempo:** 0:00–0:40

**En pantalla:** título, integrantes y una imagen representativa de Spotify Charts.

**Narración:**

Hola. Somos el Equipo 51, integrado por Fernando Arango Gaviria, Jose Luis Armenta Mandujano, Demenard Gardy Armand y Ricardo Ismael Vega Aguilar. En este proyecto analizamos datos diarios de artistas en Spotify Charts mediante PySpark. Nuestro objetivo fue construir un proceso integral de aprendizaje aplicado a grandes volúmenes de datos y responder una pregunta concreta: ¿las características históricas y geográficas de una observación permiten distinguir si un artista se encuentra en la franja Top del chart o en una posición Estable?

## Diapositiva 2 — Problema y datos

**Tiempo:** 0:40–1:35

**En pantalla:** volumen original, cobertura temporal y unidad de análisis.

**Narración:**

Utilizamos el archivo `charts_artists_daily.csv`, perteneciente al conjunto Spotify Charts Daily Updated. La población original contiene 22 millones 711 mil 258 registros, con fechas entre octubre de 2021 y mayo de 2026. Cada fila representa una combinación de artista, país y fecha.

El procesamiento se realizó con PySpark porque el archivo tiene millones de observaciones y no resulta conveniente depender de un flujo completamente en memoria. Durante la auditoría revisamos el esquema, nulos, duplicados y cobertura temporal. Excluimos Venezuela debido a una anomalía de carga identificada en el análisis previo y comenzamos la ventana evaluable el 21 de octubre de 2022. Así obtuvimos una población de 17 millones 914 mil 239 registros con suficiente historial para distinguir artistas nuevos y veteranos.

## Diapositiva 3 — Caracterización y muestreo

**Tiempo:** 1:35–2:35

**En pantalla:** las tres variables de caracterización y los ocho estratos.

**Narración:**

Caracterizamos la población mediante tres variables. La primera fue antigüedad: un artista es Veterano si supera 365 días máximos en chart y Nuevo en caso contrario. La segunda fue alcance: un artista es Global si aparece en más de diez países y Local si aparece en diez o menos. La tercera fue visibilidad competitiva: Top corresponde a posiciones del 1 al 50 y Estable a posiciones del 51 al 200.

La combinación de estas categorías produce ocho estratos. Aplicamos muestreo aleatorio estratificado proporcional sin reemplazo, con un objetivo de 200 mil registros. La muestra resultante contiene 200 mil 33 observaciones y conserva los ocho estratos. La mayor diferencia entre las proporciones de población y muestra fue de sólo 0.1864 puntos porcentuales. Esto nos permitió reducir el costo computacional sin perder la estructura principal de la población.

## Diapositiva 4 — Preparación y prevención de fuga

**Tiempo:** 2:35–3:25

**En pantalla:** variables predictoras y una señal de exclusión sobre `rank`.

**Narración:**

La tarea supervisada consiste en clasificar cada observación como Top o Estable. Utilizamos días actuales en chart, máximo histórico de días, número de países y variables categóricas de país, antigüedad y alcance.

Una decisión metodológica importante fue excluir `rank` de las variables predictoras. La etiqueta se construye precisamente a partir del ranking; por lo tanto, incluirlo produciría fuga de información y un desempeño artificialmente alto. Todas las transformaciones se organizaron en un pipeline reproducible. Además, calculamos pesos inversos por clase para que la categoría Estable, que es más frecuente, no dominara el entrenamiento.

## Diapositiva 5 — Ajuste del modelo

**Tiempo:** 3:25–4:15

**En pantalla:** tabla con las cuatro configuraciones de Random Forest.

**Narración:**

El modelo principal fue Random Forest. Comparamos cuatro configuraciones: 50 o 100 árboles, combinados con profundidad máxima de 6 u 8. Para esta selección utilizamos un fold fijo de validación. El criterio principal fue AUC-ROC y F1 ponderado funcionó como desempate.

La configuración seleccionada utilizó 100 árboles y profundidad máxima 8. Esta búsqueda fue deliberadamente compacta: queríamos justificar el nivel de complejidad sin realizar una exploración excesiva para el entorno local. Después de seleccionar la configuración, pasamos a una evaluación independiente mediante validación cruzada.

## Diapositiva 6 — Validación cruzada y resultados

**Tiempo:** 4:15–5:35

**En pantalla:** gráfica de métricas por fold y curvas ROC.

**Narración:**

Construimos cinco folds dentro de cada estrato. El fold menor tuvo 40 mil 4 registros y el mayor 40 mil 10, por lo que la distribución fue prácticamente uniforme. En cada iteración entrenamos con cuatro folds y probamos con el restante.

El modelo obtuvo una accuracy promedio de 0.7385, F1 ponderado de 0.7506, precisión ponderada de 0.7772 y AUC-ROC de 0.7881. La desviación estándar de AUC-ROC fue 0.0024 y la de F1 fue 0.0038.

La línea base que siempre predice Estable alcanzó una accuracy de 0.7448, ligeramente mayor que la del modelo. Sin embargo, su recall para Top es cero y su F1 ponderado es solamente 0.6359. Random Forest elevó ese F1 en 0.1147 y logró recuperar 68.5 por ciento de los casos Top.

La baja variabilidad muestra que el desempeño no depende de una sola partición favorable. Las curvas ROC de los cinco folds se encuentran muy próximas entre sí. El mejor fold es el 3 en todo el proyecto, con una regla única: mayor AUC-ROC y F1 como desempate. La matriz de confusión y las métricas por clase muestran precisión de 0.8752 para Estable y 0.4912 para Top. El F1 de Top es 0.5722, por lo que esa clase sigue siendo el principal espacio de mejora.

## Diapositiva 7 — Interpretación y KMeans

**Tiempo:** 5:35–6:40

**En pantalla:** importancia de variables, selección de k y centroides.

**Narración:**

Las variables con mayor importancia promedio fueron el máximo histórico de días en chart, el contexto del país y el número de países en los que aparece el artista. Esto sugiere que la trayectoria y el alcance contienen señales útiles para distinguir niveles de visibilidad. Sin embargo, la importancia del modelo no implica causalidad.

Como complemento utilizamos KMeans con variables numéricas estandarizadas. Comparamos valores de k entre 2 y 6 mediante inertia y Silhouette. El mejor resultado fue k igual a 2, con Silhouette de 0.4945. El cluster mayor reunió aproximadamente 72.5 por ciento de la muestra y mostró mayor permanencia y alcance; el segundo reunió 27.5 por ciento y presentó menor permanencia, menor alcance y un ranking promedio más bajo. Estos clusters son perfiles descriptivos, no segmentos causales.

## Diapositiva 8 — Limitaciones y trabajo futuro

**Tiempo:** 6:40–7:40

**En pantalla:** limitaciones a la izquierda y mejoras futuras a la derecha.

**Narración:**

El proyecto tiene varias limitaciones. Primero, la tarea es explicativa y contemporánea; no pronostica posiciones futuras. Segundo, un mismo artista puede aparecer en distintos folds, por lo que medimos generalización entre observaciones y no necesariamente hacia artistas nunca vistos. Tercero, el índice de país no representa cercanía regional o cultural. Finalmente, trabajar con una muestra reduce el costo, pero deja fuera parte de la población.

Como trabajo futuro proponemos una división temporal, folds agrupados por artista, comparación con Gradient-Boosted Trees o regresión logística y variables históricas calculadas únicamente con información anterior a cada fecha. También sería valioso ejecutar el flujo sobre infraestructura distribuida y la población completa.

## Diapositiva 9 — Conclusiones

**Tiempo:** 7:40–8:40

**En pantalla:** diagrama del flujo completo y tres resultados destacados.

**Narración:**

En conclusión, el proyecto integró todas las etapas solicitadas: lectura, auditoría, caracterización, muestreo, preparación, ajuste, entrenamiento, validación, visualización y discusión. La muestra conservó los ocho estratos, los cinco folds estuvieron balanceados y se evitó la fuga de información al excluir el ranking.

Random Forest alcanzó un AUC-ROC promedio de 0.7881 y un F1 ponderado de 0.7506, con variabilidad baja entre experimentos. Aunque no superó la accuracy de la línea base mayoritaria, sí recuperó la clase Top y mejoró ampliamente el F1. KMeans añadió una lectura complementaria de perfiles de permanencia y alcance.

La aportación principal no es solamente una métrica, sino un proceso reproducible y documentado para aplicar aprendizaje automático a una población de gran volumen. Gracias por su atención.

## Lista de apoyo visual

- Portada del reporte.
- Tabla de variables y ocho estratos.
- Comparación población contra muestra.
- Tabla de hiperparámetros.
- Métricas por fold.
- Curvas ROC.
- Matriz de confusión.
- Importancia de variables.
- Gráfica de selección de KMeans.
- Diagrama final del flujo metodológico.
