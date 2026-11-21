import json
from shapely.geometry import shape

# Load Ward GeoJSON
with open("rcc_wards.geojson", "r", encoding="utf-8") as file:
    data = json.load(file)

features = data.get("features", [])

print("\n===== RAJSHAHI WARD BOUNDARY TEST =====")

print("Total Ward Features:", len(features))

for index, feature in enumerate(features, start=1):

    geometry = shape(feature["geometry"])
    properties = feature.get("properties", {})

    print(f"\nWard Feature {index}")
    print("Geometry Type:", geometry.geom_type)
    print("Geometry Valid:", geometry.is_valid)
    print("Properties:", properties)

print("\n===== TEST COMPLETED =====")