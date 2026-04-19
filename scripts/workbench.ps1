param(
    [ValidateSet("test", "score", "borrowers", "refresh", "daily", "full")]
    [string[]]$Task = @("daily"),
    [string]$Python = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Resolve-Python {
    param([string]$Preferred)

    if ($Preferred) {
        return $Preferred
    }

    if ($env:VIRTUAL_ENV) {
        $activeVenvPython = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
        if (Test-Path $activeVenvPython) {
            return $activeVenvPython
        }
    }

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    return "python"
}

function Invoke-Step {
    param(
        [string]$Label,
        [string[]]$Command
    )

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    Write-Host ($Command -join " ") -ForegroundColor DarkGray
    & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Label"
    }
}

function Test-PythonModule {
    param([string]$Module)

    & $pythonExe "-c" "import $Module"
    return ($LASTEXITCODE -eq 0)
}

$pythonExe = Resolve-Python -Preferred $Python

function Run-Pytest {
    if (-not (Test-PythonModule -Module "pytest")) {
        throw "pytest is not installed for $pythonExe. Install dev dependencies with 'pip install -e .[dev]' or pass -Python to a Python environment that has pytest."
    }

    Invoke-Step -Label "Run test suite" -Command @($pythonExe, "-m", "pytest", "-q")
}

function Run-Screener {
    $args = @($pythonExe, "red_flag_screener.py", "--live-na")
    $label = "Run screener"

    if (-not $DryRun) {
        $args += @("--csv", "data/processed/screener_results.csv")
        $label = "Refresh screener CSV"
    }

    Invoke-Step -Label $label -Command $args
}

function Run-BorrowerDb {
    if ($DryRun) {
        Write-Host ""
        Write-Host "==> Skip borrower database rebuild (no dry-run mode available)" -ForegroundColor Yellow
        return
    }

    Invoke-Step -Label "Rebuild borrower database" -Command @(
        $pythonExe, "portfolio_collector.py", "--build-db"
    )
}

function Run-Refresh {
    $args = @($pythonExe, "refresh.py")
    if ($DryRun) {
        $args += "--dry-run"
    }
    Invoke-Step -Label "Run refresh pipeline" -Command $args
}

function Run-Daily {
    $args = @($pythonExe, "refresh.py", "--score-only")
    if ($DryRun) {
        $args += "--dry-run"
    }
    Invoke-Step -Label "Run score-only refresh" -Command $args
    Run-Screener
}

function Run-Full {
    Run-Refresh
    Run-BorrowerDb
    Run-Screener
    Run-Pytest
}

foreach ($item in $Task) {
    switch ($item) {
        "test" { Run-Pytest }
        "score" { Run-Screener }
        "borrowers" { Run-BorrowerDb }
        "refresh" { Run-Refresh }
        "daily" { Run-Daily }
        "full" { Run-Full }
        default { throw "Unknown task: $item" }
    }
}

Write-Host ""
Write-Host "Completed task(s): $($Task -join ', ')" -ForegroundColor Green
