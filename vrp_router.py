"""Capacity- and time-constrained vehicle routing over the road graph."""

import time

import networkx as nx

from classical_router import compute_path_metrics, edge_cost


def _shortest_leg(graph, start, end, emergency_mode):
    path = nx.shortest_path(
        graph,
        start,
        end,
        weight=lambda u, v, data: min(
            edge_cost(edge, emergency_mode) for edge in data.values()
        ),
    )
    return path, compute_path_metrics(graph, path, emergency_mode)


def optimize_vrp(
    graph,
    depot_start,
    depot_end,
    stops,
    vehicle_count,
    vehicle_capacity,
    max_route_time_minutes,
    emergency_mode=False,
):
    """Greedy insertion heuristic for an open capacitated VRP.

    Vehicles start at depot_start, serve assigned stops, and finish at
    depot_end. Stops that cannot fit capacity or route-time constraints remain
    in ``unassigned_stops`` instead of being silently dropped.
    """
    started = time.perf_counter()
    vehicle_count = max(1, min(int(vehicle_count), 100))
    vehicle_capacity = float(vehicle_capacity)
    max_route_time_minutes = float(max_route_time_minutes)
    if vehicle_capacity <= 0 or max_route_time_minutes <= 0:
        raise ValueError("vehicle_capacity and max_route_time_minutes must be positive")

    vehicles = [
        {
            "vehicle_id": f"V-{index:02d}",
            "stops": [],
            "demand": 0.0,
            "path": [depot_start],
            "metrics": {"travel_time_min": 0.0, "distance_km": 0.0, "cost": 0.0, "avg_congestion": 1.0},
        }
        for index in range(1, vehicle_count + 1)
    ]
    unassigned = []

    # Largest demands first prevents small deliveries from consuming all capacity.
    ordered_stops = sorted(stops, key=lambda stop: float(stop.get("demand", 1)), reverse=True)
    for stop in ordered_stops:
        stop_node = stop["node"]
        demand = float(stop.get("demand", 1))
        candidates = []
        for vehicle in vehicles:
            if vehicle["demand"] + demand > vehicle_capacity:
                continue
            proposed_stops = vehicle["stops"] + [stop]
            current_node = depot_start
            combined_path = [depot_start]
            total_metrics = []
            feasible = True
            for proposed_stop in proposed_stops:
                leg_path, leg_metrics = _shortest_leg(graph, current_node, proposed_stop["node"], emergency_mode)
                combined_path.extend(leg_path[1:])
                total_metrics.append(leg_metrics)
                current_node = proposed_stop["node"]
            final_path, final_metrics = _shortest_leg(graph, current_node, depot_end, emergency_mode)
            combined_path.extend(final_path[1:])
            total_metrics.append(final_metrics)
            travel_time = sum(item["travel_time_min"] for item in total_metrics)
            if travel_time > max_route_time_minutes:
                feasible = False
            if feasible:
                candidates.append((travel_time, vehicle, proposed_stops, combined_path, total_metrics))

        if not candidates:
            unassigned.append({key: value for key, value in stop.items() if key != "node"})
            continue

        _, vehicle, proposed_stops, combined_path, total_metrics = min(candidates, key=lambda item: item[0])
        vehicle["stops"] = proposed_stops
        vehicle["demand"] += demand
        vehicle["path"] = combined_path
        vehicle["metrics"] = {
            key: round(sum(item[key] for item in total_metrics), 2)
            for key in ("travel_time_min", "distance_km", "cost", "fuel_l", "operating_cost")
        }
        vehicle["metrics"]["avg_congestion"] = round(
            sum(item["avg_congestion"] * item["distance_km"] for item in total_metrics)
            / max(sum(item["distance_km"] for item in total_metrics), 0.001),
            2,
        )

    assignments = []
    for index, vehicle in enumerate(vehicles, start=1):
        if not vehicle["stops"]:
            continue
        assignments.append({
            "vehicle_id": vehicle["vehicle_id"],
            "route_index": index,
            "stop_ids": [stop.get("id", f"stop-{position + 1}") for position, stop in enumerate(vehicle["stops"])],
            "stop_count": len(vehicle["stops"]),
            "demand": round(vehicle["demand"], 2),
            "capacity_remaining": round(vehicle_capacity - vehicle["demand"], 2),
            "path": vehicle["path"],
            **vehicle["metrics"],
            "within_max_time": vehicle["metrics"]["travel_time_min"] <= max_route_time_minutes,
        })

    return {
        "algorithm": "Capacitated VRP (greedy insertion)",
        "vehicle_count": vehicle_count,
        "vehicle_capacity": vehicle_capacity,
        "max_route_time_minutes": max_route_time_minutes,
        "stop_count": len(stops),
        "served_stop_count": sum(item["stop_count"] for item in assignments),
        "unassigned_stop_count": len(unassigned),
        "unassigned_stops": unassigned,
        "route_count": len(assignments),
        "assignments": assignments,
        "compute_time_sec": round(time.perf_counter() - started, 4),
    }
