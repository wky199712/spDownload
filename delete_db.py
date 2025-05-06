import sqlite3
conn = sqlite3.connect("anime.db")
c = conn.cursor()
c.execute("DELETE FROM episode;")
c.execute("DELETE FROM anime;")
conn.commit()
conn.close()