param(
    [string]$RepositoryRoot = "."
)

Set-StrictMode -Version Latest

$GeneratedArtifactDeniedPaths = @(
    "data/raw/quikstrike/",
    "data/processed/quikstrike/",
    "data/reports/quikstrike/",
    "data/raw/quikstrike_matrix/",
    "data/processed/quikstrike_matrix/",
    "data/reports/quikstrike_matrix/",
    "data/raw/",
    "data/processed/",
    "data/reports/",
    "backend/data/raw/",
    "backend/data/processed/",
    "backend/data/reports/",
    "node_modules/",
    ".next/",
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

function Test-PathDenied {
    param([string]$Path)

    $normalized = ($Path -replace "\\", "/").TrimStart("./")
    foreach ($prefix in $GeneratedArtifactDeniedPaths) {
        if ($normalized.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    foreach ($segment in @("/node_modules/", "/.venv/", "/venv/", "/.next/")) {
        if ($normalized.IndexOf($segment, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    foreach ($pattern in $GeneratedArtifactDeniedPatterns) {
        if ((Split-Path -Leaf $normalized) -like $pattern -or $normalized -like $pattern) {
            return $true
        }
    }
    return $false
}

$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
Push-Location $root
try {
    git rev-parse --git-dir *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Generated artifact guard must run inside a git repository."
        exit 1
    }

    $tracked = @(git ls-files)
    $violations = @($tracked | Where-Object { Test-PathDenied $_ } | Sort-Object -Unique)
    if ($violations.Count -gt 0) {
        Write-Error ("Generated artifacts are tracked:`n" + ($violations -join "`n"))
        exit 1
    }

    Write-Output "Generated artifact guard passed. No tracked generated artifacts were found."
    exit 0
}
finally {
    Pop-Location
}
