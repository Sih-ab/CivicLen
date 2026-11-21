import json
from shapely.geometry import shape

# Load Rajshahi City Corporation boundary
with open("rcc_boundary.geojson", "r", encoding="utf-8") as file:
    geojson_data = json.load(file)

# Extract polygon geometry
features = geojson_data.get("features", [])

if not features:
    print("ERROR: No boundary features found.")

else:
    for feature in features:
        geometry = shape(feature["geometry"])

        print("Boundary Test Successful!")
        print("Geometry Type:", geometry.geom_type)
        print("Is Valid:", geometry.is_valid)
        print("Area:", geometry.area)
        print("Bounds:", geometry.bounds)