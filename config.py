"""
Central configuration for the Quantum-Inspired Traffic Optimizer.
"""

import os

# City to load the road network for (must match the traffic dataset's city)
CITY_NAME = "Bengaluru, Karnataka, India"

# Network type: 'drive' | 'walk' | 'bike'
NETWORK_TYPE = "drive"

# Resolve runtime files relative to this backend package, so `python app.py`
# works whether it is launched from the repository root or backend directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cache file so we don't re-download OSM data every run
GRAPH_CACHE_PATH = os.path.join(BASE_DIR, "bengaluru_graph.graphml")
GRAPH_PKL_PATH = os.path.join(BASE_DIR, "bengaluru_graph.pkl")

# --- Real traffic dataset ---
# Source: "Bangalore's Traffic Pulse" (Kaggle, CC0)
# https://www.kaggle.com/datasets/preethamgouda/banglore-city-traffic-dataset
TRAFFIC_DATASET_PATH = os.path.join(BASE_DIR, "Banlgore_traffic_dataset.csv")

# --- Multi-objective cost weights (must sum to 1.0 conceptually, not enforced) ---
WEIGHT_TIME = 0.55
WEIGHT_DISTANCE = 0.15
WEIGHT_FUEL = 0.15
WEIGHT_FUEL_COST = 0.15
WEIGHT_CONGESTION = 0.30

# Reference scales used to normalize unlike edge metrics before combining them.
# They are deliberately configurable so the objective can be tuned centrally.
NORMALIZATION_DISTANCE_KM = 10.0
NORMALIZATION_TIME_MIN = 30.0
NORMALIZATION_FUEL_L = 1.0
NORMALIZATION_FUEL_COST = 100.0
NORMALIZATION_CONGESTION = 3.0

# Edge-level vehicle operating assumptions used by the weighted graph.
FUEL_CONSUMPTION_L_PER_100KM = 8.0
FUEL_PRICE_PER_LITRE = 100.0
TIME_COST_PER_MINUTE = 1.0

# --- QIGA (Quantum-Inspired Genetic Algorithm) hyperparameters ---
QIGA_POPULATION_SIZE = 12
QIGA_GENERATIONS = 10
QIGA_ROTATION_STEP = 0.08
QIGA_MUTATION_PROB = 0.08
QIGA_ELITE_COUNT = 3

# --- Traffic refresh (cycles through real dataset time-slices) ---
TRAFFIC_UPDATE_INTERVAL_SEC = 15

# --- Emergency vehicle priority mode ---
# When enabled, congestion is heavily discounted (assumes right-of-way /
# siren clearance) so ambulances, fire trucks, police get the fastest
# physical route rather than the least-congested one.
EMERGENCY_CONGESTION_DISCOUNT = 0.15  # multiply congestion impact by this factor