import math
from typing import List, Dict, Any, Tuple, Optional
from database import is_mongo_connected, get_zones_col, mem_zones

def ccw(A: Tuple[float, float], B: Tuple[float, float], C: Tuple[float, float]) -> float:
    """Computes cross product of vector AB and AC."""
    return (B[0] - A[0]) * (C[1] - A[1]) - (B[1] - A[1]) * (C[0] - A[0])

def on_segment(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float], eps: float = 1e-9) -> bool:
    """Checks if point p lies on line segment ab."""
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps and
        min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )

def segments_intersect(
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
    d: Tuple[float, float],
    eps: float = 1e-9
) -> bool:
    """
    Determines if line segment ab intersects line segment cd.
    Handles strict interior intersections and collinear/touching overlaps.
    """
    d1 = ccw(c, d, a)
    d2 = ccw(c, d, b)
    d3 = ccw(a, b, c)
    d4 = ccw(a, b, d)

    # General strict intersection
    if ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps)) and \
       ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)):
        return True

    # Special collinear / endpoint on segment cases
    if abs(d1) <= eps and on_segment(a, c, d, eps):
        return True
    if abs(d2) <= eps and on_segment(b, c, d, eps):
        return True
    if abs(d3) <= eps and on_segment(c, a, b, eps):
        return True
    if abs(d4) <= eps and on_segment(d, a, b, eps):
        return True

    return False

def compute_polygon_area(vertices: List[Tuple[float, float]]) -> float:
    """
    Computes absolute area using the Shoelace formula (Gauss's area formula).
    vertices: list of (x, y) tuples
    """
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1] - vertices[j][0] * vertices[i][1]
    return abs(area) / 2.0

def validate_polygon_vertices(raw_polygon: Any) -> Tuple[bool, Optional[str], List[Dict[str, float]]]:
    """
    Validates a single polygon's vertices:
    1. Must be a non-empty list of at least 3 vertices.
    2. Coordinates must be finite numeric values within [0.0, 1.0].
    3. No boolean or non-numeric types.
    4. No duplicate consecutive vertices or zero-length edges (including closing edge).
    5. Non-zero area.
    6. Non-self-intersecting (simple polygon).

    Returns:
      (is_valid, error_message, normalized_vertices)
      where normalized_vertices is [{"x": float, "y": float}, ...]
    """
    if not isinstance(raw_polygon, list):
        return False, "Polygon must be a list of vertices", []

    if len(raw_polygon) < 3:
        return False, f"Polygon must contain at least 3 distinct vertices, got {len(raw_polygon)}", []

    parsed_tuples: List[Tuple[float, float]] = []
    normalized_list: List[Dict[str, float]] = []

    for idx, v in enumerate(raw_polygon):
        if isinstance(v, dict):
            if "x" not in v or "y" not in v:
                return False, f"Vertex at index {idx} missing 'x' or 'y' coordinate", []
            x_raw = v["x"]
            y_raw = v["y"]
        elif isinstance(v, (list, tuple)) and len(v) >= 2:
            x_raw = v[0]
            y_raw = v[1]
        else:
            return False, f"Vertex at index {idx} must be a dict with 'x' and 'y' or a 2-element list", []

        # Reject booleans (in Python, bool is a subclass of int)
        if isinstance(x_raw, bool) or isinstance(y_raw, bool):
            return False, f"Vertex at index {idx} coordinates cannot be boolean", []

        # Validate numeric
        if not isinstance(x_raw, (int, float)) or not isinstance(y_raw, (int, float)):
            return False, f"Vertex at index {idx} coordinates must be numeric", []

        # Validate finite
        try:
            x_f = float(x_raw)
            y_f = float(y_raw)
        except (ValueError, TypeError):
            return False, f"Vertex at index {idx} contains non-numeric coordinates", []

        if math.isnan(x_f) or math.isinf(x_f) or math.isnan(y_f) or math.isinf(y_f):
            return False, f"Vertex at index {idx} contains NaN or infinite coordinates", []

        # Validate range [0.0, 1.0]
        if not (0.0 <= x_f <= 1.0) or not (0.0 <= y_f <= 1.0):
            return False, f"Vertex at index {idx} coordinates ({x_f}, {y_f}) out of bounds; must be within [0.0, 1.0]", []

        parsed_tuples.append((x_f, y_f))
        normalized_list.append({"x": round(x_f, 6), "y": round(y_f, 6)})

    n = len(parsed_tuples)

    # Check for consecutive duplicate vertices and zero-length edges (including closing edge)
    eps = 1e-7
    for i in range(n):
        j = (i + 1) % n
        dx = abs(parsed_tuples[i][0] - parsed_tuples[j][0])
        dy = abs(parsed_tuples[i][1] - parsed_tuples[j][1])
        if dx < eps and dy < eps:
            if j == 0 and i == n - 1:
                return False, "Polygon closing edge has zero length (first and last vertex are identical; polygon is implicitly closed)", []
            return False, f"Polygon contains duplicate consecutive vertices or zero-length edges between vertex {i} and {j}", []

    # Check total distinct vertices
    distinct = set((round(x, 6), round(y, 6)) for x, y in parsed_tuples)
    if len(distinct) < 3:
        return False, f"Polygon must contain at least 3 distinct vertices, got {len(distinct)}", []

    # Check self-intersection for non-adjacent edges first (before area calculation,
    # as symmetrical self-intersecting bowties can have canceling signed areas)
    if n >= 4:
        for i in range(n):
            a = parsed_tuples[i]
            b = parsed_tuples[(i + 1) % n]
            for j in range(i + 1, n):
                # Skip adjacent edges (which share a vertex by definition)
                if (i + 1) % n == j or (j + 1) % n == i:
                    continue

                c = parsed_tuples[j]
                d = parsed_tuples[(j + 1) % n]

                if segments_intersect(a, b, c, d):
                    return False, f"Polygon is self-intersecting: edge {i} intersects non-adjacent edge {j}", []

    # Check non-zero area (Shoelace formula)
    area = compute_polygon_area(parsed_tuples)
    if area < 1e-7:
        return False, f"Polygon has zero or degenerate area ({area:.8f})", []

    return True, None, normalized_list

def lookup_zone(zone_id: Any) -> Optional[Dict[str, Any]]:
    """
    Finds a zone by ID in MongoDB or in-memory fallback.
    Returns zone dict or None.
    """
    if zone_id is None:
        return None
    str_id = str(zone_id).strip()
    if not str_id:
        return None

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_zones_col()
            query = {"$or": [{"_id": str_id}]}
            try:
                query["$or"].append({"_id": ObjectId(str_id)})
            except Exception:
                pass
            found = col.find_one(query)
            if found:
                found["_id"] = str(found["_id"])
                return found
        except Exception:
            pass

    found = next((z for z in mem_zones if str(z.get("_id")) == str_id), None)
    if found:
        return found
    return None

def validate_camera_zone_mappings(raw_zones: Any) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
    """
    Validates a list of camera-to-zone polygon mappings:
    1. Must be a list.
    2. Each entry must have 'zoneId' and 'polygon'.
    3. 'zoneId' must reference an existing zone.
    4. No duplicate zone mappings for the same camera.
    5. 'polygon' must be valid per validate_polygon_vertices.
    6. 'priority' must be an integer (defaults to 1).

    Returns:
      (is_valid, error_message, validated_mappings)
    """
    if raw_zones is None:
        return True, None, []

    if not isinstance(raw_zones, list):
        return False, "Zone configuration must be a list of zone mappings", []

    validated_mappings: List[Dict[str, Any]] = []
    seen_zones = set()

    for idx, mapping in enumerate(raw_zones):
        if not isinstance(mapping, dict):
            return False, f"Zone mapping at index {idx} must be a dictionary", []

        zone_id = mapping.get("zoneId")
        if not zone_id or not isinstance(zone_id, (str, int)):
            return False, f"Zone mapping at index {idx} missing or invalid 'zoneId'", []

        str_zid = str(zone_id).strip()
        if not str_zid:
            return False, f"Zone mapping at index {idx} has empty 'zoneId'", []

        # Reject duplicate zone mappings for the same camera
        if str_zid in seen_zones:
            return False, f"Duplicate zone mapping for zoneId '{str_zid}' on camera", []
        seen_zones.add(str_zid)

        # Validate that referenced zoneId exists
        zone_doc = lookup_zone(str_zid)
        if not zone_doc:
            return False, f"Referenced zoneId '{str_zid}' does not exist", []

        # Validate priority
        priority_val = mapping.get("priority", 1)
        if isinstance(priority_val, bool) or not isinstance(priority_val, int):
            return False, f"Priority at index {idx} must be an integer, got {type(priority_val).__name__}", []
        if priority_val < 0:
            return False, f"Priority at index {idx} must be a non-negative integer", []

        # Validate polygon
        raw_poly = mapping.get("polygon")
        if raw_poly is None:
            return False, f"Zone mapping at index {idx} missing 'polygon'", []

        is_valid_poly, err, norm_poly = validate_polygon_vertices(raw_poly)
        if not is_valid_poly:
            return False, f"Invalid polygon for zone '{str_zid}': {err}", []

        validated_mappings.append({
            "zoneId": str_zid,
            "zoneName": zone_doc.get("name", "Monitored Zone"),
            "polygon": norm_poly,
            "priority": int(priority_val)
        })

    return True, None, validated_mappings
