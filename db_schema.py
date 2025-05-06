import sqlite3

conn = sqlite3.connect("anime.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS anime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    cover TEXT,
    intro TEXT,
    update_time TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS episode (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id INTEGER,
    title TEXT,
    play_url TEXT,
    FOREIGN KEY(anime_id) REFERENCES anime(id)
)
""")
conn.commit()
conn.close()