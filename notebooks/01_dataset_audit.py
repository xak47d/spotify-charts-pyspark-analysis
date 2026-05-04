# %%
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    ShortType,
)


# %%
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "raw"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_FILES = {
    "charts_songs_daily": "charts_songs_daily.csv.gz",
    "charts_artists_daily": "charts_artists_daily.csv.gz",
    "charts_albums_weekly": "charts_albums_weekly.csv.gz",
    "songs": "songs.csv",
    "artists": "artists.csv",
    "albums": "albums.csv",
    "artwork": "artwork.csv",
    "links": "links.csv",
}


# %%
def build_spark() -> SparkSession:
    return (
        SparkSession.builder.master("local[*]")
        .appName("spotify-dataset-audit")
        .config("spark.sql.session.timeZone", "America/Mexico_City")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def available_files() -> dict[str, Path]:
    return {
        logical_name: RAW_DIR / filename
        for logical_name, filename in REQUIRED_FILES.items()
        if (RAW_DIR / filename).exists()
    }


def missing_files() -> dict[str, Path]:
    return {
        logical_name: RAW_DIR / filename
        for logical_name, filename in REQUIRED_FILES.items()
        if not (RAW_DIR / filename).exists()
    }


def read_csv(spark: SparkSession, file_path: Path) -> DataFrame:
    return (
        spark.read.option("header", True)
        .option("inferSchema", True)
        .option("multiLine", False)
        .csv(str(file_path))
    )


def numeric_columns(df: DataFrame) -> list[str]:
    numeric_types = (IntegerType, LongType, ShortType, FloatType, DoubleType)
    return [
        field.name for field in df.schema.fields if isinstance(field.dataType, numeric_types)
    ]


def profile_table(logical_name: str, file_path: Path, spark: SparkSession) -> DataFrame:
    df = read_csv(spark, file_path)

    print(f"\n===== {logical_name} =====")
    print(f"Path: {file_path}")
    print(f"Columns ({len(df.columns)}): {df.columns}")
    df.printSchema()

    row_count = df.count()
    print(f"Row count: {row_count}")

    null_metrics = []
    for column_name in df.columns:
        null_count = df.filter(F.col(column_name).isNull()).count()
        null_metrics.append((column_name, null_count))

    null_df = spark.createDataFrame(null_metrics, ["column_name", "null_count"])
    null_df = null_df.withColumn(
        "null_pct",
        F.when(F.lit(row_count) > 0, F.round(F.col("null_count") / F.lit(row_count) * 100, 4)).otherwise(F.lit(None)),
    )

    print("Top null counts:")
    null_df.orderBy(F.desc("null_count")).show(20, truncate=False)

    summary_rows = [
        (
            logical_name,
            file_path.name,
            str(file_path),
            row_count,
            len(df.columns),
        )
    ]
    summary_df = spark.createDataFrame(
        summary_rows,
        ["table_name", "file_name", "file_path", "row_count", "column_count"],
    )

    summary_df.write.mode("overwrite").parquet(str(OUTPUTS_DIR / f"{logical_name}_summary.parquet"))
    null_df.write.mode("overwrite").parquet(str(OUTPUTS_DIR / f"{logical_name}_nulls.parquet"))

    numeric_cols = numeric_columns(df)
    if numeric_cols:
        stats_df = df.select(numeric_cols).summary()
        print("Numeric summary:")
        stats_df.show(truncate=False)
        stats_df.write.mode("overwrite").parquet(str(OUTPUTS_DIR / f"{logical_name}_numeric_summary.parquet"))

    return summary_df


def print_file_status() -> None:
    present = available_files()
    missing = missing_files()

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Raw dir: {RAW_DIR}")
    print(f"Available files: {len(present)}")
    for logical_name, path in present.items():
        print(f"  OK  {logical_name:<22} -> {path.name}")

    if missing:
        print(f"\nMissing files: {len(missing)}")
        for logical_name, path in missing.items():
            print(f"  MISS {logical_name:<22} -> {path.name}")


def union_summaries(dataframes: Iterable[DataFrame]) -> DataFrame:
    iterator = iter(dataframes)
    first = next(iterator)
    result = first
    for df in iterator:
        result = result.unionByName(df)
    return result


# %%
print_file_status()


# %%
spark = build_spark()


# %%
present_files = available_files()

if not present_files:
    print(
        "No dataset files were found in spotify_project/raw. "
        "Place the Kaggle files there and rerun this script."
    )
else:
    summary_dfs = []
    for logical_name, file_path in present_files.items():
        summary_dfs.append(profile_table(logical_name, file_path, spark))

    combined_summary = union_summaries(summary_dfs)
    combined_summary.orderBy("table_name").show(truncate=False)
    combined_summary.write.mode("overwrite").parquet(str(OUTPUTS_DIR / "combined_table_summary.parquet"))


# %%
spark.stop()
