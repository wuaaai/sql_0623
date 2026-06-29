"""创建测试数据库 (SQLite)"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "temp", "test.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)

conn.executescript("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    age INTEGER,
    city TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    price REAL,
    stock INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER,
    amount REAL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);

INSERT INTO users (name, email, age, city) VALUES
('张三', 'zhangsan@example.com', 28, '北京'),
('李四', 'lisi@example.com', 35, '上海'),
('王五', 'wangwu@example.com', 22, '广州'),
('赵六', 'zhaoliu@example.com', 42, '深圳'),
('孙七', 'sunqi@example.com', 31, '北京'),
('周八', 'zhouba@example.com', 26, '上海');

INSERT INTO products (name, category, price, stock) VALUES
('笔记本电脑', '电子产品', 5999.00, 50),
('无线鼠标', '电子产品', 99.00, 200),
('机械键盘', '电子产品', 399.00, 150),
('Python编程书', '图书', 79.00, 80),
('SQL入门指南', '图书', 59.00, 60),
('办公椅', '家具', 899.00, 30);

INSERT INTO orders (user_id, product_id, quantity, amount, status, created_at) VALUES
(1, 1, 1, 5999.00, '已完成', '2026-06-01'),
(1, 2, 2, 198.00, '已完成', '2026-06-02'),
(2, 1, 1, 5999.00, '已完成', '2026-06-03'),
(2, 4, 3, 237.00, '已完成', '2026-06-05'),
(3, 2, 1, 99.00, '已取消', '2026-06-10'),
(3, 3, 1, 399.00, '已完成', '2026-06-12'),
(4, 6, 2, 1798.00, '已完成', '2026-06-15'),
(5, 5, 1, 59.00, '已完成', '2026-06-18'),
(6, 1, 1, 5999.00, '进行中', '2026-06-20'),
(2, 3, 1, 399.00, '已完成', '2026-06-21');
""")

conn.commit()
conn.close()
print(f"测试数据库已创建: {db_path}")
print("表: users(6行), products(6行), orders(10行)")
