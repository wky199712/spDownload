import sqlite3

# 连接数据库
conn = sqlite3.connect("anime.db")
c = conn.cursor()

# 查看所有表名
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = c.fetchall()
print("数据库中的表：")
for table in tables:
    print(f"- {table[0]}")

print("\n" + "="*50)

# 查看 anime 表的字段结构
try:
    c.execute("PRAGMA table_info(anime)")
    columns = c.fetchall()

    print("anime 表的字段结构：")
    print("序号 | 字段名 | 数据类型 | 是否非空 | 默认值 | 是否主键")
    print("-" * 60)
    for column in columns:
        print(
            f"{column[0]:4} | {column[1]:15} | {column[2]:10} | {column[3]:8} | {str(column[4]):8} | {column[5]:8}")
except Exception as e:
    print(f"查看 anime 表失败: {e}")

# 查看 episode 表的字段结构（如果存在）
try:
    c.execute("PRAGMA table_info(episode)")
    columns = c.fetchall()

    print("\nepisode 表的字段结构：")
    print("序号 | 字段名 | 数据类型 | 是否非空 | 默认值 | 是否主键")
    print("-" * 60)
    for column in columns:
        print(
            f"{column[0]:4} | {column[1]:15} | {column[2]:10} | {column[3]:8} | {str(column[4]):8} | {column[5]:8}")
except Exception as e:
    print(f"查看 episode 表失败: {e}")

# 查看一些示例数据
try:
    c.execute("SELECT * FROM anime LIMIT 3")
    rows = c.fetchall()
    print(f"\nanime 表前3条数据示例：")
    for i, row in enumerate(rows, 1):
        print(f"第{i}条: {row}")
except Exception as e:
    print(f"查看示例数据失败: {e}")

conn.close()
