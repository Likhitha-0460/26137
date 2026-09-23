"""
Flask API — Quantum-Inspired Multi-User Traffic Route Optimization Platform.
Backed by real Bengaluru traffic data & OSM road network.
"""

from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

import config
from graph_utils import load_city_graph, nearest_node
from traffic_simulator import TrafficSimulator
from classical_router import (
    edge_cost,
    dijkstra_route,
    astar_route,
    bpr_route,
    aco_route,
    compute_path_metrics,
    coordinated_fleet_routes,
)
from qiga_router import QIGARouter
from qpso_router import QPSORouter
from vrp_router import optimize_vrp
from multi_route import (
    generate_diverse_routes,
    compute_extended_metrics,
    compute_optimization_score,
    classify_traffic,
    OPTIMIZATION_PRESETS,
)
import database as db

import os
import json
import time
import pandas as pd
import networkx as nx

frontend_folder = os.path.join(os.path.dirname(config.BASE_DIR), "frontend")
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "qroute-dev-secret-key-2026")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
CORS(app, supports_credentials=True)

# ── Initialize database ──────────────────────────────────────────────
db.init_db()

# Seed default admin & demo user if they don't exist
if not db.find_user_by_identifier("admin@qroute.com"):
    db.create_user("Admin User", "admin@qroute.com", "+91 90000 00000",
                   "admin", generate_password_hash("admin123"), "admin")
if not db.find_user_by_identifier("user@qroute.com"):
    db.create_user("Demo User", "user@qroute.com", "+91 91234 56789",
                   "demo", generate_password_hash("demo123"), "user")

# ── Load road graph & traffic ────────────────────────────────────────
print("[app] Booting up — loading road network...")
G = load_city_graph()

simulator = TrafficSimulator(G)
simulator.start_background_updates()

qiga = QIGARouter(G)
qpso = QPSORouter(G)
experiments = []
_route_cache = {}
ROUTE_CACHE_TTL_SEC = 30


# ── Auth helpers ─────────────────────────────────────────────────────

def _password_matches(stored_hash, candidate_password):
    if not stored_hash:
        return False
    if any(stored_hash.startswith(p) for p in ("pbkdf2:", "scrypt:", "sha256:", "argon2")):
        return check_password_hash(stored_hash, candidate_password)
    return stored_hash == candidate_password


def _sanitize_user(user):
    safe = dict(user)
    safe.pop("password_hash", None)
    safe.pop("password", None)
    return safe


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.find_user_by_id(user_id)
    return user


def _require_auth():
    user = _current_user()
    if not user:
        return None, (jsonify({"error": "Authentication required."}), 401)
    return user, None


def _require_admin():
    user = _current_user()
    if not user:
        return None, (jsonify({"error": "Authentication required."}), 401)
    if user.get("role") != "admin":
        return None, (jsonify({"error": "Admin access required."}), 403)
    return user, None


# ── Cache helpers ────────────────────────────────────────────────────

def _cache_key(name, payload):
    return name + ":" + json.dumps(payload, sort_keys=True, default=str)


def _get_cached_route(name, payload):
    key = _cache_key(name, payload)
    cached = _route_cache.get(key)
    if cached and time.monotonic() - cached["created_at"] < ROUTE_CACHE_TTL_SEC:
        return cached["data"]
    if cached:
        _route_cache.pop(key, None)
    return None


def _cache_route(name, payload, data):
    _route_cache[_cache_key(name, payload)] = {
        "created_at": time.monotonic(),
        "data": data,
    }
    return data


def _node_coords(node_id):
    return {"lat": G.nodes[node_id]["y"], "lon": G.nodes[node_id]["x"]}


def _path_to_coords(path):
    return [_node_coords(n) for n in path]


def _path_to_weighted_edges(path, emergency_mode=False):
    weighted_edges = []
    for source, target in zip(path[:-1], path[1:]):
        edge_data = G.get_edge_data(source, target)
        best_edge = min(edge_data.values(), key=lambda data: edge_cost(data, emergency_mode))
        cong = float(best_edge.get("congestion", 1.0))
        weighted_edges.append({
            "from": _node_coords(source),
            "to": _node_coords(target),
            "weight": round(edge_cost(best_edge, emergency_mode), 6),
            "length_m": round(float(best_edge.get("length", 0.0)), 2),
            "congestion": round(cong, 2),
            "traffic_level": classify_traffic(cong),
            "fuel_l": round(float(best_edge.get("fuel_l", 0.0)), 6),
            "fuel_cost": round(float(best_edge.get("fuel_cost", 0.0)), 4),
        })
    return weighted_edges


def _add_path_visualization(route, emergency_mode=False):
    route["path_coords"] = _path_to_coords(route["path"])
    route["weighted_edges"] = _path_to_weighted_edges(route["path"], emergency_mode)
    return route


def _traffic_cache_token():
    return simulator.version


# ── Static file routes ───────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(frontend_folder, "auth.html")


@app.route("/map")
def serve_map():
    return send_from_directory(frontend_folder, "index.html")


@app.route("/admin/login")
def serve_admin_login():
    return send_from_directory(frontend_folder, "admin-login.html")


@app.route("/<path:path>")
def serve_static(path):
    if path.startswith("api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    file_path = os.path.join(frontend_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(frontend_folder, path)
    return send_from_directory(frontend_folder, "index.html")


# ── Auth API ─────────────────────────────────────────────────────────

@app.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    data = request.get_json(force=True) or {}
    required = ["name", "email", "password"]
    missing = [f for f in required if not str(data.get(f, "")).strip()]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    role = str(data.get("role", "user")).lower()
    if role not in {"user", "admin"}:
        return jsonify({"error": "Role must be 'user' or 'admin'"}), 400

    email = str(data["email"]).strip()
    phone = str(data.get("phone", "")).strip()
    username = str(data.get("username", email.split("@")[0])).strip()
    name = str(data["name"]).strip()
    password = str(data["password"]).strip()

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    if db.user_exists(email=email, phone=phone if phone else None, username=username):
        return jsonify({"error": "A user with this email, phone, or username already exists."}), 409

    user = db.create_user(name, email, phone, username,
                          generate_password_hash(password), role)
    return jsonify({
        "message": f"{role.title()} account created successfully.",
        "user": _sanitize_user(user),
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True) or {}
    identifier = str(data.get("identifier", "")).strip()
    password = str(data.get("password", "")).strip()
    if not identifier or not password:
        return jsonify({"error": "Identifier and password are required."}), 400

    user = db.find_user_by_identifier(identifier)
    if not user or not _password_matches(user.get("password_hash"), password):
        return jsonify({"error": "Invalid credentials."}), 401

    session["user_id"] = user["id"]
    session["role"] = user["role"]
    db.update_last_login(user["id"])
    db.create_session(user["id"])

    return jsonify({
        "message": "Login successful.",
        "user": _sanitize_user(user),
    })


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(force=True) or {}
    identifier = str(data.get("identifier", "")).strip()
    password = str(data.get("password", "")).strip()
    if not identifier or not password:
        return jsonify({"error": "Email/phone/username and password are required."}), 400

    user = db.find_user_by_identifier(identifier)
    if not user or user.get("role") != "admin" or not _password_matches(user.get("password_hash"), password):
        return jsonify({"error": "Invalid admin credentials."}), 401

    session["user_id"] = user["id"]
    session["role"] = "admin"
    db.update_last_login(user["id"])
    db.create_session(user["id"])

    return jsonify({
        "message": "Admin login successful.",
        "user": _sanitize_user(user),
    })


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    user = _current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401
    return jsonify({"user": _sanitize_user(user)})


# ── Graph & Traffic Info ─────────────────────────────────────────────

@app.route("/api/geocode", methods=["GET"])
def geocode():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    if "bengaluru" not in query.lower() and "bangalore" not in query.lower():
        search_query = f"{query}, Bengaluru, Karnataka, India"
    else:
        search_query = query

    import urllib.parse
    import urllib.request

    url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(search_query)}&limit=5&addressdetails=1"
    req = urllib.request.Request(url, headers={"User-Agent": "SIH-Traffic-Optimizer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            results = []
            for item in data:
                # Build area name from address components
                addr = item.get("address", {})
                area_parts = []
                for key in ["road", "suburb", "neighbourhood", "village", "town", "city_district"]:
                    if addr.get(key):
                        area_parts.append(addr[key])
                        if len(area_parts) >= 2:
                            break
                area_name = ", ".join(area_parts) if area_parts else item.get("display_name", "").split(",")[0]

                results.append({
                    "display_name": item.get("display_name"),
                    "area_name": area_name,
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                })
            return jsonify(results)
    except Exception as err:
        return jsonify({"error": str(err)}), 500


@app.route("/api/graph-bounds", methods=["GET"])
def graph_bounds():
    lats = [data["y"] for _, data in G.nodes(data=True)]
    lons = [data["x"] for _, data in G.nodes(data=True)]
    return jsonify({
        "center": {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)},
        "bounds": {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
        },
        "node_count": len(G.nodes),
        "edge_count": len(G.edges),
        "city": config.CITY_NAME,
        "dataset_loaded": simulator.dataset_available(),
        "dataset_source": "Kaggle: Bangalore's Traffic Pulse (CC0)",
        "optimization_modes": list(OPTIMIZATION_PRESETS.keys()),
    })


@app.route("/api/congestion", methods=["GET"])
def congestion_snapshot():
    snap = simulator.snapshot_congestion()
    sorted_edges = sorted(snap.items(), key=lambda x: x[1], reverse=True)
    sample = []
    for (u, v, k), level in sorted_edges[:3000]:
        sample.append({
            "from": _node_coords(u),
            "to": _node_coords(v),
            "congestion": round(level, 2),
        })
    return jsonify({"edges": sample, "dataset_loaded": simulator.dataset_available()})


@app.route("/api/city-insights", methods=["GET"])
def city_insights():
    congestion_by_road = {}
    for u, v, k, data in G.edges(keys=True, data=True):
        name = data.get("name", "Unnamed road")
        if isinstance(name, list):
            name = name[0] if name else "Unnamed road"
        congestion_by_road.setdefault(name, []).append(data.get("congestion", 1.0))

    ranked = sorted(
        (
            {"road": name, "avg_congestion": round(sum(vals) / len(vals), 2), "segments": len(vals)}
            for name, vals in congestion_by_road.items()
            if name != "Unnamed road"
        ),
        key=lambda r: r["avg_congestion"],
        reverse=True,
    )

    return jsonify({
        "city": config.CITY_NAME,
        "most_congested_roads": ranked[:15],
        "dataset_source": "Kaggle: Bangalore's Traffic Pulse (CC0)",
    })


@app.route("/api/traffic-mode", methods=["POST"])
def traffic_mode():
    body = request.get_json(force=True) or {}
    mode = body.get("mode", "Normal")
    factors = {"Free Flow": 0.75, "Normal": 1.0, "Peak Hour": 1.35, "Heavy Congestion": 1.8, "Accident / Road Block": 2.4}
    factor = float(body.get("factor", factors.get(mode, 1.0)))
    blocked = 0
    for _, _, _, data in G.edges(keys=True, data=True):
        base = float(data.get("dataset_congestion", data.get("congestion", 1.0)))
        data["congestion"] = round(max(1.0, min(3.0, base * factor)), 3)
        data["available"] = not (mode == "Accident / Road Block" and data["congestion"] >= 2.9)
        blocked += int(not data["available"])
    simulator.version += 1
    return jsonify({"mode": mode, "factor": factor, "blocked_edges": blocked, "updated_edges": len(G.edges)})


@app.route("/api/dataset", methods=["GET"])
def dataset_summary():
    path = config.TRAFFIC_DATASET_PATH
    if not os.path.exists(path):
        return jsonify({"available": False, "path": path, "error": "Dataset not found"}), 404
    frame = pd.read_csv(path)
    missing = {str(column): int(value) for column, value in frame.isna().sum().items() if value}
    return jsonify({
        "available": True,
        "path": path,
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "missing_values": missing,
        "preview": json.loads(frame.head(8).to_json(orient="records")),
        "numeric_statistics": json.loads(frame.describe(include="number").round(3).to_json()),
    })


# ── Multi-Route Calculation ──────────────────────────────────────────

@app.route("/api/routes/calculate", methods=["POST"])
def calculate_routes():
    """Generate multiple diverse optimized routes for a user."""
    user, err = _require_auth()
    if err:
        return err

    body = request.get_json(force=True) or {}
    try:
        src_lat = float(body["source_lat"])
        src_lon = float(body["source_lon"])
        tgt_lat = float(body["target_lat"])
        tgt_lon = float(body["target_lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "source_lat, source_lon, target_lat, target_lon are required"}), 400

    num_routes = max(1, min(int(body.get("num_routes", 3)), 5))
    traffic_pref = str(body.get("traffic_preference", "any")).lower()
    opt_mode = str(body.get("optimization_mode", "balanced")).lower()
    emergency = bool(body.get("emergency_mode", False))
    source_label = str(body.get("source_label", ""))
    dest_label = str(body.get("destination_label", ""))

    source = nearest_node(G, src_lat, src_lon)
    target = nearest_node(G, tgt_lat, tgt_lon)

    if source == target:
        return jsonify({"error": "Source and target resolved to the same node — pick points further apart"}), 400

    # Check cache
    cache_payload = {
        "source": source, "target": target, "num_routes": num_routes,
        "traffic_pref": traffic_pref, "opt_mode": opt_mode,
        "emergency": emergency, "traffic_version": _traffic_cache_token(),
    }
    cached = _get_cached_route("multi_route", cache_payload)
    if cached is not None:
        return jsonify(cached)

    try:
        result = generate_diverse_routes(
            G, source, target, num_routes,
            emergency, opt_mode, traffic_pref,
        )
    except nx.NetworkXNoPath as e:
        return jsonify({"error": str(e)}), 400

    # Save to database
    request_id = db.create_route_request(
        user["id"], src_lat, src_lon, source_label,
        tgt_lat, tgt_lon, dest_label,
        traffic_pref, opt_mode, num_routes, emergency,
    )

    # Add visualization and save routes
    for route in result["routes"]:
        _add_path_visualization(route, emergency)

        db.save_route(
            request_id, route["route_index"], route["algorithm"],
            route["distance_km"], route["travel_time_min"],
            route.get("fuel_consumption_l", 0), route.get("fuel_cost", 0),
            route.get("traffic_level", "MEDIUM"), route["avg_congestion"],
            route.get("optimization_score", 0), route["cost"],
        )

        # Remove raw path (too large for JSON)
        route.pop("path", None)

    response_data = {
        "request_id": request_id,
        "source_coords": _node_coords(source),
        "target_coords": _node_coords(target),
        "source_label": source_label,
        "destination_label": dest_label,
        "emergency_mode": emergency,
        "optimization_mode": opt_mode,
        "traffic_preference": traffic_pref,
        **result,
    }

    return jsonify(_cache_route("multi_route", cache_payload, response_data))


@app.route("/api/routes/select", methods=["POST"])
def select_route():
    """User selects one of the generated routes."""
    user, err = _require_auth()
    if err:
        return err

    data = request.get_json(force=True) or {}
    route_id = str(data.get("route_id", "")).strip()
    request_id = str(data.get("request_id", "")).strip()
    if not route_id or not request_id:
        return jsonify({"error": "route_id and request_id are required."}), 400

    db.select_route(route_id, request_id)
    return jsonify({"message": "Route selected.", "route_id": route_id})


# ── Route History ────────────────────────────────────────────────────

@app.route("/api/routes/history", methods=["GET"])
def route_history():
    user, err = _require_auth()
    if err:
        return err
    history = db.get_user_route_history(user["id"])
    return jsonify({"history": history})


# ── User Profile ─────────────────────────────────────────────────────

@app.route("/api/user/profile", methods=["GET"])
def user_profile():
    user, err = _require_auth()
    if err:
        return err
    history = db.get_user_route_history(user["id"], limit=5)
    return jsonify({
        "user": _sanitize_user(user),
        "recent_routes": history,
    })


# ── Legacy Optimize (kept for backward compatibility) ────────────────

@app.route("/api/optimize", methods=["POST"])
def optimize():
    body = request.get_json(force=True)
    try:
        src_lat, src_lon = float(body["source_lat"]), float(body["source_lon"])
        tgt_lat, tgt_lon = float(body["target_lat"]), float(body["target_lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "source_lat, source_lon, target_lat, target_lon are required"}), 400

    emergency_mode = bool(body.get("emergency_mode", False))
    settings = body.get("settings", body)

    source = nearest_node(G, src_lat, src_lon)
    target = nearest_node(G, tgt_lat, tgt_lon)

    if source == target:
        return jsonify({"error": "Source and target resolved to the same node — pick points further apart"}), 400

    cache_payload = {
        "source": source, "target": target, "emergency": emergency_mode,
        "settings": settings, "traffic_version": _traffic_cache_token(),
    }
    cached = _get_cached_route("optimize", cache_payload)
    if cached is not None:
        return jsonify(cached)

    results = {
        "emergency_mode": emergency_mode,
        "source_coords": _node_coords(source),
        "target_coords": _node_coords(target),
    }

    try:
        dij = dijkstra_route(G, source, target, emergency_mode)
        _add_path_visualization(dij, emergency_mode)
        results["dijkstra"] = dij
    except Exception as e:
        results["dijkstra"] = {"error": f"No path found: {str(e)}"}

    try:
        astar = astar_route(G, source, target, emergency_mode)
        _add_path_visualization(astar, emergency_mode)
        results["astar"] = astar
    except Exception as e:
        results["astar"] = {"error": f"No path found: {str(e)}"}

    try:
        qpso_result = qpso.optimize(source, target, emergency_mode, settings)
        _add_path_visualization(qpso_result, emergency_mode)
        results["qpso"] = qpso_result
        results["qiga"] = qpso_result
    except Exception as e:
        results["qiga"] = {"error": f"QIGA optimization error: {str(e)}"}

    baseline_congestion = results.get("dijkstra", {}).get("avg_congestion")
    if baseline_congestion:
        for key in ("dijkstra", "astar", "qpso", "qiga"):
            route = results.get(key, {})
            if "avg_congestion" in route:
                route["congestion_avoidance_pct"] = round(
                    max(0.0, (baseline_congestion - route["avg_congestion"])
                    / max(baseline_congestion, 1.0) * 100.0), 1
                )

    if "cost" in results.get("dijkstra", {}) and "cost" in results.get("qpso", {}):
        baseline_cost = results["dijkstra"]["cost"]
        qiga_cost = results["qpso"]["cost"]
        results["improvement_vs_dijkstra_pct"] = round(
            (baseline_cost - qiga_cost) / max(baseline_cost, 0.001) * 100, 1
        )
        baseline_time = results["dijkstra"].get("travel_time_min", 0)
        qiga_time = results["qpso"].get("travel_time_min", 0)
        results["time_saved_min"] = round(max(0, baseline_time - qiga_time), 1)

    results["experiment"] = {
        "objective": "F = alpha*T + beta*D + gamma*C + delta*P",
        "engine": "QPSO",
        "settings": settings,
    }

    return jsonify(_cache_route("optimize", cache_payload, results))


# ── Benchmark ────────────────────────────────────────────────────────

@app.route("/api/benchmark", methods=["POST"])
def benchmark():
    body = request.get_json(force=True) or {}
    try:
        source = nearest_node(G, float(body["source_lat"]), float(body["source_lon"]))
        target = nearest_node(G, float(body["target_lat"]), float(body["target_lon"]))
    except (KeyError, ValueError):
        return jsonify({"error": "source_lat, source_lon, target_lat, target_lon are required"}), 400

    emergency = bool(body.get("emergency_mode", False))
    requested_settings = body.get("settings", {})

    # Benchmark mode: quick (default), standard, detailed
    benchmark_mode = str(body.get("benchmark_mode", "quick")).lower()

    if benchmark_mode == "detailed":
        benchmark_settings = {
            "population_size": max(4, min(int(requested_settings.get("population_size", 10)), 12)),
            "iterations": max(2, min(int(requested_settings.get("iterations", 12)), 20)),
            "generations": max(2, min(int(requested_settings.get("generations", 8)), 12)),
            "seed": requested_settings.get("seed", 42),
            "weight_time": requested_settings.get("weight_time", 0.45),
            "weight_distance": requested_settings.get("weight_distance", 0.2),
            "weight_congestion": requested_settings.get("weight_congestion", 0.3),
        }
        classical_runners = (dijkstra_route, astar_route, bpr_route, aco_route)
        run_quantum = True
    elif benchmark_mode == "standard":
        benchmark_settings = {
            "population_size": max(4, min(int(requested_settings.get("population_size", 6)), 8)),
            "iterations": max(2, min(int(requested_settings.get("iterations", 6)), 10)),
            "generations": max(2, min(int(requested_settings.get("generations", 4)), 6)),
            "seed": requested_settings.get("seed", 42),
            "weight_time": requested_settings.get("weight_time", 0.45),
            "weight_distance": requested_settings.get("weight_distance", 0.2),
            "weight_congestion": requested_settings.get("weight_congestion", 0.3),
        }
        classical_runners = (dijkstra_route, astar_route, aco_route)
        run_quantum = True
    else:  # quick
        benchmark_settings = {
            "population_size": 4,
            "iterations": 3,
            "generations": 3,
            "seed": requested_settings.get("seed", 42),
            "weight_time": requested_settings.get("weight_time", 0.45),
            "weight_distance": requested_settings.get("weight_distance", 0.2),
            "weight_congestion": requested_settings.get("weight_congestion", 0.3),
        }
        classical_runners = (dijkstra_route, astar_route)
        run_quantum = False

    cache_payload = {
        "source": source, "target": target, "emergency": emergency,
        "settings": benchmark_settings, "mode": benchmark_mode,
        "traffic_version": _traffic_cache_token(),
    }
    cached = _get_cached_route("benchmark", cache_payload)
    if cached is not None:
        return jsonify(cached)

    results = []
    for runner in classical_runners:
        try:
            result = runner(G, source, target, emergency)
            _add_path_visualization(result, emergency)
            # Add fuel metrics
            ext = compute_extended_metrics(G, result["path"], emergency)
            result["fuel_consumption_l"] = ext.get("fuel_consumption_l", 0)
            result["fuel_cost"] = ext.get("fuel_cost", 0)
            result["traffic_level"] = ext.get("traffic_level", "MEDIUM")
            results.append(result)
        except Exception:
            pass

    if run_quantum:
        try:
            quantum = qpso.optimize(source, target, emergency, benchmark_settings)
            _add_path_visualization(quantum, emergency)
            ext = compute_extended_metrics(G, quantum["path"], emergency)
            quantum["fuel_consumption_l"] = ext.get("fuel_consumption_l", 0)
            quantum["fuel_cost"] = ext.get("fuel_cost", 0)
            quantum["traffic_level"] = ext.get("traffic_level", "MEDIUM")
            results.append(quantum)
        except Exception:
            pass
        try:
            qiga_result = qiga.optimize(source, target, emergency, benchmark_settings)
            _add_path_visualization(qiga_result, emergency)
            ext = compute_extended_metrics(G, qiga_result["path"], emergency)
            qiga_result["fuel_consumption_l"] = ext.get("fuel_consumption_l", 0)
            qiga_result["fuel_cost"] = ext.get("fuel_cost", 0)
            qiga_result["traffic_level"] = ext.get("traffic_level", "MEDIUM")
            results.append(qiga_result)
        except Exception:
            pass

    if not results:
        return jsonify({"error": "No algorithm could find a path"}), 400

    fastest = min(results, key=lambda r: r.get("travel_time_min", float("inf")))
    fastest_time = max(float(fastest.get("travel_time_min", 0)), 0.001)
    for result in results:
        travel_time = max(float(result.get("travel_time_min", 0)), 0.001)
        result["efficiency_pct"] = round(fastest_time / travel_time * 100.0, 2)
        result["time_gap_pct"] = round(max(0.0, (travel_time - fastest_time) / fastest_time * 100.0), 2)

    minima = {
        key: max(min(float(r.get(key, 0)) for r in results), 0.001)
        for key in ("travel_time_min", "avg_congestion", "distance_km", "compute_time_sec")
    }
    for result in results:
        score = (
            0.45 * minima["travel_time_min"] / max(float(result.get("travel_time_min", 0)), 0.001)
            + 0.25 * minima["avg_congestion"] / max(float(result.get("avg_congestion", 0)), 0.001)
            + 0.20 * minima["distance_km"] / max(float(result.get("distance_km", 0)), 0.001)
            + 0.10 * minima["compute_time_sec"] / max(float(result.get("compute_time_sec", 0)), 0.001)
        )
        result["overall_score_pct"] = round(score * 100.0, 2)
        # Remove path from response
        result.pop("path", None)

    ranked = sorted(results, key=lambda r: r["overall_score_pct"], reverse=True)
    for index, result in enumerate(ranked, start=1):
        result["rank"] = index

    efficient = ranked[0]
    worst = ranked[-1]
    response_data = {
        "algorithms": results,
        "benchmark_mode": benchmark_mode,
        "objective": "travel time + distance + congestion + compute time",
        "same_scenario": True,
        "best_travel_time": fastest["algorithm"],
        "recommended_algorithm": efficient["algorithm"],
        "worst_algorithm": worst["algorithm"],
        "scoring": {
            "travel_time": 45, "congestion": 25, "distance": 20, "compute_time": 10,
            "meaning": "Higher overall score is better.",
        },
    }
    return jsonify(_cache_route("benchmark", cache_payload, response_data))


# ── Experiments ──────────────────────────────────────────────────────

@app.route("/api/experiments", methods=["GET", "POST"])
def experiment_history():
    if request.method == "POST":
        experiment = request.get_json(force=True) or {}
        experiment["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        experiments.append(experiment)
        return jsonify({"saved": True, "id": len(experiments), "saved_at": experiment["saved_at"]}), 201
    return jsonify({"experiments": experiments, "count": len(experiments)})


# ── Admin API ────────────────────────────────────────────────────────

@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    user, err = _require_admin()
    if err:
        return err

    users = db.get_all_users()
    return jsonify({"users": [_sanitize_user(u) for u in users]})


@app.route("/api/admin/statistics", methods=["GET"])
def admin_statistics():
    user, err = _require_admin()
    if err:
        return err

    stats = db.get_admin_statistics()
    return jsonify(stats)


@app.route("/api/admin/routes", methods=["GET"])
def admin_routes():
    user, err = _require_admin()
    if err:
        return err

    routes = db.get_all_route_requests()
    return jsonify({"route_requests": routes})


@app.route("/api/admin/performance", methods=["GET"])
def admin_performance():
    user, err = _require_admin()
    if err:
        return err

    return jsonify({
        "graph_nodes": len(G.nodes),
        "graph_edges": len(G.edges),
        "cache_entries": len(_route_cache),
        "cache_ttl_sec": ROUTE_CACHE_TTL_SEC,
        "traffic_version": simulator.version,
        "traffic_update_interval": config.TRAFFIC_UPDATE_INTERVAL_SEC,
    })


# ── Fleet & VRP (preserved) ─────────────────────────────────────────

@app.route("/api/fleet-optimize", methods=["POST"])
def fleet_optimize():
    body = request.get_json(force=True) or {}
    try:
        source = nearest_node(G, float(body["source_lat"]), float(body["source_lon"]))
        target = nearest_node(G, float(body["target_lat"]), float(body["target_lon"]))
        vehicle_count = int(body.get("vehicle_count", 1))
        max_time_minutes = float(body.get("max_time_minutes", 60))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "source/target coords, vehicle_count, max_time_minutes required"}), 400

    if not 1 <= vehicle_count <= 100:
        return jsonify({"error": "vehicle_count must be between 1 and 100"}), 400
    if source == target:
        return jsonify({"error": "Source and target resolved to the same node"}), 400

    emergency_mode = bool(body.get("emergency_mode", False))
    cache_payload = {"source": source, "target": target, "vehicles": vehicle_count,
                     "max_time": max_time_minutes, "emergency": emergency_mode}
    cached = _get_cached_route("fleet", cache_payload)
    if cached is not None:
        return jsonify(cached)

    try:
        fleet = coordinated_fleet_routes(G, source, target, vehicle_count, max_time_minutes, emergency_mode)
        for assignment in fleet["assignments"]:
            _add_path_visualization(assignment, emergency_mode)
        fleet["assignments"] = [
            {k: v for k, v in a.items() if k != "path"} for a in fleet["assignments"]
        ]
        response_data = {
            "source_coords": _node_coords(source), "target_coords": _node_coords(target),
            "emergency_mode": emergency_mode, **fleet,
        }
        return jsonify(_cache_route("fleet", cache_payload, response_data))
    except Exception as error:
        return jsonify({"error": f"Fleet optimization failed: {error}"}), 500


@app.route("/api/vrp-optimize", methods=["POST"])
def vrp_optimize():
    body = request.get_json(force=True) or {}
    try:
        depot_start = nearest_node(G, float(body["source_lat"]), float(body["source_lon"]))
        depot_end = nearest_node(G, float(body["target_lat"]), float(body["target_lon"]))
        vehicle_count = int(body.get("vehicle_count", 1))
        vehicle_capacity = float(body.get("vehicle_capacity", 10))
        max_route_time = float(body.get("max_route_time_minutes", body.get("max_time_minutes", 60)))
        raw_stops = body.get("stops", [])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "depot coords, stops, vehicle_count, vehicle_capacity required"}), 400

    if not isinstance(raw_stops, list) or not raw_stops:
        return jsonify({"error": "stops must contain at least one delivery stop"}), 400

    try:
        stops = []
        for index, stop in enumerate(raw_stops, start=1):
            lat, lon = float(stop["lat"]), float(stop["lon"])
            demand = float(stop.get("demand", 1))
            stops.append({
                "id": str(stop.get("id", f"stop-{index}")),
                "lat": lat, "lon": lon, "demand": demand,
                "node": nearest_node(G, lat, lon),
            })
        result = optimize_vrp(G, depot_start, depot_end, stops, vehicle_count,
                              vehicle_capacity, max_route_time, bool(body.get("emergency_mode", False)))
        for assignment in result["assignments"]:
            _add_path_visualization(assignment, bool(body.get("emergency_mode", False)))
            assignment.pop("path", None)
        result["source_coords"] = _node_coords(depot_start)
        result["target_coords"] = _node_coords(depot_end)
        return jsonify(result)
    except (ValueError, nx.NetworkXNoPath) as error:
        return jsonify({"error": f"VRP could not create a feasible plan: {error}"}), 400
    except Exception as error:
        return jsonify({"error": f"VRP optimization failed: {error}"}), 500


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, port=5000, use_reloader=False)