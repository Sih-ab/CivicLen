from road_matching import find_nearest_roads, match_report_to_road

# Existing reports whose RoadID is currently NULL.
# This script only tests matches; it does NOT update SQL Server.
reports = [
    {"ReportID": 1, "Latitude": 24.364840, "Longitude": 88.600095},
    {"ReportID": 2, "Latitude": 24.374830, "Longitude": 88.621979},
    {"ReportID": 4, "Latitude": 24.368339, "Longitude": 88.581116},
    {"ReportID": 5, "Latitude": 24.361722, "Longitude": 88.626882},
    {"ReportID": 7, "Latitude": 24.364769, "Longitude": 88.607374},
    {"ReportID": 8, "Latitude": 24.364769, "Longitude": 88.607374},
    {"ReportID": 9, "Latitude": 24.364769, "Longitude": 88.607374},
    {"ReportID": 10, "Latitude": 24.375092, "Longitude": 88.622291},
    {"ReportID": 12, "Latitude": 24.361722, "Longitude": 88.626882},
]

print("\nROAD MATCHING TEST — NO DATABASE CHANGES")
print("=" * 72)

for report in reports:
    report_id = report["ReportID"]
    lat = report["Latitude"]
    lon = report["Longitude"]

    print(f"\nReport {report_id} | Latitude: {lat} | Longitude: {lon}")
    candidates = find_nearest_roads(lat, lon, limit=3)

    if not candidates:
        print("No road candidates found.")
        continue

    print("Nearest road candidates:")
    for rank, road in enumerate(candidates, start=1):
        print(
            f"  {rank}. OSMID={road['OSMID']} | "
            f"Type={road['RoadType']} | "
            f"Name={road['RoadName']} | "
            f"Distance={road['DistanceMeters']} m"
        )

    result = match_report_to_road(lat, lon)
    print(f"Decision: {'AUTO-MATCH CANDIDATE' if result['matched'] else 'MANUAL REVIEW'}")
    print(f"Reason: {result['reason']}")
    if result["matched"]:
        print(
            f"Suggested OSMID: {result['road']['OSMID']} "
            f"({result['road']['DistanceMeters']} m)"
        )

print("\nTest completed. No database records were changed.")
