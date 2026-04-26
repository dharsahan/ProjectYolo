import sqlite3
import os

db_path = "yolo_v2.db"
if not os.path.exists(db_path):
    print("DB NOT FOUND")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT task_id, status, created_at FROM background_tasks ORDER BY created_at DESC LIMIT 10")
    print(cur.fetchall())
    conn.close()
