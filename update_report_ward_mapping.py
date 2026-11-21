import json
import pyodbc
from shapely.geometry import shape, Point

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=SIHAB\\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
)

# Load Ward GeoJSON
with open("rcc_wards.geojson", "r", encoding="utf-8") as file:
    geojson_data = json.load(file)

wards = []

for feature in geojson_data["features"]:
    ward_number = feature["properties"].get("ward_name")
    polygon = shape(feature["geometry"])

    wards.append({
        "ward_number": str(ward_number),
        "polygon": polygon
    })

print(f"Loaded Ward Polygons: {len(wards)}")

connection = pyodbc.connect(CONNECTION_STRING)
cursor = connection.cursor()

cursor.execute("""
    SELECT ReportID, Latitude, Longitude
    FROM dbo.Reports
""")

reports = cursor.fetchall()

updated_count = 0
outside_count = 0

for report in reports:
    report_id = report.ReportID
    latitude = report.Latitude
    longitude = report.Longitude

    if latitude is None or longitude is None:
        outside_count += 1
        continue

    point = Point(float(longitude), float(latitude))

    matched_wards = [
        ward["ward_number"]
        for ward in wards
        if ward["polygon"].covers(point)
    ]

    if len(matched_wards) == 1:
        cursor.execute("""
            UPDATE dbo.Reports
            SET WardNumber = ?
            WHERE ReportID = ?
        """, matched_wards[0], report_id)

        updated_count += 1

    else:
        outside_count += 1

connection.commit()

cursor.close()
connection.close()

print("\n========== UPDATE SUMMARY ==========")
print(f"Total Reports: {len(reports)}")
print(f"Successfully Updated: {updated_count}")
print(f"Outside / Unmatched: {outside_count}")
print("Database update completed.")