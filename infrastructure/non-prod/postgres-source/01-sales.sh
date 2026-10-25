#!/bin/sh
# Test source for Phase 2. Runs once, on the first start of an empty volume.
# Same model as the SQL Server sample (crm): segments, 10,000 customers, and an empty orders table that
# seed-large.sh fills with ~10M rows for throughput tests.
set -eu

psql -v ON_ERROR_STOP=1 --username postgres --dbname sales <<EOSQL
CREATE TABLE segments (
  segment_id   INT          PRIMARY KEY,
  segment_name VARCHAR(100) NOT NULL
);

CREATE TABLE customers (
  customer_id INT          PRIMARY KEY,
  full_name   VARCHAR(200) NOT NULL,
  email       VARCHAR(320),
  segment_id  INT          NOT NULL REFERENCES segments (segment_id),
  is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMP(3) NOT NULL,
  updated_at  TIMESTAMP(3) NOT NULL
);

CREATE TABLE orders (
  order_id    BIGINT        PRIMARY KEY,
  customer_id INT           NOT NULL,
  amount      NUMERIC(12,2) NOT NULL,
  status      VARCHAR(20)   NOT NULL,
  created_at  TIMESTAMP(3)  NOT NULL
);

INSERT INTO segments VALUES (1, 'Retail'), (2, 'SME'), (3, 'Enterprise');

INSERT INTO customers
SELECT i, 'Customer ' || i, 'customer' || i || '@example.com', i % 3 + 1, i % 50 = 0,
       now() - make_interval(mins => i * 7), now() - make_interval(mins => i)
FROM generate_series(1, 10000) AS i;

-- Dedicated read-only role, as every connection requires (architecture §3.7).
CREATE ROLE svc_ingest_ro LOGIN PASSWORD '${RO_PASSWORD}';
ALTER ROLE svc_ingest_ro SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE sales TO svc_ingest_ro;
GRANT USAGE ON SCHEMA public TO svc_ingest_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO svc_ingest_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO svc_ingest_ro;
EOSQL
