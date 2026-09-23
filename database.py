"""
SQLite database layer for Q-ROUTE.
Provides persistent storage for users, route requests, routes, and sessions.
"""

import os
import sqlite3
import time
import uuid
import threading
from contextlib import contextmanager

import config

DB_PATH = os.path.join(config.BASE_DIR, "qroute.db")

_local = threading.local()


def _get_connection():
    """Thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def get_db():
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Create all tables if they don't exist."""
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                activated INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login TEXT
            );

            CREATE TABLE IF NOT EXISTS route_requests (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                origin_lat REAL NOT NULL,
                origin_lon REAL NOT NULL,
                origin_label TEXT,
                destination_lat REAL NOT NULL,
                destination_lon REAL NOT NULL,
                destination_label TEXT,
                traffic_preference TEXT DEFAULT 'any',
                optimization_mode TEXT DEFAULT 'balanced',
                requested_route_count INTEGER DEFAULT 3,
                emergency_mode INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS routes (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                route_index INTEGER NOT NULL,
                algorithm TEXT NOT NULL,
                distance_km REAL,
                travel_time_min REAL,
                fuel_consumption_l REAL,
                fuel_cost REAL,
                traffic_level TEXT,
                avg_congestion REAL,
                optimization_score REAL,
                cost REAL,
                route_geometry TEXT,
                selected INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (request_id) REFERENCES route_requests(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                login_time TEXT NOT NULL,
                logout_time TEXT,
                last_active TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_route_requests_user ON route_requests(user_id);
            CREATE INDEX IF NOT EXISTS idx_routes_request ON routes(request_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        """)
    print("[database] SQLite database initialized.")


# ─── User CRUD ────────────────────────────────────────────────────────

def create_user(name, email, phone, username, password_hash, role="user"):
    user_id = f"{role}-{uuid.uuid4().hex[:12]}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute(
            "INSERT INTO users (id, name, email, phone, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, name, email, phone, username, password_hash, role, created_at),
        )
    return {
        "id": user_id, "name": name, "email": email, "phone": phone,
        "username": username, "role": role, "created_at": created_at, "activated": True,
    }


def find_user_by_identifier(identifier):
    if not identifier:
        return None
    value = str(identifier).strip().lower()
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM users WHERE LOWER(email)=? OR LOWER(phone)=? OR LOWER(username)=?",
            (value, value, value),
        ).fetchone()
    return dict(row) if row else None


def find_user_by_id(user_id):
    if not user_id:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_all_users():
    with get_db() as db:
        rows = db.execute("SELECT id, name, email, phone, username, role, activated, created_at, last_login FROM users").fetchall()
    return [dict(r) for r in rows]


def update_last_login(user_id):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))


def user_exists(email=None, phone=None, username=None):
    with get_db() as db:
        conditions = []
        params = []
        if email:
            conditions.append("LOWER(email)=?")
            params.append(email.lower())
        if phone:
            conditions.append("LOWER(phone)=?")
            params.append(phone.lower())
        if username:
            conditions.append("LOWER(username)=?")
            params.append(username.lower())
        if not conditions:
            return False
        query = f"SELECT COUNT(*) FROM users WHERE {' OR '.join(conditions)}"
        count = db.execute(query, params).fetchone()[0]
    return count > 0


# ─── Session CRUD ─────────────────────────────────────────────────────

def create_session(user_id):
    session_id = uuid.uuid4().hex
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute(
            "INSERT INTO sessions (id, user_id, login_time, last_active) VALUES (?,?,?,?)",
            (session_id, user_id, now, now),
        )
    return session_id


def close_session(session_id):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute("UPDATE sessions SET logout_time=? WHERE id=?", (now, session_id))


def touch_session(session_id):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute("UPDATE sessions SET last_active=? WHERE id=?", (now, session_id))


def get_active_session_count():
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE logout_time IS NULL"
        ).fetchone()[0]
    return count


# ─── Route Request CRUD ──────────────────────────────────────────────

def create_route_request(user_id, origin_lat, origin_lon, origin_label,
                          dest_lat, dest_lon, dest_label,
                          traffic_preference="any", optimization_mode="balanced",
                          route_count=3, emergency_mode=False):
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute(
            """INSERT INTO route_requests
            (id, user_id, origin_lat, origin_lon, origin_label, destination_lat, destination_lon,
             destination_label, traffic_preference, optimization_mode,
             requested_route_count, emergency_mode, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (request_id, user_id, origin_lat, origin_lon, origin_label,
             dest_lat, dest_lon, dest_label, traffic_preference, optimization_mode,
             route_count, int(emergency_mode), created_at),
        )
    return request_id


def save_route(request_id, route_index, algorithm, distance_km, travel_time_min,
               fuel_l, fuel_cost, traffic_level, avg_congestion, score, cost,
               geometry_json=""):
    route_id = f"route-{uuid.uuid4().hex[:12]}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with get_db() as db:
        db.execute(
            """INSERT INTO routes
            (id, request_id, route_index, algorithm, distance_km, travel_time_min,
             fuel_consumption_l, fuel_cost, traffic_level, avg_congestion,
             optimization_score, cost, route_geometry, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (route_id, request_id, route_index, algorithm, distance_km,
             travel_time_min, fuel_l, fuel_cost, traffic_level, avg_congestion,
             score, cost, geometry_json, created_at),
        )
    return route_id


def select_route(route_id, request_id):
    with get_db() as db:
        db.execute("UPDATE routes SET selected=0 WHERE request_id=?", (request_id,))
        db.execute("UPDATE routes SET selected=1 WHERE id=?", (route_id,))


def get_user_route_history(user_id, limit=50):
    with get_db() as db:
        rows = db.execute(
            """SELECT rr.id as request_id, rr.origin_label, rr.destination_label,
                      rr.origin_lat, rr.origin_lon, rr.destination_lat, rr.destination_lon,
                      rr.traffic_preference, rr.optimization_mode, rr.created_at,
                      r.id as route_id, r.route_index, r.algorithm, r.distance_km,
                      r.travel_time_min, r.fuel_consumption_l, r.fuel_cost,
                      r.traffic_level, r.avg_congestion, r.optimization_score,
                      r.cost, r.selected
               FROM route_requests rr
               LEFT JOIN routes r ON r.request_id = rr.id
               WHERE rr.user_id = ?
               ORDER BY rr.created_at DESC, r.route_index ASC
               LIMIT ?""",
            (user_id, limit * 5),
        ).fetchall()
    # Group by request
    requests = {}
    for row in rows:
        row = dict(row)
        req_id = row["request_id"]
        if req_id not in requests:
            requests[req_id] = {
                "id": req_id,
                "origin_label": row["origin_label"],
                "destination_label": row["destination_label"],
                "origin_lat": row["origin_lat"],
                "origin_lon": row["origin_lon"],
                "destination_lat": row["destination_lat"],
                "destination_lon": row["destination_lon"],
                "traffic_preference": row["traffic_preference"],
                "optimization_mode": row["optimization_mode"],
                "created_at": row["created_at"],
                "routes": [],
            }
        if row.get("route_id"):
            requests[req_id]["routes"].append({
                "id": row["route_id"],
                "route_index": row["route_index"],
                "algorithm": row["algorithm"],
                "distance_km": row["distance_km"],
                "travel_time_min": row["travel_time_min"],
                "fuel_consumption_l": row["fuel_consumption_l"],
                "fuel_cost": row["fuel_cost"],
                "traffic_level": row["traffic_level"],
                "avg_congestion": row["avg_congestion"],
                "optimization_score": row["optimization_score"],
                "cost": row["cost"],
                "selected": bool(row["selected"]),
            })
    return list(requests.values())[:limit]


# ─── Admin Statistics ─────────────────────────────────────────────────

def get_admin_statistics():
    with get_db() as db:
        total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_requests = db.execute("SELECT COUNT(*) FROM route_requests").fetchone()[0]
        today = time.strftime("%Y-%m-%d", time.gmtime())
        requests_today = db.execute(
            "SELECT COUNT(*) FROM route_requests WHERE created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]
        active_sessions = get_active_session_count()
        total_routes = db.execute("SELECT COUNT(*) FROM routes").fetchone()[0]

        # Recent route requests for monitoring
        recent = db.execute(
            """SELECT rr.id, rr.user_id, u.name as user_name, u.email,
                      rr.origin_label, rr.destination_label,
                      rr.traffic_preference, rr.optimization_mode,
                      rr.requested_route_count, rr.created_at
               FROM route_requests rr
               JOIN users u ON u.id = rr.user_id
               ORDER BY rr.created_at DESC LIMIT 20""",
        ).fetchall()

    return {
        "total_users": total_users,
        "total_route_requests": total_requests,
        "requests_today": requests_today,
        "active_sessions": active_sessions,
        "total_routes_generated": total_routes,
        "recent_requests": [dict(r) for r in recent],
    }


def get_all_route_requests(limit=100):
    with get_db() as db:
        rows = db.execute(
            """SELECT rr.*, u.name as user_name, u.email as user_email
               FROM route_requests rr
               JOIN users u ON u.id = rr.user_id
               ORDER BY rr.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
