"""
Basic, explainable route optimization module.

The five official bus stops are fixed (a college bus can't skip stops), but
between consecutive stops there are commonly two possible road segments in
real life (e.g. a main road vs a bypass). This module models that as a small
weighted graph and uses Dijkstra's shortest-path algorithm to pick the
fastest sequence of road segments between stops, given the CURRENT traffic
condition on each segment. This is a real, standard graph algorithm (easy to
explain in a viva) - not a claim of a commercial-grade navigation system.

Each time traffic conditions change, re-running optimize_route() can select
a different (faster) segment - which is what "route optimization" means in
this prototype.
"""

import heapq

# Segment graph: (from_stop, to_stop) -> list of alternate road options
# each option: {"name": ..., "base_minutes": ..., "traffic_sensitivity": multiplier by traffic}
ROAD_SEGMENTS = {
    ("Villupuram Bus Stand", "Mundiyampakkam"): [
        {"name": "Main Road", "base_minutes": 12, "sensitivity": {"low": 1.0, "medium": 1.3, "high": 1.7}},
        {"name": "Bypass Road", "base_minutes": 15, "sensitivity": {"low": 1.0, "medium": 1.05, "high": 1.15}},
    ],
    ("Mundiyampakkam", "Kandamangalam"): [
        {"name": "Main Road", "base_minutes": 10, "sensitivity": {"low": 1.0, "medium": 1.25, "high": 1.6}},
        {"name": "Village Road", "base_minutes": 13, "sensitivity": {"low": 1.0, "medium": 1.1, "high": 1.2}},
    ],
    ("Kandamangalam", "Thirunavalur"): [
        {"name": "Main Road", "base_minutes": 11, "sensitivity": {"low": 1.0, "medium": 1.3, "high": 1.75}},
        {"name": "Bypass Road", "base_minutes": 14, "sensitivity": {"low": 1.0, "medium": 1.1, "high": 1.2}},
    ],
    ("Thirunavalur", "IFET College"): [
        {"name": "Main Road", "base_minutes": 9, "sensitivity": {"low": 1.0, "medium": 1.2, "high": 1.5}},
        {"name": "College Road", "base_minutes": 10, "sensitivity": {"low": 1.0, "medium": 1.05, "high": 1.1}},
    ],
}

ROUTE_STOPS_IN_ORDER = [
    "Villupuram Bus Stand", "Mundiyampakkam", "Kandamangalam", "Thirunavalur", "IFET College",
]


def segment_time(segment, traffic_condition):
    return segment["base_minutes"] * segment["sensitivity"].get(traffic_condition, 1.0)


def optimize_route(traffic_by_segment=None):
    """
    traffic_by_segment: optional dict {(from_stop,to_stop): "low"|"medium"|"high"}.
    If not provided, assumes "medium" traffic everywhere.

    Runs Dijkstra's shortest-path algorithm over the stop graph (each edge
    weighted by the FASTEST available road option under current traffic) and
    returns the optimized path with per-segment choice and total time.
    """
    traffic_by_segment = traffic_by_segment or {}

    # Build adjacency: for each pair of consecutive stops, pick the best (fastest) road
    # option given traffic - this is the "optimization" decision.
    edges = []  # (from, to, weight_minutes, chosen_road_name)
    for (a, b), options in ROAD_SEGMENTS.items():
        traffic = traffic_by_segment.get((a, b), "medium")
        best = min(options, key=lambda opt: segment_time(opt, traffic))
        edges.append((a, b, segment_time(best, traffic), best["name"]))

    # Dijkstra over the (linear, but generalizable) stop graph
    graph = {}
    for a, b, w, road in edges:
        graph.setdefault(a, []).append((b, w, road))

    start = ROUTE_STOPS_IN_ORDER[0]
    end = ROUTE_STOPS_IN_ORDER[-1]

    dist = {stop: float("inf") for stop in ROUTE_STOPS_IN_ORDER}
    dist[start] = 0
    prev = {}
    pq = [(0, start)]
    visited = set()

    while pq:
        d, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)
        if node == end:
            break
        for neighbor, weight, road in graph.get(node, []):
            nd = d + weight
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = (node, road, weight)
                heapq.heappush(pq, (nd, neighbor))

    # Reconstruct path
    path = []
    node = end
    while node in prev:
        p, road, weight = prev[node]
        path.append({"from": p, "to": node, "road": road, "minutes": round(weight, 1)})
        node = p
    path.reverse()

    return {
        "optimized_path": path,
        "total_estimated_minutes": round(dist[end], 1),
        "note": "Fastest available road segment chosen per hop using Dijkstra's algorithm, "
                "based on current traffic per segment. Stops themselves stay fixed.",
    }
