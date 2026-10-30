#!/usr/bin/env bash
# Fills the `orders` table of the test sources with ROWS rows (default 10,000,000) for the Phase 2 throughput
# tests. Run manually once the stack is up; the normal start stays fast. Skips a source that already has the rows.
# Usage: bash infrastructure/non-prod/example-sources/seed-large.sh [sqlserver|postgres|mysql ...]
set -euo pipefail

cd "$(dirname "$0")"
ROWS="${ROWS:-10000000}"
compose=(docker compose -f docker-compose.yml)
if [[ $# -gt 0 ]]; then targets=("$@"); else targets=(sqlserver postgres mysql); fi

seed_sqlserver() {
  "${compose[@]}" exec -T sqlserver bash -c '/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -b -d crm' <<EOSQL
SET NOCOUNT ON;
ALTER DATABASE crm SET RECOVERY SIMPLE;
IF (SELECT COUNT_BIG(*) FROM dbo.orders) < ${ROWS}
BEGIN
  TRUNCATE TABLE dbo.orders;
  WITH n AS (
    SELECT TOP (${ROWS}) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS i
    FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b CROSS JOIN sys.all_objects AS c
  )
  INSERT INTO dbo.orders WITH (TABLOCK) (order_id, customer_id, amount, status, created_at)
  SELECT i, i % 10000 + 1, (i % 100000) / 100.0,
         CHOOSE(i % 4 + 1, 'new', 'paid', 'shipped', 'cancelled'),
         DATEADD(SECOND, -CAST(i AS INT), CAST('2026-10-01' AS DATETIME2(3)))
  FROM n;
END
SELECT COUNT_BIG(*) AS sqlserver_orders FROM dbo.orders;
EOSQL
}

seed_postgres() {
  "${compose[@]}" exec -T postgres-source psql -v ON_ERROR_STOP=1 -U postgres -d sales <<EOSQL
DO \$\$
BEGIN
  IF (SELECT COUNT(*) FROM orders) < ${ROWS} THEN
    TRUNCATE orders;
    INSERT INTO orders
    SELECT i, i % 10000 + 1, (i % 100000) / 100.0,
           (ARRAY['new', 'paid', 'shipped', 'cancelled'])[i % 4 + 1],
           TIMESTAMP '2026-10-01' - make_interval(secs => i)
    FROM generate_series(1, ${ROWS}) AS i;
  END IF;
END \$\$;
ANALYZE orders;
SELECT COUNT(*) AS postgres_orders FROM orders;
EOSQL
}

seed_mysql() {
  "${compose[@]}" exec -T mysql-source bash -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" shop' <<EOSQL
DROP PROCEDURE IF EXISTS seed_orders;
DELIMITER //
CREATE PROCEDURE seed_orders()
BEGIN
  IF (SELECT COUNT(*) FROM orders) < ${ROWS} THEN
    TRUNCATE orders;
    CREATE TEMPORARY TABLE d (i INT PRIMARY KEY);
    INSERT INTO d VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9);
    INSERT INTO orders (order_id, customer_id, amount, status, created_at)
    SELECT n, n % 10000 + 1, (n % 100000) / 100.0,
           ELT(n % 4 + 1, 'new', 'paid', 'shipped', 'cancelled'),
           TIMESTAMP('2026-10-01') - INTERVAL n SECOND
    FROM (
      SELECT a.i + b.i * 10 + c.i * 100 + e.i * 1000 + f.i * 10000 + g.i * 100000 + h.i * 1000000 + 1 AS n
      FROM d a, d b, d c, d e, d f, d g, d h
    ) AS numbers
    WHERE n <= ${ROWS};
    DROP TEMPORARY TABLE d;
  END IF;
END //
DELIMITER ;
CALL seed_orders();
DROP PROCEDURE seed_orders;
SELECT COUNT(*) AS mysql_orders FROM orders;
EOSQL
}

for target in "${targets[@]}"; do
  echo "Seeding ${ROWS} orders in ${target}..."
  start=$(date +%s)
  "seed_${target}"
  echo "${target}: done in $(($(date +%s) - start)) s"
done
