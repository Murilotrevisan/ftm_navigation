[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $IdfArguments
)

$ErrorActionPreference = 'Stop'
$idfPython = 'C:\Users\murilo\.espressif\tools\idf-python\3.11.2'
$idfExport = 'C:\Users\murilo\esp\v5.5.2\esp-idf\export.ps1'

if (-not (Test-Path -LiteralPath $idfPython)) {
    throw "ESP-IDF Python directory not found: $idfPython"
}
if (-not (Test-Path -LiteralPath $idfExport)) {
    throw "ESP-IDF export script not found: $idfExport"
}

$env:Path = $idfPython + [IO.Path]::PathSeparator + $env:Path
& $idfExport
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& idf.py @IdfArguments
exit $LASTEXITCODE
