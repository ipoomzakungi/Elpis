Set-StrictMode -Version Latest

$GeneratedArtifactDeniedPaths = @(
    "data/raw/",
    "data/processed/",
    "data/reports/",
    "node_modules/",
    ".venv/",
    "venv/",
    "frontend/.next/"
)

$GeneratedArtifactDeniedPatterns = @(
    "*.parquet",
    "*.duckdb",
    "*.duckdb.wal",
    ".env",
    ".env.*"
)

Write-Output "Generated artifact guard policy loaded. Full validation is implemented in a later task."