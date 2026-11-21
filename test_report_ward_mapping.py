import json
import pyodbc
from shapely.geometry import shape, Point

# SQL Server connection
CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=SIHAB\\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
)

# Load Ward GeoJSON
with open("rcc_wards.geojson", "r", encoding="utf-8") as file:
    geojson_data = json.load(file)

# Prepare Ward polygons
wards = []

for feature in geojson_data["features"]:
    properties = feature["properties"]

    ward_number = properties.get("ward_name")

    polygon = shape(feature["geometry"])

    wards.append({
        "ward_number": ward_number,
        "polygon": polygon
    })

print(f"Total Ward Polygons Loaded: {len(wards)}")

# Connect to SQL Server
connection = pyodbc.connect(CONNECTION_STRING)
cursor = connection.cursor()

# Read Reports
cursor.execute("""
    SELECT ReportID, IssueType, Latitude, Longitude, Status
    FROM dbo.Reports
    ORDER BY ReportID DESC
""")

reports = cursor.fetchall()

print("\n========== REPORT WARD MAPPING ==========\n")

for report in reports:
    report_id = report.ReportID
    issue_type = report.IssueType
    latitude = report.Latitude
    longitude = report.Longitude
    status = report.Status

    if latitude is None or longitude is None:
        print(f"Report {report_id}: Missing coordinates")
        continue

    point = Point(float(longitude), float(latitude))

    matched_wards = [
        ward["ward_number"]
        for ward in wards
        if ward["polygon"].covers(point)
    ]

    if len(matched_wards) == 1:
        print(
            f"Report ID: {report_id} | "
            f"Issue: {issue_type} | "
            f"Ward: {matched_wards[0]} | "
            f"Status: {status}"
        )

    elif len(matched_wards) == 0:
        print(f"Report ID: {report_id} | Outside all wards")

    else:
        print(
            f"Report ID: {report_id} | "
            f"Multiple matching wards: {matched_wards}"
        )

cursor.close()
connection.close()

print("\n========== TEST COMPLETED ==========")