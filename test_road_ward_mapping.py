import pyodbc
import json
from shapely.geometry import shape, Point

# SQL Server connection
connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=SIHAB\\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
)

conn = pyodbc.connect(connection_string)
cursor = conn.cursor()

# Load Ward GeoJSON
with open("rcc_wards.geojson", "r", encoding="utf-8") as file:
    ward_data = json.load(file)

# Prepare Ward polygons
wards = []

for feature in ward_data["features"]:
    properties = feature["properties"]

    wards.append({
        "ward_name": properties.get("ward_name"),
        "polygon": shape(feature["geometry"])
    })

# Fetch road coordinates
cursor.execute("""
    SELECT RoadID, Latitude, Longitude
    FROM Roads
""")

roads = cursor.fetchall()

ward_counts = {
    str(ward["ward_name"]): 0
    for ward in wards
}

outside_count = 0
overlap_count = 0
inside_count = 0

# Match roads with Ward polygons
for road in roads:

    road_id, latitude, longitude = road

    if latitude is None or longitude is None:
        continue

    point = Point(float(longitude), float(latitude))

    matching_wards = [
        ward["ward_name"]
        for ward in wards
        if ward["polygon"].covers(point)
    ]

    if len(matching_wards) == 1:
        ward_counts[str(matching_wards[0])] += 1
        inside_count += 1

    elif len(matching_wards) == 0:
        outside_count += 1

    else:
        overlap_count += 1

# Display results
print("\n===== ROAD TO WARD MAPPING RESULTS =====")

print("Total Roads:", len(roads))
print("Assigned to Ward:", inside_count)
print("Outside All Wards:", outside_count)
print("Multiple Ward Matches:", overlap_count)

print("\n===== WARD-WISE ROAD COUNT =====")

for ward_number in sorted(ward_counts, key=int):
    print(f"Ward {ward_number}: {ward_counts[ward_number]} roads")

cursor.close()
conn.close()