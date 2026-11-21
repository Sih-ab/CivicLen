
import json
from pathlib import Path
import pyodbc

# 1. Load the GeoJSON dataset
file_path = Path(r"C:\Users\mdsih\Downloads\export.geojson")

with file_path.open("r", encoding="utf-8") as file:
    data = json.load(file)

features = data.get("features", [])

# 2. Prepare road records
roads = []
seen_osm_ids = set()

for feature in features:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}

    if geometry.get("type") != "LineString":
        continue

    osm_id = properties.get("@id", "")

    if not osm_id.startswith("way/"):
        continue

    try:
        numeric_osm_id = int(osm_id.split("/")[-1])
    except ValueError:
        continue

    if numeric_osm_id in seen_osm_ids:
        continue

    coordinates = geometry.get("coordinates", [])

    if not coordinates:
        continue

    longitude, latitude = coordinates[0][:2]

    roads.append((
        numeric_osm_id,
        properties.get("name"),
        properties.get("highway"),
        latitude,
        longitude,
    ))

    seen_osm_ids.add(numeric_osm_id)

print("Prepared road records:", len(roads))

# 3. Connect to SQL Server
connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=SIHAB\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

connection = pyodbc.connect(connection_string)

try:
    cursor = connection.cursor()

    # 4. Insert roads, skipping OSM IDs already in the table
    cursor.fast_executemany = True

    cursor.executemany(
        """
        INSERT INTO dbo.Roads
            (OSMID, RoadName, RoadType, Latitude, Longitude)
        SELECT ?, ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1
            FROM dbo.Roads
            WHERE OSMID = ?
        );
        """,
        [
            (osm_id, name, road_type, lat, lon, osm_id)
            for osm_id, name, road_type, lat, lon in roads
        ],
    )

    connection.commit()

    cursor.execute("SELECT COUNT(*) FROM dbo.Roads")
    total_roads = cursor.fetchone()[0]

    print("Import completed successfully!")
    print("Total roads in database:", total_roads)

finally:
    connection.close()
