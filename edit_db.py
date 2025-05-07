import sqlite3

conn = sqlite3.connect("anime.db")  # 路径改成你的数据库文件
c = conn.cursor()
try:
    c.execute("CREATE UNIQUE INDEX idx_episode_unique ON episode(anime_id, title, play_url, line_id);")
    print("唯一索引创建成功")
except Exception as e:
    print("创建唯一索引时出错：", e)
conn.commit()
conn.close()