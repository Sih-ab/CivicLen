import json
import re
from functools import lru_cache

from shapely import transform
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from pyproj import Transformer


# Rajshahi: UTM Zone 45N
# Converts GPS coordinates into meters
projector = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32645",
    always_xy=True
)


def get_numeric_osmid(osm_id):
    """
    Convert OSM ID such as way/1559375714
    into numeric ID.
    """

    if not osm_id:
        return None

    match = re.search(r"(\d+)$", str(osm_id))

    if match:
        return int(match.group(1))

    return None


@lru_cache(maxsize=1)
def load_roads(geojson_path="export.geojson"):
    """
    Load road geometries clipped to Rajshahi City Corporation boundary.
    All distance calculations use metric coordinates.
    """

    # Load RCC ward boundaries
    ward_path = "rcc_wards.geojson"

    with open(ward_path, "r", encoding="utf-8") as file:
        ward_data = json.load(file)

    ward_polygons = [
        shape(feature["geometry"])
        for feature in ward_data.get("features", [])
        if feature.get("geometry")
    ]

    # Combine all wards into one RCC boundary
    rcc_boundary = unary_union(ward_polygons)

    # Convert RCC boundary into metric coordinates
    rcc_boundary_metric = transform(
        rcc_boundary,
        projector.transform,
        interleaved=False
    )

    # Load road GeoJSON
    with open(geojson_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    roads = []

    total_roads = 0
    included_roads = 0
    clipped_roads = 0

    for feature in data.get("features", []):

        properties = feature.get("properties", {})
        geometry_data = feature.get("geometry")

        if not geometry_data:
            continue

        osm_id = get_numeric_osmid(properties.get("@id"))

        if osm_id is None:
            continue

        try:
            geometry = shape(geometry_data)

            if geometry.geom_type != "LineString":
                continue

            total_roads += 1

            # Convert road geometry into metric coordinates
            metric_geometry = transform(
                geometry,
                projector.transform,
                interleaved=False
            )

            # Keep only the part inside RCC boundary
            clipped_geometry = metric_geometry.intersection(
                rcc_boundary_metric
            )

            if clipped_geometry.is_empty:
                continue

            if clipped_geometry.geom_type not in {
                "LineString",
                "MultiLineString"
            }:
                continue

            included_roads += 1

            if clipped_geometry.geom_type == "MultiLineString":
                clipped_roads += 1

            roads.append({
                "OSMID": osm_id,
                "RoadName": properties.get("name"),
                "RoadType": properties.get("highway"),
                "geometry": clipped_geometry,
                "geojson_geometry": geometry_data
            })

        except Exception as error:
            print(f"Skipping OSM ID {osm_id}: {error}")

    print(f"Total source roads: {total_roads}")
    print(f"Roads inside RCC boundary: {included_roads}")
    print(f"Roads with clipped geometry: {clipped_roads}")

    return roads

def find_nearest_roads(latitude, longitude, limit=2):
    """
    Find nearest roads from a report location.
    Distance is calculated in meters.
    """

    roads = load_roads()

    # Convert report GPS coordinates into meters
    x, y = projector.transform(
        longitude,
        latitude
    )

    report_point = Point(x, y)

    results = []

    for road in roads:

        distance = report_point.distance(
            road["geometry"]
        )

        results.append({
            "OSMID": road["OSMID"],
            "RoadName": road["RoadName"],
            "RoadType": road["RoadType"],
            "DistanceMeters": round(distance, 2)
        })

    # Sort roads by distance
    results.sort(
        key=lambda item: item["DistanceMeters"]
    )

    return results[:limit]

def match_report_to_road(latitude, longitude):
    """
    Match a report to an RCC road using distance
    and confidence-based classification.
    """

    nearest = find_nearest_roads(
        latitude,
        longitude,
        limit=2
    )

    if not nearest:
        return {
            "matched": False,
            "confidence": "Low",
            "reason": "No road candidates found",
            "road": None,
            "candidates": []
        }

    first = nearest[0]

    if len(nearest) < 2:
        return {
            "matched": False,
            "confidence": "Low",
            "reason": "Not enough road candidates",
            "road": None,
            "candidates": nearest
        }

    second = nearest[1]

    distance = first["DistanceMeters"]

    distance_gap = (
        second["DistanceMeters"] - distance
    )

    # HIGH CONFIDENCE
    if (
        distance <= 1.5
        and distance_gap >= 3.0
    ):
        return {
            "matched": True,
            "confidence": "High",
            "reason": "High-confidence match",
            "road": first,
            "candidates": nearest,
            "distance_gap": round(distance_gap, 2)
        }

    # MODERATE CONFIDENCE
    if (
        distance <= 5.0
        and distance_gap >= 3.0
    ):
        return {
            "matched": False,
            "confidence": "Moderate",
            "reason": "Potential match - manual review required",
            "road": first,
            "candidates": nearest,
            "distance_gap": round(distance_gap, 2)
        }

    # LOW CONFIDENCE
    return {
        "matched": False,
        "confidence": "Low",
        "reason": "Low-confidence match - manual review required",
        "road": None,
        "candidates": nearest,
        "distance_gap": round(distance_gap, 2)
    }


# ==========================================
# TESTING
# ==========================================

if __name__ == "__main__":

    test_reports = [
        {
            "ReportID": 3,
            "Latitude": 24.363535,
            "Longitude": 88.604349,
            "ExistingRoadID": 183
        },
        {
            "ReportID": 6,
            "Latitude": 24.375785,
            "Longitude": 88.593102,
            "ExistingRoadID": 1556
        },
        {
            "ReportID": 11,
            "Latitude": 24.376786,
            "Longitude": 88.588811,
            "ExistingRoadID": 189
        },
        {
            "ReportID": 17,
            "Latitude": 24.376818,
            "Longitude": 88.617885,
            "ExistingRoadID": None
        },
        {
            "ReportID": 18,
            "Latitude": 24.377074,
            "Longitude": 88.618021,
            "ExistingRoadID": None
        }



    ]

    for report in test_reports:

        print("\n" + "=" * 45)
        print(f"REPORT ID: {report['ReportID']}")
        print("=" * 45)

        print(
            "Existing RoadID:",
            report["ExistingRoadID"]
        )

        candidates = find_nearest_roads(
            report["Latitude"],
            report["Longitude"],
            limit=2
        )

        print("Nearest Road Candidates:")

        for candidate in candidates:
            print(candidate)



        result = match_report_to_road(
            report["Latitude"],
            report["Longitude"]
        )

        print("Matched:", result["matched"])
        print("Confidence:", result["confidence"])
        print("Reason:", result["reason"])

        if result["road"]:

            print(
                "Suggested OSM ID:",
                result["road"]["OSMID"]
            )

            print(
                "Distance:",
                result["road"]["DistanceMeters"],
                "meters"
            )

        else:

            print("Manual Review Required")

    # ==========================================
    # CONTROLLED MODERATE CONFIDENCE TEST
    # ==========================================

    print("\n" + "=" * 45)
    print("CONTROLLED MODERATE CONFIDENCE TEST")
    print("=" * 45)

    original_find_nearest_roads = find_nearest_roads

    def test_nearest_roads(latitude, longitude, limit=2):
        return [
            {
                "OSMID": 111111,
                "RoadName": "Test Road A",
                "RoadType": "tertiary",
                "DistanceMeters": 4.0
            },
            {
                "OSMID": 222222,
                "RoadName": "Test Road B",
                "RoadType": "secondary",
                "DistanceMeters": 8.0
            }
        ]

    try:
        find_nearest_roads = test_nearest_roads

        test_result = match_report_to_road(24.370000, 88.600000)

        print("Matched:", test_result["matched"])
        print("Confidence:", test_result["confidence"])
        print("Reason:", test_result["reason"])
        print("Distance:", test_result["road"]["DistanceMeters"])
        print("Distance Gap:", test_result["distance_gap"])

    finally:
        find_nearest_roads = original_find_nearest_roads