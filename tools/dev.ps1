# FTM project task runner (Windows entry point).
#
# Routes each subcommand to the side that owns it, so a caller never has to
# know which (docs/CONTAINER.md §5):
#
#   container (build + host unit tests, never touches a board)
#     setup  build  target-build  test-host  test-host-selfcheck  coverage
#     shell  clean
#
#   Windows host, project venv (everything that needs the boards)
#     venv  boards  flash  e2e  manual  tools-test
#
# Usage:  .\tools\dev.ps1 <command> [args]
#         .\tools\dev.ps1 help

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = 'help',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)

$ErrorActionPreference = 'Stop'

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot 'docker\docker-compose.yml'
$VenvDir     = Join-Path $RepoRoot '.venv'
$VenvPython  = Join-Path $VenvDir 'Scripts\python.exe'
$BuildDir    = Join-Path $RepoRoot 'build_container'

function Write-Section($text) {
    Write-Host ""
    Write-Host "== $text" -ForegroundColor Cyan
}

function Fail($text) {
    Write-Host "ERROR: $text" -ForegroundColor Red
    exit 1
}

# Docker Desktop adds itself to the *Machine* PATH. A shell opened before or
# during install lacks it, and the resulting "docker: not found" reads like a
# permissions problem when it is only PATH (docs/CONTAINER.md §7).
function Initialize-DockerPath {
    if (Get-Command docker -ErrorAction SilentlyContinue) { return }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Fail "docker not found even after refreshing PATH from the registry. Is Docker Desktop installed and running?"
    }
}

function Invoke-Container([string[]]$ContainerArgs) {
    Initialize-DockerPath
    $composeArgs = @('compose', '-f', $ComposeFile, 'run', '--rm', 'dev') + $ContainerArgs
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-DevSh([string]$Subcommand) {
    Invoke-Container @('bash', 'tools/dev.sh', $Subcommand)
}

function Assert-Venv {
    if (-not (Test-Path $VenvPython)) {
        Fail "no venv at $VenvDir. Run:  .\tools\dev.ps1 venv"
    }
}

function Invoke-VenvPython([string[]]$PyArgs) {
    Assert-Venv
    & $VenvPython @PyArgs
    return $LASTEXITCODE
}

# --- container-side commands -------------------------------------------

function Cmd-Setup {
    Write-Section "Building the ftm-dev image"
    Initialize-DockerPath
    & docker compose -f $ComposeFile build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & docker compose -f $ComposeFile run --rm dev bash -c 'idf.py --version; ceedling version | head -4; gcovr --version | head -1'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Cmd-Shell {
    Write-Section "Interactive container shell (repo at /project)"
    Invoke-Container @('bash')
}

# --- host-side commands -------------------------------------------------

function Cmd-Venv {
    Write-Section "Creating $VenvDir"

    # The Microsoft Store `python` alias shadows real interpreters, so prefer
    # the IDF Python explicitly (docs/CONTAINER.md §4).
    $idfPython = 'C:\Users\murilo\.espressif\tools\idf-python\3.11.2\python.exe'
    if (Test-Path $idfPython) {
        $bootstrap = $idfPython
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $bootstrap = 'py'
    } else {
        Fail "no usable Python found to create the venv."
    }

    if (-not (Test-Path $VenvPython)) {
        if ($bootstrap -eq 'py') {
            & py -3 -m venv $VenvDir
        } else {
            & $bootstrap -m venv $VenvDir
        }
        if ($LASTEXITCODE -ne 0) { Fail "venv creation failed." }
    } else {
        Write-Host "venv already present, reusing it."
    }

    # Note the venv python, never the system or IDF python: nothing this
    # project installs may leak into either.
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $RepoRoot 'requirements-test.txt')
    if ($LASTEXITCODE -ne 0) { Fail "dependency install failed." }

    Write-Section "venv ready"
    & $VenvPython -c "import sys; print('interpreter:', sys.executable)"
}

function Cmd-Boards {
    Write-Section "Attached Espressif boards (MAC -> port)"
    Assert-Venv
    & $VenvPython (Join-Path $RepoRoot 'tools\board_ports.py') --list
    Write-Section "Roles (tools/boards.json)"
    & $VenvPython (Join-Path $RepoRoot 'tools\board_ports.py') --require-all
    exit $LASTEXITCODE
}

function Cmd-Flash([string[]]$FlashArgs) {
    if ($FlashArgs.Count -lt 1) {
        Fail "usage: .\tools\dev.ps1 flash <role> [app-build-dir]`n       roles are defined in tools/boards.json"
    }
    Assert-Venv

    $role = $FlashArgs[0]
    if ($FlashArgs.Count -ge 2) {
        $appBuild = $FlashArgs[1]
    } else {
        $appBuild = Join-Path $BuildDir 'target_smoke'
    }

    $flasherArgs = Join-Path $appBuild 'flasher_args.json'
    if (-not (Test-Path $flasherArgs)) {
        Fail "no build at $appBuild (expected $flasherArgs).`n       Build it first:  .\tools\dev.ps1 target-build"
    }

    Write-Section "Resolving role '$role' to a board by MAC"
    $port = & $VenvPython (Join-Path $RepoRoot 'tools\board_ports.py') --role $role
    if ($LASTEXITCODE -ne 0) {
        # board_ports.py has already printed the specific reason -- board not
        # attached, or a role that does not exist.
        Fail "cannot flash '$role': could not resolve it to a board (see above)."
    }
    $port = $port.Trim()
    Write-Host "role '$role' -> $port"

    $meta = Get-Content $flasherArgs -Raw | ConvertFrom-Json

    # flash_files is an offset -> relative path map; esptool wants them as
    # alternating positional arguments, ordered by offset.
    $files = @()
    foreach ($prop in $meta.flash_files.PSObject.Properties) {
        $files += [pscustomobject]@{
            Offset = [Convert]::ToInt64($prop.Name, 16)
            Raw    = $prop.Name
            Path   = (Join-Path $appBuild $prop.Value)
        }
    }
    $files = $files | Sort-Object Offset

    $espArgs = @('-m', 'esptool', '--chip', $meta.extra_esptool_args.chip,
                 '--port', $port, '--baud', '460800',
                 '--before', $meta.extra_esptool_args.before,
                 '--after', $meta.extra_esptool_args.after,
                 'write_flash',
                 '--flash_mode', $meta.flash_settings.flash_mode,
                 '--flash_freq', $meta.flash_settings.flash_freq,
                 '--flash_size', $meta.flash_settings.flash_size)
    foreach ($f in $files) {
        if (-not (Test-Path $f.Path)) { Fail "missing image $($f.Path)" }
        $espArgs += $f.Raw
        $espArgs += $f.Path
    }

    Write-Section "Flashing $role on $port"
    & $VenvPython @espArgs
    if ($LASTEXITCODE -ne 0) { Fail "flash failed on $port." }
    Write-Host "flashed '$role' on $port" -ForegroundColor Green
}

function Invoke-Pytest([string[]]$PytestArgs) {
    Assert-Venv
    Push-Location $RepoRoot
    try {
        & $VenvPython @(@('-m', 'pytest') + $PytestArgs)
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0) { exit $code }
}

function Cmd-E2E([string[]]$ExtraArgs) {
    Write-Section "L3 E2E -- both boards, Windows venv"
    Invoke-Pytest (@('tests/e2e', '-m', 'e2e', '-v') + $ExtraArgs)
}

function Cmd-Manual([string[]]$ExtraArgs) {
    Write-Section "L5 manual -- operator-driven, Windows venv"
    Invoke-Pytest (@('tests/manual', '-m', 'manual', '-v', '-s') + $ExtraArgs)
}

function Cmd-ToolsTest([string[]]$ExtraArgs) {
    Write-Section "L4 host tool tests -- Windows venv, no hardware"
    Invoke-Pytest (@('tests/tools', '-v') + $ExtraArgs)
}

function Show-Help {
    @'
Usage: .\tools\dev.ps1 <command> [args]

Container (build + host unit tests; never touches a board):
  setup                 build the ftm-dev image and print tool versions
  build                 build bench firmware for esp32c3
  target-build          build the L2 on-target smoke app
  test-host             L1a (Ceedling -> domain) + L1b (IDF linux -> services)
  test-host-selfcheck   prove the L1b harness fails loudly instead of hanging
  coverage              gcovr over L1a -> build_container/coverage
  shell                 interactive container shell
  clean                 delete build_container/

Windows host, project venv (everything that needs the boards):
  venv                  create .venv and install requirements-test.txt
  boards                list attached boards and resolve roles by MAC
  flash <role> [dir]    flash the board whose MAC matches <role>
  e2e                   L3 end-to-end across both boards
  manual                L5 operator-driven test
  tools-test            L4 tests for host Python tools

Test levels, where they run and how long they take: tests/README.md
'@ | Write-Host
}

switch ($Command.ToLower()) {
    'setup'               { Cmd-Setup }
    'build'               { Invoke-DevSh 'build' }
    'target-build'        { Invoke-DevSh 'target-build' }
    'test-host'           { Invoke-DevSh 'test-host' }
    'test-host-selfcheck' { Invoke-DevSh 'test-host-selfcheck' }
    'coverage'            { Invoke-DevSh 'coverage' }
    'clean'               { Invoke-DevSh 'clean' }
    'shell'               { Cmd-Shell }
    'venv'                { Cmd-Venv }
    'boards'              { Cmd-Boards }
    'flash'               { Cmd-Flash $Rest }
    'e2e'                 { Cmd-E2E $Rest }
    'manual'              { Cmd-Manual $Rest }
    'tools-test'          { Cmd-ToolsTest $Rest }
    'help'                { Show-Help }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
        exit 2
    }
}
