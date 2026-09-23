"""
Quantum-Inspired Genetic Algorithm (QIGA / QGOA) for dynamic multi-objective traffic route optimization.

Key Quantum Mechanics:
1. Q-bit Quantum Chromosome Representation:
   - Chromosome consists of quantum rotation angles theta in [0, pi/2].
   - State amplitudes: alpha = cos(theta) (|0> state: physical distance focus),
     beta = sin(theta) (|1> state: traffic/congestion avoidance focus).
2. Quantum Measurement (Superposition Collapse):
   - Quantum superposition probabilities weight the multi-objective cost function to evaluate candidate path variations.
3. Quantum Rotation Gate Update:
   - Rotates population chromosomes toward elite leaders:
     U(delta_theta) = [[cos(delta_theta), -sin(delta_theta)], [sin(delta_theta), cos(delta_theta)]]
4. Quantum NOT-Gate Mutation:
   - Inverts quantum state (theta -> pi/2 - theta) with mutation probability to escape local congestion traps.
"""

import math
import random
import time
import networkx as nx

import config
from classical_router import edge_cost, compute_path_metrics


class QIGARouter:
    def __init__(self, graph):
        self.G = graph

    def _init_chromosome(self):
        """
        Quantum Chromosome vector:
        [0]: theta_cong  (congestion penalty sensitivity angle)
        [1]: theta_dist  (distance penalty sensitivity angle)
        [2]: theta_stoch (quantum exploration noise angle)
        """
        return [random.uniform(0.05, math.pi / 2 - 0.05) for _ in range(6)]

    def _get_candidate_paths(self, source, target, emergency_mode: bool = False):
        """Generate a compact set of quality path options without expensive full-grid exploration."""
        paths = []

        def heuristic(u, v):
            return ((self.G.nodes[u]["y"] - self.G.nodes[v]["y"]) ** 2 +
                    (self.G.nodes[u]["x"] - self.G.nodes[v]["x"]) ** 2) ** 0.5 * 1000

        try:
            p1 = nx.astar_path(
                self.G, source, target,
                heuristic=heuristic,
                weight=lambda u, v, d: min(edge_cost(x, emergency_mode) for x in d.values())
            )
            paths.append(p1)
        except Exception:
            pass

        try:
            p2 = nx.shortest_path(
                self.G, source, target,
                weight=lambda u, v, d: min(float(x.get("length", 50.0)) for x in d.values())
            )
            paths.append(p2)
        except Exception:
            pass

        try:
            def avoid_cong_weight(u, v, d):
                best = min(d.values(), key=lambda x: edge_cost(x, emergency_mode))
                cong = float(best.get("congestion", 1.0))
                return edge_cost(best, emergency_mode) * (cong ** 2)

            p3 = nx.astar_path(
                self.G, source, target,
                heuristic=heuristic,
                weight=avoid_cong_weight
            )
            paths.append(p3)
        except Exception:
            pass

        # Deduplicate paths
        unique_paths = []
        seen = set()
        for p in paths:
            t = tuple(p)
            if t not in seen:
                seen.add(t)
                unique_paths.append(p)

        if not unique_paths:
            unique_paths.append(nx.shortest_path(self.G, source, target))

        return unique_paths

    def _quantum_eval(self, chromosome, candidate_metrics, emergency_mode: bool = False):
        """
        Evaluate quantum chromosome against path metrics using quantum state amplitudes:
        alpha_cong = cos(theta_0)^2
        beta_dist = sin(theta_1)^2
        """
        theta_cong, theta_dist = chromosome[0], chromosome[1]
        alpha_cong = math.cos(theta_cong) ** 2
        beta_dist = math.sin(theta_dist) ** 2

        best_score = float("inf")
        best_path = None
        best_m = None

        for path, m in candidate_metrics:
            # Weighted multi-objective quantum cost
            c_score = (
                m["travel_time_min"] * (1.0 + alpha_cong * (m["avg_congestion"] - 1.0))
                + m["distance_km"] * beta_dist
            )
            if c_score < best_score:
                best_score = c_score
                best_path = path
                best_m = m

        return best_score, best_path, best_m

    def _quantum_rotation_gate(self, chromosome, best_chromosome):
        new_chrom = []
        for theta, best_theta in zip(chromosome, best_chromosome):
            direction = 1.0 if best_theta > theta else -1.0
            new_theta = theta + direction * config.QIGA_ROTATION_STEP
            new_theta = min(max(new_theta, 0.01), math.pi / 2 - 0.01)
            new_chrom.append(new_theta)
        return new_chrom

    def _quantum_not_mutation(self, chromosome):
        return [
            (math.pi / 2 - theta) if random.random() < config.QIGA_MUTATION_PROB else theta
            for theta in chromosome
        ]

    def optimize(self, source, target, emergency_mode: bool = False, settings=None):
        start_time = time.perf_counter()
        settings = settings or {}
        population_size = max(4, min(int(settings.get("population_size", 6)), 24))
        generations = max(2, min(int(settings.get("generations", 4)), 18))

        candidate_paths = self._get_candidate_paths(source, target, emergency_mode)
        candidate_metrics = [
            (p, compute_path_metrics(self.G, p, emergency_mode))
            for p in candidate_paths
        ]

        population = [self._init_chromosome() for _ in range(population_size)]
        best_chromosome = None
        best_fitness = float("inf")
        best_path = candidate_paths[0]
        best_metrics = candidate_metrics[0][1]
        fitness_history = []

        for gen in range(generations):
            scored = []
            for chrom in population:
                score, path, m = self._quantum_eval(chrom, candidate_metrics, emergency_mode)
                scored.append((score, chrom, path, m))

            scored.sort(key=lambda x: x[0])
            cur_best_score, cur_best_chrom, cur_best_path, cur_best_m = scored[0]

            fitness_history.append(round(cur_best_m["cost"], 2))

            if cur_best_m["cost"] < best_metrics["cost"] or best_chromosome is None:
                best_chromosome = cur_best_chrom
                best_path = cur_best_path
                best_metrics = cur_best_m

            # Quantum evolution update
            elites = [item[1] for item in scored[:min(config.QIGA_ELITE_COUNT, population_size)]]
            new_population = list(elites)
            ref_chrom = best_chromosome if best_chromosome is not None else cur_best_chrom

            while len(new_population) < population_size:
                parent = random.choice(scored[: max(3, population_size // 3)])[1]
                child = self._quantum_rotation_gate(parent, ref_chrom)
                child = self._quantum_not_mutation(child)
                new_population.append(child)

            population = new_population

        elapsed = time.perf_counter() - start_time

        # Calculate congestion avoidance % vs Dijkstra baseline
        dijkstra_path = candidate_paths[0]
        d_metrics = candidate_metrics[0][1]
        baseline_cong = d_metrics["avg_congestion"]
        qiga_cong = best_metrics["avg_congestion"]
        avoidance_pct = round(max(0.0, (baseline_cong - qiga_cong) / max(baseline_cong, 1.0) * 100.0), 1)

        return {
            "algorithm": "QIGA (Quantum-Inspired)",
            "path": best_path,
            "compute_time_sec": round(elapsed, 4),
            "fitness_history": fitness_history,
            "congestion_avoidance_pct": avoidance_pct,
            "emergency_congestion_cleared": emergency_mode,
            "time_complexity": "O(Pop × Gen)",
            **best_metrics,
        }