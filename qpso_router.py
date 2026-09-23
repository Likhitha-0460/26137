"""Classical Quantum Particle Swarm Optimization for graph route selection."""

import math
import random
import time

import networkx as nx

from classical_router import compute_path_metrics, edge_cost


class QPSORouter:
    def __init__(self, graph):
        self.G = graph

    def _candidate_paths(self, source, target, emergency_mode):
        weights = [
            lambda u, v, data: min(edge_cost(item, emergency_mode) for item in data.values()),
            lambda u, v, data: min(float(item.get("length", 50.0)) for item in data.values()),
            lambda u, v, data: min(edge_cost(item, emergency_mode) * float(item.get("congestion", 1.0)) for item in data.values()),
            lambda u, v, data: min(float(item.get("base_travel_time", 1.0)) * float(item.get("congestion", 1.0)) for item in data.values()),
        ]
        paths = []
        for weight in weights:
            try:
                paths.append(nx.shortest_path(self.G, source, target, weight=weight))
            except nx.NetworkXNoPath:
                continue
        unique = []
        seen = set()
        for path in paths:
            if tuple(path) not in seen:
                seen.add(tuple(path))
                unique.append(path)
        if not unique:
            raise nx.NetworkXNoPath("No candidate route exists")
        return unique

    @staticmethod
    def _fitness(metrics, weights):
        return sum(weights[key] * metrics[key] for key in ("travel_time_min", "distance_km", "congestion_cost", "constraint_penalty"))

    def optimize(self, source, target, emergency_mode=False, settings=None):
        settings = settings or {}
        population_size = max(4, min(int(settings.get("population_size", 8)), 60))
        iterations = max(2, min(int(settings.get("iterations", 12)), 120))
        seed = settings.get("seed")
        rng = random.Random(seed)
        weights = {
            "travel_time_min": float(settings.get("weight_time", 0.45)),
            "distance_km": float(settings.get("weight_distance", 0.2)),
            "congestion_cost": float(settings.get("weight_congestion", 0.3)),
            "constraint_penalty": float(settings.get("weight_penalty", 0.05)),
        }
        total = sum(weights.values()) or 1.0
        weights = {key: value / total for key, value in weights.items()}
        paths = self._candidate_paths(source, target, emergency_mode)
        metric_rows = []
        for path in paths:
            metrics = compute_path_metrics(self.G, path, emergency_mode)
            metrics["fitness"] = round(self._fitness(metrics, weights), 6)
            metric_rows.append(metrics)

        start = time.perf_counter()
        particles = [rng.uniform(0, len(paths) - 1) for _ in range(population_size)]
        personal_best = list(particles)
        personal_scores = [metric_rows[min(int(round(value)), len(paths) - 1)]["fitness"] for value in particles]
        best_index = min(range(population_size), key=lambda index: personal_scores[index])
        global_best = personal_best[best_index]
        global_score = personal_scores[best_index]
        history = []
        average_history = []
        for iteration in range(iterations):
            mean_best = sum(personal_best) / len(personal_best)
            scores = []
            for index, particle in enumerate(particles):
                attractor = (personal_best[index] + global_best) / 2
                beta = 0.9 - 0.5 * iteration / max(iterations - 1, 1)
                particle = attractor + (-1 if rng.random() < 0.5 else 1) * beta * abs(mean_best - particle) * math.log(1 / max(rng.random(), 1e-9))
                particles[index] = min(max(particle, 0), len(paths) - 1)
                score = metric_rows[min(int(round(particle)), len(paths) - 1)]["fitness"]
                scores.append(score)
                if score < personal_scores[index]:
                    personal_scores[index] = score
                    personal_best[index] = particle
                    if score < global_score:
                        global_score = score
                        global_best = particle
            history.append(round(global_score, 6))
            average_history.append(round(sum(scores) / len(scores), 6))

        selected_index = min(int(round(global_best)), len(paths) - 1)
        result = dict(metric_rows[selected_index])
        result.update({
            "algorithm": "QPSO (Quantum Particle Swarm Optimization)",
            "path": paths[selected_index],
            "compute_time_sec": round(time.perf_counter() - start, 5),
            "fitness_history": history,
            "average_fitness_history": average_history,
            "convergence_iteration": next((i + 1 for i, value in enumerate(history) if value <= global_score), iterations),
            "population_size": population_size,
            "iterations": iterations,
            "seed": seed,
            "objective_weights": weights,
            "candidate_count": len(paths),
            "quantum_update": "x = p + beta * |mbest - x| * ln(1/u)",
        })
        return result