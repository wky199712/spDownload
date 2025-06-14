import sqlite3

conn = sqlite3.connect("anime.db")
c = conn.cursor()
# 清空 anime 表
c.execute("DELETE FROM anime")
# 清空 episode 表
c.execute("DELETE FROM episode")
conn.commit()
conn.close()
print("anime.db 已清空！")