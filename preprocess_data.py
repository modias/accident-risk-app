"""Build accident lookup table from US Accidents CSV."""

import argparse
import json
from pathlib import Path

import pandas as pd

from data_mappings import map_place, map_weather, visibility_bucket

DEFAULT_CSV = (
    "/Users/amodi/Documents/Skills:Project/US accident risk analysis/"
    "US_Accidents_March23.csv"
)
DATA_DIR = Path(__file__).parent / "data"
LOOKUP_PATH = DATA_DIR / "accident_lookup.parquet"
META_PATH = DATA_DIR / "baseline.json"

USE_COLS = [
    "Start_Time",
    "Visibility(mi)",
    "Weather_Condition",
    "Street",
    "Description",
    "Junction",
    "Traffic_Signal",
    "Amenity",
    "Severity",
]


def transform_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk.copy()
    chunk["hour"] = pd.to_datetime(chunk["Start_Time"], errors="coerce").dt.hour
    visibility = chunk["Visibility(mi)"].fillna(chunk["Visibility(mi)"].median())
    chunk["vis_bucket"] = visibility.apply(visibility_bucket)
    chunk["weather"] = chunk["Weather_Condition"].fillna("unknown").map(map_weather)
    chunk["place_type"] = chunk.apply(
        lambda row: map_place(
            row["Street"],
            row["Description"],
            bool(row["Junction"]),
            bool(row["Traffic_Signal"]),
            bool(row["Amenity"]),
        ),
        axis=1,
    )
    return chunk.dropna(subset=["hour"])


def aggregate_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        chunk.groupby(["hour", "vis_bucket", "place_type", "weather"], observed=True)
        .agg(
            accident_count=("Severity", "count"),
            severity_sum=("Severity", "sum"),
        )
        .reset_index()
    )
    return grouped


def merge_aggregates(frames: list[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(frames, ignore_index=True)
    lookup = (
        combined.groupby(["hour", "vis_bucket", "place_type", "weather"], observed=True)
        .agg(
            accident_count=("accident_count", "sum"),
            severity_sum=("severity_sum", "sum"),
        )
        .reset_index()
    )
    lookup["avg_severity"] = lookup["severity_sum"] / lookup["accident_count"]
    return lookup.drop(columns=["severity_sum"])


def build_lookup(csv_path: str, chunk_size: int = 500_000) -> tuple[pd.DataFrame, dict]:
    aggregates: list[pd.DataFrame] = []
    total_rows = 0
    total_severity = 0.0

    print(f"Reading {csv_path} in chunks of {chunk_size:,}...")
    for i, chunk in enumerate(
        pd.read_csv(csv_path, usecols=USE_COLS, chunksize=chunk_size, low_memory=False)
    ):
        total_rows += len(chunk)
        total_severity += chunk["Severity"].sum()
        transformed = transform_chunk(chunk)
        aggregates.append(aggregate_chunk(transformed))
        print(f"  chunk {i + 1}: {total_rows:,} rows processed")

    lookup = merge_aggregates(aggregates)
    baseline = {
        "total_accidents": int(total_rows),
        "avg_severity": round(total_severity / total_rows, 3),
        "max_bucket_count": int(lookup["accident_count"].max()),
    }
    return lookup, baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build accident risk lookup table")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to US Accidents CSV")
    parser.add_argument("--chunk-size", type=int, default=500_000)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lookup, baseline = build_lookup(args.csv, args.chunk_size)

    lookup.to_parquet(LOOKUP_PATH, index=False)
    META_PATH.write_text(json.dumps(baseline, indent=2))

    print(f"\nSaved lookup ({len(lookup):,} buckets) -> {LOOKUP_PATH}")
    print(f"Saved baseline -> {META_PATH}")
    print(f"Total accidents: {baseline['total_accidents']:,}")
    print(f"Average severity: {baseline['avg_severity']}")


if __name__ == "__main__":
    main()
