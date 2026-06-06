param(
    [datetime]$From = [datetime]"2024-01-01",
    [string]$To = "now",
    [string]$Instrument = "xauusd",
    [string]$Timeframe = "m1",
    [switch]$Install,
    [switch]$Force,
    [switch]$NoCombine
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$RawDir = Join-Path $Root "data\raw\dukascopy"
$MonthlyDir = Join-Path $RawDir "monthly"
New-Item -ItemType Directory -Force -Path $MonthlyDir | Out-Null

if ($Install) {
    npm install
}

function Resolve-ToDate {
    param([string]$ToValue)
    if ($ToValue.ToLowerInvariant() -eq "now") {
        return [datetime]::UtcNow
    }
    return [datetime]$ToValue
}

function Normalize-DukascopyCsvName {
    param([string]$ExpectedPath)
    $AppendedPath = "$ExpectedPath.csv"
    if ((Test-Path $AppendedPath) -and -not (Test-Path $ExpectedPath)) {
        Move-Item -LiteralPath $AppendedPath -Destination $ExpectedPath
    }
}

function Download-MonthSide {
    param(
        [string]$Side,
        [datetime]$ChunkStart,
        [datetime]$ChunkEnd,
        [bool]$IsFinalChunk
    )

    $MonthLabel = $ChunkStart.ToString("yyyy-MM")
    $FileName = "xauusd_m1_${Side}_${MonthLabel}.csv"
    $ExpectedPath = Join-Path $MonthlyDir $FileName
    Normalize-DukascopyCsvName -ExpectedPath $ExpectedPath

    if ((Test-Path $ExpectedPath) -and -not $Force) {
        $Existing = Get-Item -LiteralPath $ExpectedPath
        if ($Existing.Length -gt 0) {
            Write-Host "Skipping existing $Side $MonthLabel ($($Existing.Length) bytes)"
            return
        }
    }

    $FromText = $ChunkStart.ToString("yyyy-MM-dd")
    $EndText = if ($Script:RequestedToNow -and $IsFinalChunk) { "now" } else { $ChunkEnd.ToString("yyyy-MM-dd") }

    Write-Host "Downloading $Side $FromText -> $EndText"
    npx dukascopy-node -i $Instrument -from $FromText -to $EndText -t $Timeframe -p $Side -f csv -dir ./data/raw/dukascopy/monthly -fn $FileName
    Normalize-DukascopyCsvName -ExpectedPath $ExpectedPath
}

function Combine-MonthlyFiles {
    param([string]$Side)

    $Pattern = "xauusd_m1_${Side}_*.csv"
    $Files = Get-ChildItem -LiteralPath $MonthlyDir -Filter $Pattern | Sort-Object Name
    if (-not $Files) {
        throw "No monthly $Side CSV files found under $MonthlyDir"
    }

    $OutputPath = Join-Path $RawDir "xauusd_m1_${Side}_2024_to_now.csv"
    $Writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $WroteHeader = $false
        foreach ($File in $Files) {
            $Reader = [System.IO.StreamReader]::new($File.FullName)
            try {
                $Header = $Reader.ReadLine()
                if (-not $WroteHeader) {
                    $Writer.WriteLine($Header)
                    $WroteHeader = $true
                }
                while (-not $Reader.EndOfStream) {
                    $Line = $Reader.ReadLine()
                    if ($Line) {
                        $Writer.WriteLine($Line)
                    }
                }
            }
            finally {
                $Reader.Dispose()
            }
        }
    }
    finally {
        $Writer.Dispose()
    }

    $Combined = Get-Item -LiteralPath $OutputPath
    Write-Host "Combined $Side monthly files -> $OutputPath ($($Combined.Length) bytes)"
}

$Script:RequestedToNow = $To.ToLowerInvariant() -eq "now"
$ToDate = Resolve-ToDate -ToValue $To
if ($ToDate -le $From) {
    throw "To date must be after From date."
}

$ChunkStart = [datetime]::SpecifyKind($From.Date, [System.DateTimeKind]::Utc)
while ($ChunkStart -lt $ToDate) {
    $NextMonth = [datetime]::new($ChunkStart.Year, $ChunkStart.Month, 1, 0, 0, 0, [System.DateTimeKind]::Utc).AddMonths(1)
    $ChunkEnd = if ($NextMonth -lt $ToDate) { $NextMonth } else { $ToDate }
    $IsFinalChunk = $ChunkEnd -eq $ToDate
    Download-MonthSide -Side "bid" -ChunkStart $ChunkStart -ChunkEnd $ChunkEnd -IsFinalChunk $IsFinalChunk
    Download-MonthSide -Side "ask" -ChunkStart $ChunkStart -ChunkEnd $ChunkEnd -IsFinalChunk $IsFinalChunk
    $ChunkStart = $ChunkEnd
}

if (-not $NoCombine) {
    Combine-MonthlyFiles -Side "bid"
    Combine-MonthlyFiles -Side "ask"
}
