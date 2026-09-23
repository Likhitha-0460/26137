import config
import networkx as nx
import time
import random


def edge_cost(data, emergency_mode: bool = False):
    """
    Multi-objective edge cost combining time, distance, fuel, fuel cost,
    and congestion for a weighted routing graph.
    """
    base_time = float(data.get("base_travel_time", 1.0))
    length_m = float(data.get("length", 50.0))
    distance_km = float(data.get("distance_km", length_m / 1000.0))
    fuel_l = float(data.get("fuel_l", distance_km * config.FUEL_CONSUMPTION_L_PER_100KM / 100.0))
    fuel_cost = float(data.get("fuel_cost", fuel_l * config.FUEL_PRICE_PER_LITRE))
    congestion = float(data.get("congestion", 1.0))

    effective_congestion = 1.0 if emergency_mode else congestion

    # Normalize each metric before applying weights. Traffic is read from the
    # live edge value so background simulator updates affect new searches.
    time_cost = (base_time / 60.0) / config.NORMALIZATION_TIME_MIN
    dist_cost = distance_km / config.NORMALIZATION_DISTANCE_KM
    fuel_cost_term = fuel_l / config.NORMALIZATION_FUEL_L
    fuel_price_cost = fuel_cost / config.NORMALIZATION_FUEL_COST
    congestion_cost = effective_congestion / config.NORMALIZATION_CONGESTION

    return (
        config.WEIGHT_TIME * time_cost
        + config.WEIGHT_DISTANCE * dist_cost
        + config.WEIGHT_FUEL * fuel_cost_term
        + config.WEIGHT_FUEL_COST * fuel_price_cost
        + config.WEIGHT_CONGESTION * congestion_cost
    )


def compute_path_metrics(G, path, emergency_mode: bool = False):
    total_cost = 0.0
    total_length_m = 0.0
    total_time_sec = 0.0
    total_fuel_l = 0.0
    total_operating_cost = 0.0
    weighted_speed = 0.0
    congestions = []

    for u, v in zip(path[:-1], path[1:]):
        edge_data_dict = G.get_edge_data(u, v)
        best_edge = min(edge_data_dict.values(), key=lambda d: edge_cost(d, emergency_mode))
        
        c = edge_cost(best_edge, emergency_mode)
        total_cost += c
        
        length = float(best_edge.get("length", 50.0))
        base_time = float(best_edge.get("base_travel_time", 1.0))
        fuel_l = float(best_edge.get("fuel_l", length / 1000.0 * config.FUEL_CONSUMPTION_L_PER_100KM / 100.0))
        edge_cost_value = float(best_edge.get("cost", 0.0))
        speed_kmh = float(best_edge.get("speed_kmh", 30.0))
        cong = float(best_edge.get("congestion", 1.0))
        
        if emergency_mode:
            eff_cong = 1.0
        else:
            eff_cong = cong
            
        total_length_m += length
        total_time_sec += base_time * eff_cong
        total_fuel_l += fuel_l
        total_operating_cost += edge_cost_value
        weighted_speed += speed_kmh * length
        congestions.append(cong)

    avg_cong = sum(congestions) / len(congestions) if congestions else 1.0

    return {
        "cost": round(total_cost, 2),
        "distance_km": round(total_length_m / 1000.0, 2),
        "travel_time_min": round(total_time_sec / 60.0, 1),
        "fuel_l": round(total_fuel_l, 3),
        "operating_cost": round(total_operating_cost, 2),
        "avg_speed_kmh": round(weighted_speed / max(total_length_m, 1.0), 1),
        "avg_congestion": round(avg_cong, 2),
        "congestion_cost": round(avg_cong * (total_length_m / 1000.0), 4),
        "constraint_penalty": 0.0,
    }


def dijkstra_route(G, source, target, emergency_mode: bool = False):
    start = time.perf_counter()
    path = nx.shortest_path(
        G, source, target,
        weight=lambda u, v, d: min(edge_cost(x, emergency_mode) for x in d.values())
    )
    elapsed = time.perf_counter() - start
    metrics = compute_path_metrics(G, path, emergency_mode)
    return {
        "algorithm": "Dijkstra (classical)",
        "path": path,
        "compute_time_sec": round(elapsed, 4),
        "time_complexity": "O((V + E) log V)",
        "congestion_avoidance_pct": 0.0,
        **metrics,
    }


def astar_route(G, source, target, emergency_mode: bool = False):
    def heuristic(u, v):
        (y1, x1) = (G.nodes[u]["y"], G.nodes[u]["x"])
        (y2, x2) = (G.nodes[v]["y"], G.nodes[v]["x"])
        return ((y1 - y2) ** 2 + (x1 - x2) ** 2) ** 0.5 * 1000

    start = time.perf_counter()
    path = nx.astar_path(
        G, source, target, heuristic=heuristic,
        weight=lambda u, v, d: min(edge_cost(x, emergency_mode) for x in d.values())
    )
    elapsed = time.perf_counter() - start
    metrics = compute_path_metrics(G, path, emergency_mode)
    return {
        "algorithm": "A* (classical)",
        "path": path,
        "compute_time_sec": round(elapsed, 4),
        "time_complexity": "O(E)",
        "congestion_avoidance_pct": 0.0,
        **metrics,
    }


def bpr_route(G, source, target, emergency_mode: bool = False):
    """Route using the Bureau of Public Roads travel-time formulation."""
    start = time.perf_counter()

    def weight(u, v, data):
        edge = min(data.values(), key=lambda item: edge_cost(item, emergency_mode))
        free_flow = float(edge.get("base_travel_time", 1.0))
        capacity_ratio = max(float(edge.get("congestion", 1.0)) - 1.0, 0.0) / 2.0
        # BPR: t = t0 * (1 + alpha * (volume/capacity)^beta).
        bpr_time = free_flow * (1.0 + 0.15 * capacity_ratio ** 4)
        return bpr_time + float(edge.get("length", 50.0)) / 100000.0

    path = nx.shortest_path(G, source, target, weight=weight)
    metrics = compute_path_metrics(G, path, emergency_mode)
    return {
        "algorithm": "BPR (congestion model)",
        "path": path,
        "compute_time_sec": round(time.perf_counter() - start, 4),
        "time_complexity": "O((V + E) log V)",
        "model": "t = t0 * (1 + 0.15 * (v/c)^4)",
        **metrics,
    }


def aco_route(G, source, target, emergency_mode=False, ants=6, iterations=4):
    """Bounded Ant Colony Optimization over the graph for responsive benchmarks."""
    start = time.perf_counter()
    pheromone = {}
    rng = random.Random(17)
    best_path = None
    best_metrics = None

    for iteration in range(iterations):
        for _ in range(ants):
            def weight(u, v, data):
                edge = min(data.values(), key=lambda item: edge_cost(item, emergency_mode))
                key = (u, v)
                exploration = 1.0 / max(pheromone.get(key, 0.0) + 1.0, 1.0)
                noise = 1.0 + rng.random() * 0.08
                return edge_cost(edge, emergency_mode) * (1.0 + exploration * 0.12) * noise

            try:
                path = nx.shortest_path(G, source, target, weight=weight)
            except nx.NetworkXNoPath:
                continue
            metrics = compute_path_metrics(G, path, emergency_mode)
            if best_metrics is None or metrics["cost"] < best_metrics["cost"]:
                best_path, best_metrics = path, metrics
            deposit = 1.0 / max(metrics["cost"], 0.001)
            for edge in zip(path[:-1], path[1:]):
                pheromone[edge] = pheromone.get(edge, 0.0) * 0.85 + deposit

    if best_path is None:
        raise nx.NetworkXNoPath("No ACO route exists")
    return {
        "algorithm": "ACO (Max-Min Ant System)",
        "path": best_path,
        "compute_time_sec": round(time.perf_counter() - start, 4),
        "time_complexity": "O(iterations × ants × (V + E) log V)",
        "ants": ants,
        "iterations": iterations,
        **best_metrics,
    }


def _edge_weight_for_route(G, emergency_mode, used_edges):
    """Build a weight function that discourages reusing already found roads."""
    def weight(u, v, data):
        edge = min(data.values(), key=lambda item: edge_cost(item, emergency_mode))
        reuse_count = used_edges.get((u, v), 0)
        return edge_cost(edge, emergency_mode) * (1.0 + 2.5 * reuse_count)

    return weight


def coordinated_fleet_routes(
    G,
    source,
    target,
    vehicle_count,
    max_time_minutes,
    emergency_mode=False,
):
    """Find diverse routes and assign them across a fleet sharing one trip."""
    vehicle_count = max(1, min(int(vehicle_count), 100))
    max_time_minutes = max(1.0, float(max_time_minutes))
    # Full-graph shortest-path searches are expensive on the Bengaluru graph.
    # A bounded pool keeps fleet requests responsive; vehicles can reuse these
    # alternatives when the fleet is larger than the available route pool.
    candidate_limit = min(max(vehicle_count, 6), 8)
    candidates = []
    used_edges = {}

    for _ in range(candidate_limit):
        try:
            path = nx.shortest_path(
                G,
                source,
                target,
                weight=_edge_weight_for_route(G, emergency_mode, used_edges),
            )
        except nx.NetworkXNoPath:
            break
        path_key = tuple(path)
        if any(tuple(item["path"]) == path_key for item in candidates):
            break
        metrics = compute_path_metrics(G, path, emergency_mode)
        candidates.append({"path": path, **metrics})
        for edge in zip(path[:-1], path[1:]):
            used_edges[edge] = used_edges.get(edge, 0) + 1

    if not candidates:
        raise nx.NetworkXNoPath("No candidate route exists")

    eligible = [
        candidate for candidate in candidates
        if candidate["travel_time_min"] <= max_time_minutes
    ]
    # If the time target cannot support the whole fleet, keep route diversity
    # and report violations instead of collapsing every vehicle onto one road.
    available = eligible if len(eligible) >= min(vehicle_count, len(candidates)) else candidates
    assigned_counts = {tuple(candidate["path"]): 0 for candidate in candidates}
    assignments = []

    for vehicle_number in range(1, vehicle_count + 1):
        if vehicle_number <= len(available):
            # Give each available route one vehicle before any route is reused.
            route = available[vehicle_number - 1]
        else:
            route = min(
                available,
                key=lambda candidate: (
                    assigned_counts[tuple(candidate["path"])] * candidate["travel_time_min"],
                    candidate["avg_congestion"],
                ),
            )
        route_key = tuple(route["path"])
        assigned_counts[route_key] += 1
        assignments.append({
            "vehicle_id": f"V-{vehicle_number:02d}",
            "route_index": candidates.index(route) + 1,
            "path": route["path"],
            "path_coords": [],
            "within_max_time": route["travel_time_min"] <= max_time_minutes,
            **{key: value for key, value in route.items() if key != "path"},
        })

    unique_routes = len({tuple(item["path"]) for item in assignments})
    return {
        "vehicle_count": vehicle_count,
        "max_time_minutes": max_time_minutes,
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "unique_route_count": unique_routes,
        "routes_within_limit": sum(item["within_max_time"] for item in assignments),
        "max_travel_time_min": max(item["travel_time_min"] for item in assignments),
        "assignments": assignments,
    }
