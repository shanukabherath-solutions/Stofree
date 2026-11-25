<#
.SYNOPSIS
    Builds Stofree for Windows: PyInstaller ONEDIR (+ optional ONEFILE) and the Inno Setup 7 installer.

.DESCRIPTION
    Steps (each one stops the script with a clear message if it fails; nothing is silently ignored):
      1. Validate the existing .venv and that it runs Python 3.12 (64-bit)
      2. Verify application dependencies and that the version numbers agree
      3. Install PyInstaller / Pillow into the .venv if missing
      4. (optional) run the test suite
      5. Build the ONEDIR distribution  -> dist\Stofree\Stofree.exe
      6. Validate it (files, version resource, headless self-test)
      7. (optional) build the ONEFILE exe -> dist\onefile\Stofree.exe
      8. Compile installer\Stofree.iss with Inno Setup 7 if installed -> installer-output\Stofree-Setup.exe
      9. Report where everything is

.PARAMETER OneFile
    Also build the standalone single-file Stofree.exe (dist\onefile\Stofree.exe).

.PARAMETER SkipInstaller
    Do not look for / run Inno Setup.

.PARAMETER SkipSelfTest
    Do not run "Stofree.exe --self-test" on the built executables (e.g. on a build server with no
    interactive desktop session).

.PARAMETER RunTests
    Run the pytest suite before building (needs pytest and pytest-qt in the .venv).

.PARAMETER InnoCompiler
    Full path of ISCC.exe. Otherwise the script looks at $env:INNO_SETUP_COMPILER, PATH and the
    usual "Inno Setup 7" install folders.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -OneFile
#>
[CmdletBinding()]
param(
    [switch]$OneFile,
    [switch]$SkipInstaller,
    [switch]$SkipSelfTest,
    [switch]$RunTests,
    [string]$InnoCompiler
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root        = Split-Path -Parent $PSScriptRoot
$VenvPython  = Join-Path $Root '.venv\Scripts\python.exe'
$BuildDir    = Join-Path $Root 'build'
$DistDir     = Join-Path $Root 'dist\Stofree'
$OneFileDir  = Join-Path $Root 'dist\onefile'
$InstallerOut = Join-Path $Root 'installer-output'
$SetupExe    = Join-Path $InstallerOut 'Stofree-Setup.exe'
$SpecFile    = Join-Path $Root 'packaging\Stofree.spec'
$IssFile     = Join-Path $Root 'installer\Stofree.iss'

$Summary = New-Object System.Collections.Generic.List[string]

# ------------------------------------------------------------------------------------------ helpers
function Write-Step([string]$Text) { Write-Host ''; Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text)   { Write-Host "    OK: $Text" -ForegroundColor Green }

# Run a native program and fail on a non-zero exit code. Native tools (PyInstaller, pip) write their
# normal progress to stderr, so ErrorActionPreference is relaxed for the call and the exit code decides.
function Invoke-Native([string]$What, [string]$File, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $File @Arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$What failed (exit code $code). See the output above." }
}

# Run a native program and return its output text (stdout+stderr); fail on a non-zero exit code.
function Invoke-NativeCapture([string]$What, [string]$File, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $File @Arguments 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $text = ($out -join "`n").Trim()
    if ($code -ne 0) { throw "$What failed (exit code $code):`n$text" }
    return $text
}

# Python snippets are written to a temp file (avoids PowerShell/Windows quoting problems with -c).
function Invoke-PythonSnippet([string]$What, [string]$Code) {
    if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }
    $file = Join-Path $BuildDir ('snippet_' + [guid]::NewGuid().ToString('N') + '.py')
    Set-Content -Path $file -Value $Code -Encoding ASCII
    try { return (Invoke-NativeCapture $What $VenvPython @($file)) }
    finally { Remove-Item $file -Force -ErrorAction SilentlyContinue }
}

function Format-Size([long]$Bytes) {
    if ($Bytes -ge 1MB) { return ('{0:N1} MB' -f ($Bytes / 1MB)) }
    return ('{0:N0} KB' -f ($Bytes / 1KB))
}

# Starts "<exe> --self-test <report>" with a timeout and checks the JSON report it writes.
function Test-BuiltExecutable([string]$Label, [string]$ExePath) {
    if ($SkipSelfTest) { Write-Host "    (self-test of $Label skipped by -SkipSelfTest)"; return }
    if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }
    $report = Join-Path $BuildDir ("selftest-" + $Label + ".json")
    Remove-Item $report -Force -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $ExePath -ArgumentList @('--self-test', ('"' + $report + '"')) -PassThru
    if (-not $proc.WaitForExit(180000)) {
        try { $proc.Kill() } catch { }
        throw "Self-test of $Label did not finish within 3 minutes and was stopped."
    }
    if (-not (Test-Path $report)) {
        throw "Self-test of $Label produced no report (exit code $($proc.ExitCode)). Start '$ExePath' manually and check %LOCALAPPDATA%\Stofree\logs\stofree.log."
    }
    $data = Get-Content $report -Raw | ConvertFrom-Json
    $failed = @($data.results | Where-Object { -not $_.ok })
    foreach ($r in $data.results) {
        $mark = if ($r.ok) { 'pass' } else { 'FAIL' }
        Write-Host ("    [{0}] {1}: {2}" -f $mark, $r.check, $r.detail)
    }
    if ($proc.ExitCode -ne 0 -or $failed.Count -gt 0) {
        throw "Self-test of $Label failed ($($failed.Count) check(s)). Report: $report"
    }
    Write-Ok "self-test of $Label passed (frozen=$($data.frozen), report: $report)"
}

function Find-InnoCompiler {
    if ($InnoCompiler) {
        if (-not (Test-Path $InnoCompiler)) { throw "-InnoCompiler was given but '$InnoCompiler' does not exist." }
        return (Resolve-Path $InnoCompiler).Path
    }
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($env:INNO_SETUP_COMPILER) { $candidates.Add($env:INNO_SETUP_COMPILER) }
    $onPath = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($onPath) { $candidates.Add($onPath.Source) }
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA 'Programs'))) {
        if ($base) { $candidates.Add((Join-Path $base 'Inno Setup 7\ISCC.exe')) }
    }
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path } }
    return $null
}

# ---------------------------------------------------------------------------------------------- main
try {
    Set-Location $Root
    Write-Host "Stofree Windows build - project root: $Root"
    # Fail fast on an explicit but wrong -InnoCompiler, before spending minutes on the build.
    if ($InnoCompiler -and -not (Test-Path $InnoCompiler)) { throw "-InnoCompiler was given but '$InnoCompiler' does not exist." }

    # ---- 1. Python 3.12 in the existing virtual environment
    Write-Step '1/9  Checking Python 3.12 and the .venv'
    if (-not (Test-Path $VenvPython)) {
        throw ("The virtual environment was not found ($VenvPython).`n" +
               "Create it once with:`n    py -3.12 -m venv .venv`n    .\.venv\Scripts\python.exe -m pip install -r requirements.txt")
    }
    $pyInfo = Invoke-PythonSnippet 'Reading the .venv Python version' @'
import struct, sys
print('%d.%d.%d' % sys.version_info[:3] + ' ' + str(struct.calcsize('P') * 8))
'@
    $pyVersion, $pyBits = $pyInfo -split '\s+'
    if (-not $pyVersion.StartsWith('3.12.')) {
        throw "The .venv uses Python $pyVersion but Python 3.12 is required. Recreate it: py -3.12 -m venv .venv"
    }
    if ($pyBits -ne '64') { throw "The .venv uses 32-bit Python; PySide6 needs 64-bit Python 3.12." }
    Write-Ok "Python $pyVersion (64-bit) at $VenvPython"

    # ---- 2. Dependencies + consistent version numbers
    Write-Step '2/9  Verifying application dependencies and version numbers'
    $deps = Invoke-PythonSnippet 'Verifying dependencies' @'
import importlib, importlib.metadata as md
bad = []
for name in ('PySide6.QtWidgets', 'PySide6.QtCharts', 'PySide6.QtSvg', 'psutil'):
    try:
        importlib.import_module(name)
    except Exception as exc:
        bad.append(name + ' (' + type(exc).__name__ + ': ' + str(exc) + ')')
if bad:
    print('Missing or broken: ' + '; '.join(bad))
    raise SystemExit(1)
print('PySide6 ' + md.version('PySide6') + ', psutil ' + md.version('psutil'))
'@
    Write-Ok $deps
    $Version = Invoke-NativeCapture 'Reading APP_VERSION' $VenvPython @('-c', 'from app.utils.constants import APP_VERSION; print(APP_VERSION)')
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "APP_VERSION '$Version' must look like 1.2.3 (three numbers)." }
    $versionInfo = Get-Content (Join-Path $Root 'packaging\version_info.txt') -Raw
    $quad = ($Version -split '\.') -join ', '
    foreach ($needle in @("StringStruct('FileVersion', '$Version')", "StringStruct('ProductVersion', '$Version')",
                          "filevers=($quad, 0)", "prodvers=($quad, 0)")) {
        if (-not $versionInfo.Contains($needle)) {
            throw "packaging\version_info.txt does not match APP_VERSION $Version (expected to contain: $needle)."
        }
    }
    Write-Ok "APP_VERSION $Version matches packaging\version_info.txt"

    # ---- 3. Build tools
    Write-Step '3/9  Checking build tools (PyInstaller, Pillow)'
    $tools = @(@{ Module = 'PyInstaller'; Spec = 'pyinstaller>=6.0' }, @{ Module = 'PIL'; Spec = 'pillow>=10.0' })
    foreach ($t in $tools) {
        $present = $true
        try { [void](Invoke-NativeCapture "Checking $($t.Module)" $VenvPython @('-c', "import $($t.Module)")) } catch { $present = $false }
        if (-not $present) {
            Write-Host "    $($t.Module) is missing - installing $($t.Spec) into the .venv"
            Invoke-Native "Installing $($t.Spec)" $VenvPython @('-m', 'pip', 'install', $t.Spec)
        }
    }
    $piVersion = Invoke-NativeCapture 'Reading the PyInstaller version' $VenvPython @('-m', 'PyInstaller', '--version')
    Write-Ok "PyInstaller $piVersion"

    # ---- 4. Optional tests
    Write-Step '4/9  Tests'
    if ($RunTests) {
        Invoke-Native 'The test suite' $VenvPython @('-m', 'pytest', '-q')
        Write-Ok 'test suite passed'
    } else {
        Write-Host '    (skipped - pass -RunTests to run pytest first)'
    }

    # ---- 5. ONEDIR build
    Write-Step '5/9  Building ONEDIR distribution with PyInstaller'
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
    $env:STOFREE_BUILD_MODE = 'onedir'
    try {
        Invoke-Native 'PyInstaller (ONEDIR)' $VenvPython @('-m', 'PyInstaller', '--noconfirm', '--clean',
            '--distpath', (Join-Path $Root 'dist'), '--workpath', (Join-Path $BuildDir 'onedir'), $SpecFile)
    } finally {
        Remove-Item Env:\STOFREE_BUILD_MODE -ErrorAction SilentlyContinue
    }

    # ---- 6. Validate ONEDIR
    Write-Step '6/9  Validating the ONEDIR build'
    $exe = Join-Path $DistDir 'Stofree.exe'
    if (-not (Test-Path $exe)) { throw "PyInstaller finished but $exe was not created." }
    if ((Get-Item $exe).Length -le 0) { throw "$exe is empty." }
    foreach ($name in @('logo.png', 'Ani.gif', 'stofree.ico', 'darkmode_logo.png', 'lightmode_logo.png', 'qwindows.dll')) {
        $hit = Get-ChildItem -Path $DistDir -Recurse -Filter $name -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $hit) { throw "Expected file '$name' is missing from the ONEDIR build ($DistDir)." }
    }
    $vi = (Get-Item $exe).VersionInfo
    if ($vi.ProductName -ne 'Stofree' -or $vi.FileVersion -ne $Version -or $vi.OriginalFilename -ne 'Stofree.exe') {
        throw "Stofree.exe version resource is wrong (ProductName='$($vi.ProductName)', FileVersion='$($vi.FileVersion)', OriginalFilename='$($vi.OriginalFilename)')."
    }
    Write-Ok "Stofree.exe present; ProductName=$($vi.ProductName), FileDescription='$($vi.FileDescription)', version $($vi.FileVersion)"
    Test-BuiltExecutable 'onedir' $exe
    $distBytes = (Get-ChildItem $DistDir -Recurse -File | Measure-Object Length -Sum).Sum
    $Summary.Add(("ONEDIR  (installer input)   : {0}   [{1}]" -f $exe, (Format-Size $distBytes)))

    # ---- 7. Optional ONEFILE
    Write-Step '7/9  ONEFILE build'
    if ($OneFile) {
        if (Test-Path $OneFileDir) { Remove-Item $OneFileDir -Recurse -Force }
        $env:STOFREE_BUILD_MODE = 'onefile'
        try {
            Invoke-Native 'PyInstaller (ONEFILE)' $VenvPython @('-m', 'PyInstaller', '--noconfirm', '--clean',
                '--distpath', $OneFileDir, '--workpath', (Join-Path $BuildDir 'onefile'), $SpecFile)
        } finally {
            Remove-Item Env:\STOFREE_BUILD_MODE -ErrorAction SilentlyContinue
        }
        $one = Join-Path $OneFileDir 'Stofree.exe'
        if (-not (Test-Path $one)) { throw "PyInstaller finished but $one was not created." }
        Write-Ok "ONEFILE Stofree.exe created ($(Format-Size (Get-Item $one).Length))"
        Test-BuiltExecutable 'onefile' $one
        $Summary.Add(("ONEFILE (standalone exe)    : {0}   [{1}]" -f $one, (Format-Size (Get-Item $one).Length)))
    } else {
        Write-Host '    (skipped - pass -OneFile to also build the standalone single-file exe)'
        $Summary.Add('ONEFILE (standalone exe)    : not built (use -OneFile)')
    }

    # ---- 8. Installer
    Write-Step '8/9  Inno Setup installer'
    if ($SkipInstaller) {
        Write-Host '    (skipped by -SkipInstaller)'
        $Summary.Add('Installer                    : NOT built (-SkipInstaller)')
    } else {
        $iscc = Find-InnoCompiler
        if (-not $iscc) {
            Write-Warning ('Inno Setup 7 (ISCC.exe) was not found, so Stofree-Setup.exe was NOT built. ' +
                           'Install it (winget install --id JRSoftware.InnoSetup.7 -e -s winget) or pass -InnoCompiler <path>, then run this script again.')
            $Summary.Add('Installer                    : NOT built - Inno Setup 7 not found')
        } else {
            $innoVersion = (Get-Item $iscc).VersionInfo.ProductVersion
            if ($innoVersion -and $innoVersion -match '^(\d+)\.' -and [int]$Matches[1] -lt 7) {
                throw "Inno Setup $innoVersion found at $iscc, but installer\Stofree.iss needs Inno Setup 7 or newer."
            }
            Write-Ok "Inno Setup compiler: $iscc (version $innoVersion)"
            if (-not (Test-Path (Join-Path $Root 'installer\TERMS_AND_CONDITIONS.txt'))) { throw 'installer\TERMS_AND_CONDITIONS.txt is missing.' }
            Invoke-Native 'Generating the installer wizard images' $VenvPython @((Join-Path $Root 'tools\make_installer_images.py'))
            if (Test-Path $SetupExe) { Remove-Item $SetupExe -Force }     # never report a stale installer
            Invoke-Native 'Inno Setup compile' $iscc @("/DAppVersion=$Version", $IssFile)
            if (-not (Test-Path $SetupExe)) { throw "Inno Setup finished but $SetupExe was not created." }
            $hash = (Get-FileHash $SetupExe -Algorithm SHA256).Hash
            Write-Ok "Stofree-Setup.exe created ($(Format-Size (Get-Item $SetupExe).Length))"
            $Summary.Add(("Installer                    : {0}   [{1}]" -f $SetupExe, (Format-Size (Get-Item $SetupExe).Length)))
            $Summary.Add("Installer SHA-256            : $hash")
        }
    }

    # ---- 9. Report
    Write-Step '9/9  Done - generated output'
    foreach ($line in $Summary) { Write-Host "    $line" }
    Write-Host ''
    Write-Host 'The automated checks above do NOT replace testing the installer on a clean Windows machine' -ForegroundColor Yellow
    Write-Host '(see "Release test checklist" in README.md).' -ForegroundColor Yellow
    exit 0
}
catch {
    Write-Host ''
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "(at $($_.InvocationInfo.ScriptName):$($_.InvocationInfo.ScriptLineNumber))" -ForegroundColor DarkRed
    exit 1
}
