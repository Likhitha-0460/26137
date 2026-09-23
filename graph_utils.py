"""
Loads a real road network from OpenStreetMap using OSMnx and caches it locally.
The graph is a networkx.MultiDiGraph where each edge has 'length' (meters)
and we compute a base 'travel_time' using speed limits (or default speed).
"""

import os
import pickle
from importlib import import_module

import networkx as nx

try:
    ox = import_module("osmnx")
except ImportError as exc:
    raise ImportError(
        "OSMnx is required. Install it with: pip install osmnx"
    ) from exc

import config


DEFAULT_SPEED_KMH = 30.0  # fallback speed if OSM has no maxspeed tag


def _parse_speed_kmh(maxspeed):
    """OSM maxspeed tags are messy (lists, strings, units). Normalize to km/h."""
    if maxspeed is None:
        return DEFAULT_SPEED_KMH
    if isinstance(maxspeed, list):
        maxspeed = maxspeed[0]
    try:
        digits = "".join(c for c in str(maxspeed) if c.isdigit() or c == ".")
        return float(digits) if digits else DEFAULT_SPEED_KMH
    except ValueError:
        return DEFAULT_SPEED_KMH


def load_city_graph(force_refresh: bool = False) -> nx.MultiDiGraph:
    """Load graph from fast pickle cache if present, otherwise from GraphML/OSM."""
    if not force_refresh and os.path.exists(config.GRAPH_PKL_PATH):
        print(f"[graph_utils] Fast-loading pickled graph: {config.GRAPH_PKL_PATH}")
        with open(config.GRAPH_PKL_PATH, "rb") as f:
            G = pickle.load(f)
    elif not force_refresh and os.path.exists(config.GRAPH_CACHE_PATH):
        print(f"[graph_utils] Loading GraphML graph: {config.GRAPH_CACHE_PATH}")
        G = ox.load_graphml(config.GRAPH_CACHE_PATH)
        print(f"[graph_utils] Saving fast pickle cache to: {config.GRAPH_PKL_PATH}")
        with open(config.GRAPH_PKL_PATH, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        print(f"[graph_utils] Downloading OSM graph for: {config.CITY_NAME}")
        G = ox.graph_from_place(config.CITY_NAME, network_type=config.NETWORK_TYPE)
        ox.save_graphml(G, config.GRAPH_CACHE_PATH)

    if not force_refresh and G.graph.get("qroute_weights_ready"):
        print("[graph_utils] Weighted edge metadata already cached; skipping normalization.")
        return G

    # Normalize every road segment into a weighted edge. Keep ``length`` and
    # ``base_travel_time`` because existing routers and cached graphs use them.
    for u, v, k, data in G.edges(keys=True, data=True):
        length_m = float(data.get("length", 50.0))
        speed_kmh = _parse_speed_kmh(data.get("maxspeed"))
        speed_ms = speed_kmh * 1000.0 / 3600.0
        travel_time_sec = length_m / max(speed_ms, 1.0)
        distance_km = length_m / 1000.0
        fuel_l = distance_km * config.FUEL_CONSUMPTION_L_PER_100KM / 100.0
        fuel_cost = fuel_l * config.FUEL_PRICE_PER_LITRE
        time_cost = travel_time_sec / 60.0 * config.TIME_COST_PER_MINUTE

        data["length"] = length_m
        data["distance_m"] = length_m
        data["distance_km"] = round(distance_km, 6)
        data["speed_kmh"] = speed_kmh
        data["travel_time_sec"] = float(travel_time_sec)
        data["time_min"] = round(travel_time_sec / 60.0, 6)
        data["base_travel_time"] = float(travel_time_sec)
        data["fuel_l"] = round(fuel_l, 8)
        data["fuel_cost"] = round(fuel_cost, 4)
        data.setdefault("congestion", 1.0)
        data.setdefault("dataset_congestion", data["congestion"])
        data["cost"] = round(fuel_cost + time_cost, 4)

    G.graph["qroute_weights_ready"] = True
    with open(config.GRAPH_PKL_PATH, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[graph_utils] Graph ready: {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G


def nearest_node(G, lat, lon):
    """Find the graph node nearest a given lat/lon (for user-clicked map points)."""
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)
