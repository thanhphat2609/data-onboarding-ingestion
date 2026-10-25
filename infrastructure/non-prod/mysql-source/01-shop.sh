#!/bin/sh
# Test source for Phase 2. Runs once, on the first start of an empty volume (database `shop` exists already).
# Same model as the SQL Server sample (crm): segments, 10,000 customers, and an empty orders table that
# seed-large.sh fills with ~10M rows for throughput tests.
set -eu

mysql --user=root --password="$MYSQL_ROOT_PASSWORD" shop <<EOSQL
CREATE TABLE segments (
  segment_id   INT          PRIMARY KEY,
  segment_name VARCHAR(100) NOT NULL
);

CREATE TABLE customers (
  customer_id INT          PRIMARY KEY,
  full_name   VARCHAR(200) NOT NULL,
  email       VARCHAR(320),
  segment_id  INT          NOT NULL,
  is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at  DATETIME(3)  NOT NULL,
  updated_at  DATETIME(3)  NOT NULL,
  FOREIGN KEY (segment_id) REFERENCES segments (segment_id)
);

CREATE TABLE orders (
  order_id    BIGINT        PRIMARY KEY,
  customer_id INT           NOT NULL,
  amount      DECIMAL(12,2) NOT NULL,
  status      VARCHAR(20)   NOT NULL,
  created_at  DATETIME(3)   NOT NULL
);

INSERT INTO segments VALUES (1, 'Retail'), (2, 'SME'), (3, 'Enterprise');

SET SESSION cte_max_recursion_depth = 10000;
INSERT INTO customers
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 10000)
SELECT i, CONCAT('Customer ', i), CONCAT('customer', i, '@example.com'), i % 3 + 1, i % 50 = 0,
       NOW(3) - INTERVAL (i * 7) MINUTE, NOW(3) - INTERVAL i MINUTE
FROM n;

-- Dedicated read-only user, as every connection requires (architecture §3.7).
CREATE USER 'svc_ingest_ro'@'%' IDENTIFIED BY '${RO_PASSWORD}';
GRANT SELECT ON shop.* TO 'svc_ingest_ro'@'%';
EOSQL
