import sqlite3

conn = sqlite3.connect("anime.db")
c = conn.cursor()
c.execute("ALTER TABLE episode ADD COLUMN line_id TEXT;")
conn.commit()
conn.close()