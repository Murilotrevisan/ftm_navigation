param(
    [Alias('C')]
    [string] $ProjectDirectory,

    [Alias('B')]
    [string] $BuildDirectory,

    [Alias('p')]
    [string] $Port,

    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
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

$commandArguments = @()
if ($ProjectDirectory) {
    $commandArguments += @('-C', $ProjectDirectory)
}
if ($BuildDirectory) {
    $commandArguments += @('-B', $BuildDirectory)
}
if ($Port) {
    $commandArguments += @('-p', $Port)
}
$commandArguments += $IdfArguments

& idf.py @commandArguments
exit $LASTEXITCODE
