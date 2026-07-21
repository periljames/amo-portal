# Run from repo root after env vars are set. Produces exact table counts only, no row data.
$ErrorActionPreference = "Stop"
$out = "db_exact_counts_$(Get-Date -Format yyyyMMdd_HHmmss).txt"
$dbUrl = $env:DATABASE_WRITE_URL
if (-not $dbUrl) { $dbUrl = $env:DATABASE_URL }
if (-not $dbUrl) { throw "DATABASE_WRITE_URL or DATABASE_URL is not set." }
$psqlUrl = $dbUrl -replace "^postgresql\+psycopg2://", "postgresql://"
psql $psqlUrl -v ON_ERROR_STOP=1 -f .\db_review\exact_row_count_export.sql *> $out
Write-Host "Created $out"