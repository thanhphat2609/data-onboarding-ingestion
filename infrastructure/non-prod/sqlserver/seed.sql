-- Sample source for non-prod. Idempotent: safe to run on every start.
-- Run by the sqlserver-seed service with -v RO_PASSWORD=<value>.

IF DB_ID('crm') IS NULL CREATE DATABASE crm;
GO

USE crm;
GO

IF OBJECT_ID('dbo.segments') IS NULL
CREATE TABLE dbo.segments (
  segment_id   INT           NOT NULL PRIMARY KEY,
  segment_name NVARCHAR(100) NOT NULL
);

IF OBJECT_ID('dbo.customers') IS NULL
CREATE TABLE dbo.customers (
  customer_id INT           NOT NULL PRIMARY KEY,
  full_name   NVARCHAR(200) NOT NULL,
  email       NVARCHAR(320) NULL,
  segment_id  INT           NOT NULL REFERENCES dbo.segments (segment_id),
  is_deleted  BIT           NOT NULL DEFAULT 0,
  created_at  DATETIME2(3)  NOT NULL,
  updated_at  DATETIME2(3)  NOT NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.segments)
INSERT INTO dbo.segments (segment_id, segment_name)
VALUES (1, N'Retail'), (2, N'SME'), (3, N'Enterprise');

-- 10,000 customers; a larger table for throughput tests is added in Phase 2.
IF NOT EXISTS (SELECT 1 FROM dbo.customers)
INSERT INTO dbo.customers (customer_id, full_name, email, segment_id, is_deleted, created_at, updated_at)
SELECT
  i,
  CONCAT(N'Customer ', i),
  CONCAT(N'customer', i, N'@example.com'),
  i % 3 + 1,
  CASE WHEN i % 50 = 0 THEN 1 ELSE 0 END,
  DATEADD(MINUTE, -i * 7, SYSUTCDATETIME()),
  DATEADD(MINUTE, -i, SYSUTCDATETIME())
FROM (
  SELECT TOP (10000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS i
  FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b
) AS n;
GO

-- Dedicated read-only login, as every connection requires (architecture §3.7).
IF SUSER_ID('svc_ingest_ro') IS NULL
  CREATE LOGIN svc_ingest_ro WITH PASSWORD = '$(RO_PASSWORD)';
ELSE
  ALTER LOGIN svc_ingest_ro WITH PASSWORD = '$(RO_PASSWORD)';
GO

IF USER_ID('svc_ingest_ro') IS NULL
BEGIN
  CREATE USER svc_ingest_ro FOR LOGIN svc_ingest_ro;
  ALTER ROLE db_datareader ADD MEMBER svc_ingest_ro;
END
GO

-- Empty here; seed-large.sh fills it with ~10M rows for the Phase 2 throughput tests.
IF OBJECT_ID('dbo.orders') IS NULL
CREATE TABLE dbo.orders (
  order_id    BIGINT        NOT NULL PRIMARY KEY,
  customer_id INT           NOT NULL,
  amount      DECIMAL(12,2) NOT NULL,
  status      VARCHAR(20)   NOT NULL,
  created_at  DATETIME2(3)  NOT NULL
);
GO

PRINT 'crm sample database is ready';
