import sqlite3
c = sqlite3.connect('sentinel.db')
print('TABLES:', [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
for t in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()]
    print(f'  {t}: {cols}')