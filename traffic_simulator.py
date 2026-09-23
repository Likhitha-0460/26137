"""
Loads REAL Bengaluru traffic data (Kaggle: "Bangalore's Traffic Pulse",
CC0 license) and uses it to drive congestion on the OSM road graph.

Why this design:
- The dataset is road/area-named, not pre-matched to OSM edge IDs. So we
  build a lookup: normalized road name -> list of historical congestion
  readings for that road (across different dates/times in the dataset).
- Every refresh cycle, each OSM edge whose street name matches a dataset
  road pulls a "fresh" reading by rotating through its historical samples
  (so the demo shows real, dataset-grounded variation over time rather
  than a single static number).
- Edges with NO name match (common — the dataset only covers major
  roads/intersections, not every minor residential street) fall back to
  the CITY-WIDE AVERAGE congestion from the dataset, not a random number.
  This keeps every value traceable to real data.
"""

import os
import re
import threading
import time
from collections import defaultdict

import pandas as pd

import config


def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/extra spaces, for fuzzy-ish matching."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Make column lookups resilient to spacing/punctuation differences
    between dataset versions (e.g. 'Road/Intersection Name' vs 'Road_Intersection_Name')."""
    df.columns = [
        re.sub(r"[^a-z0-9]", "_", c.strip().lower()) for c in df.columns
    ]
    return df


def _find_col(df, *keywords):
    """Find a column whose normalized name contains all given keywords."""
    for col in df.columns:
        if all(kw in col for kw in keywords):
            return col
    return None


class TrafficDatasetProvider:
    """
    Wraps the Bengaluru traffic CSV and exposes per-road congestion values.
    Falls back gracefully to a city-wide average if the CSV is missing,
    so the app still runs (with a loud warning) if someone forgets to
    download the dataset.
    """

    def __init__(self, csv_path: str):
        self.available = False
        self.road_samples = defaultdict(list)   # normalized_road_name -> [congestion values]
        self.city_avg_congestion = 1.6           # sane fallback multiplier if dataset missing
        self._load(csv_path)

    def _load(self, csv_path):
        if not os.path.exists(csv_path):
            print(
                f"[traffic_simulator] WARNING: dataset not found at '{csv_path}'. "
                f"Download 'Banglore_traffic_Dataset.csv' from Kaggle "
                f"(preethamgouda/banglore-city-traffic-dataset) and place it there. "
                f"Falling back to a flat average congestion multiplier for now."
            )
            return

        df = pd.read_csv(csv_path)
        df = _normalize_columns(df)

        road_col = _find_col(df, "road") or _find_col(df, "intersection")
        congestion_col = _find_col(df, "congestion")

        if road_col is None or congestion_col is None:
            print(
                "[traffic_simulator] WARNING: could not find expected road/congestion "
                "columns in the CSV. Check backend/data/README.md for expected schema. "
                "Falling back to flat average congestion."
            )
            return

        # Normalize congestion values onto a 1.0 (free flow) - 3.0 (heavy) multiplier scale,
        # regardless of whether the source column is 0-100, 0-10, or already a multiplier.
        raw = pd.to_numeric(df[congestion_col], errors="coerce").dropna()
        if raw.empty:
            print("[traffic_simulator] WARNING: congestion column had no numeric values.")
            return

        col_min, col_max = raw.min(), raw.max()
        span = max(col_max - col_min, 1e-6)

        def to_multiplier(v):
            scaled = (v - col_min) / span          # 0..1
            return round(1.0 + scaled * 2.0, 3)     # -> 1.0..3.0

        for _, row in df.iterrows():
            road_name = _normalize_name(str(row.get(road_col, "")))
            cval = row.get(congestion_col)
            if not road_name or pd.isna(cval):
                continue
            try:
                self.road_samples[road_name].append(to_multiplier(float(cval)))
            except (ValueError, TypeError):
                continue

        if self.road_samples:
            all_vals = [v for vals in self.road_samples.values() for v in vals]
            self.city_avg_congestion = round(sum(all_vals) / len(all_vals), 3)
            self.available = True
            print(
                f"[traffic_simulator] Loaded real Bengaluru traffic data: "
                f"{len(df)} rows, {len(self.road_samples)} distinct roads matched, "
                f"city-wide avg congestion multiplier = {self.city_avg_congestion}"
            )
        else:
            print("[traffic_simulator] WARNING: dataset parsed but no usable rows found.")

    def congestion_for_road(self, road_name: str, cycle_index: int) -> float:
        """Return a congestion multiplier for a given OSM road name, rotating
        through that road's real historical samples over time for variation."""
        if not self.available:
            return self.city_avg_congestion

        key = _normalize_name(road_name)
        samples = self.road_samples.get(key)
        if not samples:
            return self.city_avg_congestion

        return samples[cycle_index % len(samples)]


class TrafficSimulator:
    """
    Applies dataset-driven congestion onto the road graph, refreshed on an
    interval so route costs change over time the way they would in a real
    dynamic-routing deployment (later swappable for a live feed).
    """

    def __init__(self, graph, dataset_path: str = None):
        self.graph = graph
        self.provider = TrafficDatasetProvider(dataset_path or config.TRAFFIC_DATASET_PATH)
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._cycle_index = 0
        self.version = 0

    def _apply_dataset_congestion_once(self):
        with self._lock:
            for u, v, k, data in self.graph.edges(keys=True, data=True):
                osm_name = data.get("name", "")
                if isinstance(osm_name, list):  # OSM sometimes gives multiple names per edge
                    osm_name = osm_name[0] if osm_name else ""
                congestion = self.provider.congestion_for_road(
                    osm_name, self._cycle_index
                )
                data["dataset_congestion"] = congestion
                data["congestion"] = congestion
            self._cycle_index += 1
            self.version += 1

    def start_background_updates(self):
        if self._running:
            return
        self._running = True
        self._apply_dataset_congestion_once()  # apply immediately, don't wait for first sleep

        def loop():
            while self._running:
                time.sleep(config.TRAFFIC_UPDATE_INTERVAL_SEC)
                self._apply_dataset_congestion_once()

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        print("[traffic_simulator] Background dataset-driven congestion updates started.")

    def stop(self):
        self._running = False

    def snapshot_congestion(self):
        with self._lock:
            return {
                (u, v, k): data["congestion"]
                for u, v, k, data in self.graph.edges(keys=True, data=True)
            }

    def dataset_available(self):
        return self.provider.available