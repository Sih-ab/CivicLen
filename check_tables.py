
import pyodbc

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=SIHAB\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

try:
    with pyodbc.connect(CONNECTION_STRING) as connection:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT Role, COUNT(*) AS TotalUsers
            FROM dbo.Users
            GROUP BY Role
            ORDER BY Role;
        """)

        rows = cursor.fetchall()

        print("\n=== Existing User Roles ===")

        if not rows:
            print("No users registered yet.")

        for role, count in rows:
            print(f"Role: {role} | Users: {count}")

except Exception as error:
    print("Database error:", error)
