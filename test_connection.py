
import pyodbc

connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=SIHAB\SQLEXPRESS;"
    "DATABASE=CivicLenDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

try:
    connection = pyodbc.connect(connection_string)
    print("Successfully connected to CivicLenDB!")

    cursor = connection.cursor()
    cursor.execute("SELECT DB_NAME()")

    print("Connected database:", cursor.fetchone()[0])

    connection.close()

except Exception as error:
    print("Connection failed:")
    print(error)
