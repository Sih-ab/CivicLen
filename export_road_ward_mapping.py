import pyodbc
import json
import csv
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

wards = []

for feature in ward_data["features"]:
    properties = feature["properties"]

    wards.append({
        "ward_number": properties.get("ward_name"),
        "ward_code": properties.get("adm5_pcode"),
        "polygon": shape(feature["geometry"])
    })

# Fetch road coordinates
cursor.execute("""
    SELECT RoadID, Latitude, Longitude
    FROM Roads
""")

roads = cursor.fetchall()

mapping_data = []

for road in roads:
    road_id, latitude, longitude = road

    if latitude is None or longitude is None:
        continue

    point = Point(float(longitude), float(latitude))

    matching_wards = [
        ward for ward in wards
        if ward["polygon"].covers(point)
    ]

    if len(matching_wards) == 1:
        ward = matching_wards[0]

        mapping_data.append({
            "RoadID": road_id,
            "WardNumber": ward["ward_number"],
            "WardCode": ward["ward_code"]
        })

# Export CSV
with open(
    "road_ward_mapping.csv",
    "w",
    newline="",
    encoding="utf-8"
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=["RoadID", "WardNumber", "WardCode"]
    )

    writer.writeheader()
    writer.writerows(mapping_data)

cursor.close()
conn.close()

print("\n===== ROAD WARD EXPORT COMPLETED =====")
print("Total Roads:", len(roads))
print("Mapped Roads:", len(mapping_data))
print("CSV File: road_ward_mapping.csv")