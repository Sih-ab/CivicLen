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

# Connect to database
conn = pyodbc.connect(connection_string)
cursor = conn.cursor()

# Load RCC boundary
with open("rcc_boundary.geojson", "r", encoding="utf-8") as file:
    geojson_data = json.load(file)

boundary = shape(geojson_data["features"][0]["geometry"])

# Fetch roads
cursor.execute("""
    SELECT RoadID, Latitude, Longitude
    FROM Roads
""")

roads = cursor.fetchall()

inside_count = 0
outside_count = 0
invalid_count = 0

inside_roads = []

for road in roads:
    road_id, latitude, longitude = road

    if latitude is None or longitude is None:
        invalid_count += 1
        continue

    point = Point(float(longitude), float(latitude))

    if boundary.covers(point):
        inside_count += 1
        inside_roads.append(road_id)
    else:
        outside_count += 1

print("\n===== RAJSHAHI CITY CORPORATION ROAD ANALYSIS =====")
print("Total Roads:", len(roads))
print("Inside RCC Boundary:", inside_count)
print("Outside RCC Boundary:", outside_count)
print("Invalid Coordinates:", invalid_count)

print("\nFirst 20 Roads Inside RCC:")
print(inside_roads[:20])

cursor.close()
conn.close()