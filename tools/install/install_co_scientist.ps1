#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$Reconcile,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$arguments = @(
    "-m",
    "tools.install.claude_install",
    "--project",
    $repoRoot,
    "--repo-root",
    $repoRoot
)

if ($Reconcile) {
    $arguments += "--reconcile"
}

if ($Uninstall) {
    $arguments += "--uninstall"
}

& $python @arguments
exit $LASTEXITCODE
