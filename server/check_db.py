import sqlite3

conn = sqlite3.connect("health_monitoring.db")
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(sensor_data)")
columns = cursor.fetchall()

print("📋 Colonne della tabella sensor_data:")
for col in columns:
    print(col)

conn.close()
