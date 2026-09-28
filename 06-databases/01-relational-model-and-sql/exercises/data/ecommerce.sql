-- 6.1 演習用の EC サイトのデータ（SQLite 用）
-- 読み込み方: python3 -c "import sql_practice as s; s.print_query('SELECT * FROM customers')"
--   または sqlite3 CLI で: sqlite3 shop.db < data/ecommerce.sql
PRAGMA foreign_keys = ON;

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  email       TEXT NOT NULL UNIQUE,
  prefecture  TEXT,                    -- 未登録なら NULL
  created_at  TEXT NOT NULL            -- 'YYYY-MM-DD'
);

CREATE TABLE categories (
  category_id INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  parent_id   INTEGER REFERENCES categories (category_id)   -- 最上位なら NULL
);

CREATE TABLE products (
  product_id  INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  category_id INTEGER NOT NULL REFERENCES categories (category_id),
  price       INTEGER NOT NULL CHECK (price >= 0)          -- 現在の価格（円）
);

CREATE TABLE orders (
  order_id    INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers (customer_id),
  ordered_at  TEXT NOT NULL,                                -- 'YYYY-MM-DD HH:MM:SS'（UTC）
  status      TEXT NOT NULL CHECK (status IN ('paid', 'shipped', 'cancelled'))
);

CREATE TABLE order_items (
  order_id    INTEGER NOT NULL REFERENCES orders (order_id),
  product_id  INTEGER NOT NULL REFERENCES products (product_id),
  quantity    INTEGER NOT NULL CHECK (quantity > 0),
  unit_price  INTEGER NOT NULL CHECK (unit_price >= 0),     -- 購入時点の単価（円）
  PRIMARY KEY (order_id, product_id)
);

INSERT INTO customers VALUES
  (1,  '佐藤 花子',   'hanako@example.com',  '東京都', '2025-01-05'),
  (2,  '鈴木 一郎',   'ichiro@example.com',  '大阪府', '2025-01-12'),
  (3,  '高橋 美咲',   'misaki@example.com',  '東京都', '2025-02-01'),
  (4,  '田中 健太',   'kenta@example.com',   NULL,     '2025-02-14'),
  (5,  '伊藤 さくら', 'sakura@example.com',  '福岡県', '2025-03-03'),
  (6,  '渡辺 大輔',   'daisuke@example.com', '北海道', '2025-03-20'),
  (7,  '山本 結衣',   'yui@example.com',     NULL,     '2025-04-02'),
  (8,  '中村 翔',     'sho@example.com',     '愛知県', '2025-04-18'),
  (9,  '小林 陽菜',   'hina@example.com',    '東京都', '2025-05-09'),
  (10, '加藤 蓮',     'ren@example.com',     '大阪府', '2025-05-30');

INSERT INTO categories VALUES
  (1,  '本',             NULL),
  (2,  'コンピュータ',   1),
  (3,  'データベース',   2),
  (4,  'プログラミング', 2),
  (5,  '小説',           1),
  (6,  '家電',           NULL),
  (7,  'オーディオ',     6),
  (8,  'ヘッドホン',     7),
  (9,  'キッチン',       6),
  (10, 'ギフトカード',   NULL);

INSERT INTO products VALUES
  (1,  'データベース実践入門', 3, 3200),
  (2,  'SQL 徹底ガイド',       3, 3200),
  (3,  'Python 入門',          4, 2400),
  (4,  'Go 言語の基礎',        4, 3000),
  (5,  '長い夜の物語',         5, 1500),
  (6,  '春の旅',               5, 1200),
  (7,  'ワイヤレスイヤホン X1', 7, 9800),
  (8,  'ヘッドホン H200',      8, 15800),
  (9,  'ヘッドホン H100',      8, 8800),
  (10, '電気ケトル K1',        9, 4500),
  (11, 'ホットサンドメーカー', 9, 3800),
  (12, '分散システム論',       3, 4200);

INSERT INTO orders VALUES
  (1,  1, '2025-01-10 10:00:00', 'shipped'),
  (2,  2, '2025-01-15 12:30:00', 'shipped'),
  (3,  1, '2025-01-28 09:15:00', 'shipped'),
  (4,  3, '2025-02-03 20:00:00', 'shipped'),
  (5,  4, '2025-02-10 08:45:00', 'cancelled'),
  (6,  5, '2025-02-18 19:20:00', 'shipped'),
  (7,  2, '2025-02-25 13:00:00', 'shipped'),
  (8,  1, '2025-03-05 11:11:00', 'shipped'),
  (9,  6, '2025-03-12 22:05:00', 'shipped'),
  (10, 8, '2025-03-15 10:00:00', 'cancelled'),
  (11, 3, '2025-03-28 18:30:00', 'shipped'),
  (12, 9, '2025-04-02 07:50:00', 'shipped'),
  (13, 4, '2025-04-11 21:40:00', 'shipped'),
  (14, 5, '2025-04-20 16:00:00', 'shipped'),
  (15, 2, '2025-05-03 12:00:00', 'paid'),
  (16, 6, '2025-05-09 09:30:00', 'cancelled'),
  (17, 1, '2025-05-21 15:45:00', 'paid'),
  (18, 9, '2025-05-30 23:59:00', 'paid'),
  (19, 3, '2025-06-02 10:10:00', 'paid'),
  (20, 5, '2025-06-15 14:00:00', 'paid');

INSERT INTO order_items VALUES
  (1,  1,  1, 3200), (1, 3, 1, 2400),
  (2,  8,  1, 15800),
  (3,  5,  2, 1500),
  (4,  2,  1, 3200), (4, 1, 1, 3200),
  (5,  10, 1, 4500),
  (6,  7,  1, 9800),
  (7,  11, 1, 3800), (7, 10, 1, 4500),
  (8,  4,  1, 3000),
  (9,  9,  1, 8800),
  (10, 8,  1, 15800),
  (11, 6,  2, 1200), (11, 5, 1, 1500),
  (12, 1,  2, 3200),
  (13, 3,  1, 2400), (13, 2, 1, 3200),
  (14, 9,  1, 7800),
  (15, 8,  1, 15800),
  (16, 10, 1, 4500),
  (17, 10, 1, 4500), (17, 11, 1, 3800),
  (18, 4,  2, 3000), (18, 2, 2, 3200),
  (19, 7,  1, 9800),
  (20, 6,  1, 1200), (20, 5, 1, 1500);
