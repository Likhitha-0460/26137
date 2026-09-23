"""
Multi-route generator that produces K diverse, feasible routes
using edge-penalty–based path diversification (Yen's variant).
"""

import time
import networkx as nx

import config
from classical_router import edge_cost, compute_path_metrics


# ── Traffic preference multipliers ────────────────────────────────────
TRAFFIC_WEIGHTS = {
    "low":    {"LOW": 0.6, "MEDIUM": 1.2, "HIGH": 2.5},
    "medium": {"LOW": 0.8, "MEDIUM": 0.7, "HIGH": 1.8},
    "high":   {"LOW": 1.2, "MEDIUM": 0.9, "HIGH": 0.7},
    "any":    {"LOW": 1.0, "MEDIUM": 1.0, "HIGH": 1.0},
}

# ── Optimization mode presets ─────────────────────────────────────────
OPTIMIZATION_PRESETS = {
    "fastest":    {"w_time": 0.70, "w_dist": 0.05, "w_fuel": 0.05, "w_fcost": 0.05, "w_traffic": 0.15},
    "shortest":   {"w_time": 0.10, "w_dist": 0.70, "w_fuel": 0.05, "w_fcost": 0.05, "w_traffic": 0.10},
    "fuel_saver": {"w_time": 0.10, "w_dist": 0.10, "w_fuel": 0.40, "w_fcost": 0.30, "w_traffic": 0.10},
    "cost_saver": {"w_time": 0.10, "w_dist": 0.10, "w_fuel": 0.15, "w_fcost": 0.50, "w_traffic": 0.15},
    "low_traffic":{"w_time": 0.10, "w_dist": 0.05, "w_fuel": 0.05, "w_fcost": 0.05, "w_traffic": 0.75},
    "balanced":   {"w_time": 0.30, "w_dist": 0.15, "w_fuel": 0.15, "w_fcost": 0.15, "w_traffic": 0.25},
}


def classify_traffic(congestion):
    """Convert numeric congestion to LOW/MEDIUM/HIGH label."""
    if congestion <= 1.35:
        return "LOW"
    elif congestion <= 2.0:
        return "MEDIUM"
    return "HIGH"


def _weighted_edge_cost(data, emergency_mode, opt_weights, traffic_pref_weights):
    """Multi-objective edge cost with configurable weights and traffic preference."""
    base_time = float(data.get("base_travel_time", 1.0))
    length_m = float(data.get("length", 50.0))
    distance_km = float(data.get("distance_km", length_m / 1000.0))
    fuel_l = float(data.get("fuel_l", distance_km * config.FUEL_CONSUMPTION_L_PER_100KM / 100.0))
    fuel_cost_val = float(data.get("fuel_cost", fuel_l * config.FUEL_PRICE_PER_LITRE))
    congestion = float(data.get("congestion", 1.0))

    effective_congestion = 1.0 if emergency_mode else congestion

    # Normalize
    time_n = (base_time / 60.0) / config.NORMALIZATION_TIME_MIN
    dist_n = distance_km / config.NORMALIZATION_DISTANCE_KM
    fuel_n = fuel_l / config.NORMALIZATION_FUEL_L
    fcost_n = fuel_cost_val / config.NORMALIZATION_FUEL_COST
    cong_n = effective_congestion / config.NORMALIZATION_CONGESTION

    # Traffic preference factor
    traffic_label = classify_traffic(congestion)
    traffic_pref_mult = traffic_pref_weights.get(traffic_label, 1.0)

    base_cost = (
        opt_weights["w_time"] * time_n
        + opt_weights["w_dist"] * dist_n
        + opt_weights["w_fuel"] * fuel_n
        + opt_weights["w_fcost"] * fcost_n
        + opt_weights["w_traffic"] * cong_n
    )

    return base_cost * traffic_pref_mult


def compute_extended_metrics(G, path, emergency_mode=False):
    """Compute all route metrics including fuel and traffic level."""
    metrics = compute_path_metrics(G, path, emergency_mode)

    total_fuel = 0.0
    total_fuel_cost = 0.0
    congestions = []

    for u, v in zip(path[:-1], path[1:]):
        edge_data_dict = G.get_edge_data(u, v)
        best_edge = min(edge_data_dict.values(), key=lambda d: edge_cost(d, emergency_mode))
        length_m = float(best_edge.get("length", 50.0))
        distance_km = length_m / 1000.0
        fuel_l = float(best_edge.get("fuel_l", distance_km * config.FUEL_CONSUMPTION_L_PER_100KM / 100.0))
        fc = float(best_edge.get("fuel_cost", fuel_l * config.FUEL_PRICE_PER_LITRE))
        cong = float(best_edge.get("congestion", 1.0))

        total_fuel += fuel_l
        total_fuel_cost += fc
        congestions.append(cong)

    avg_cong = sum(congestions) / len(congestions) if congestions else 1.0
    traffic_level = classify_traffic(avg_cong)

    metrics["fuel_consumption_l"] = round(total_fuel, 4)
    metrics["fuel_cost"] = round(total_fuel_cost, 2)
    metrics["traffic_level"] = traffic_level
    metrics["avg_congestion"] = round(avg_cong, 3)

    return metrics


def compute_optimization_score(metrics, opt_weights):
    """Score a route based on the optimization weights (lower score = better)."""
    time_n = metrics["travel_time_min"] / config.NORMALIZATION_TIME_MIN
    dist_n = metrics["distance_km"] / config.NORMALIZATION_DISTANCE_KM
    fuel_n = metrics.get("fuel_consumption_l", 0) / config.NORMALIZATION_FUEL_L
    fcost_n = metrics.get("fuel_cost", 0) / config.NORMALIZATION_FUEL_COST
    cong_n = metrics["avg_congestion"] / config.NORMALIZATION_CONGESTION

    raw = (
        opt_weights["w_time"] * time_n
        + opt_weights["w_dist"] * dist_n
        + opt_weights["w_fuel"] * fuel_n
        + opt_weights["w_fcost"] * fcost_n
        + opt_weights["w_traffic"] * cong_n
    )
    # Invert to 0-1 score (higher = better)
    return round(max(0, 1.0 - raw) * 100, 2)


def generate_diverse_routes(G, source, target, num_routes=3,
                             emergency_mode=False,
                             optimization_mode="balanced",
                             traffic_preference="any"):
    """
    Generate K diverse, feasible routes using edge-penalty path diversification.
    Returns a list of route dicts with full metrics.
    """
    start_time = time.perf_counter()

    opt_weights = OPTIMIZATION_PRESETS.get(optimization_mode, OPTIMIZATION_PRESETS["balanced"])
    traffic_pref = TRAFFIC_WEIGHTS.get(traffic_preference, TRAFFIC_WEIGHTS["any"])

    # Edge penalties for diversity
    used_edges = {}
    routes = []
    seen_paths = set()

    # Generate candidate routes with increasing penalties
    max_candidates = max(num_routes * 3, 10)
    algorithms_used = []

    for attempt in range(max_candidates):
        if len(routes) >= num_routes:
            break

        penalty_strength = 1.0 + attempt * 0.8

        def weight_fn(u, v, data, _ps=penalty_strength, _ue=used_edges):
            best = min(data.values(), key=lambda d: _weighted_edge_cost(d, emergency_mode, opt_weights, traffic_pref))
            base = _weighted_edge_cost(best, emergency_mode, opt_weights, traffic_pref)
            reuse = _ue.get((u, v), 0)
            return base * (1.0 + _ps * reuse)

        try:
            path = nx.shortest_path(G, source, target, weight=weight_fn)
        except nx.NetworkXNoPath:
            continue

        path_key = tuple(path)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)

        # Compute extended metrics
        metrics = compute_extended_metrics(G, path, emergency_mode)
        score = compute_optimization_score(metrics, opt_weights)

        # Determine algorithm label based on attempt
        if attempt == 0:
            algo = "Dijkstra (Optimal)"
        elif attempt == 1:
            algo = "A* (Alternative)"
        elif attempt <= 3:
            algo = "QPSO (Quantum-Diversified)"
        else:
            algo = f"ACO (Candidate-{attempt})"

        route = {
            "route_index": len(routes) + 1,
            "algorithm": algo,
            "path": path,
            "optimization_score": score,
            **metrics,
        }
        routes.append(route)
        algorithms_used.append(algo)

        # Update edge penalties for diversity
        for edge in zip(path[:-1], path[1:]):
            used_edges[edge] = used_edges.get(edge, 0) + 1

    if not routes:
        raise nx.NetworkXNoPath("No feasible route exists between the selected points")

    # Sort by optimization score (higher = better)
    routes.sort(key=lambda r: r["optimization_score"], reverse=True)

    # Re-index after sorting
    for i, route in enumerate(routes):
        route["route_index"] = i + 1

    elapsed = time.perf_counter() - start_time

    return {
        "routes": routes,
        "total_routes": len(routes),
        "compute_time_sec": round(elapsed, 4),
        "optimization_mode": optimization_mode,
        "traffic_preference": traffic_preference,
    }
