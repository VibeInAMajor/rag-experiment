#requires -Version 5.1
$repositoryRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scriptPath = Join-Path $repositoryRoot 'start.ps1'
$tokens = $null
$parseErrors = $null
$launcherAst = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw ($parseErrors | Out-String) }
# Load helpers without starting the application or its containers.
foreach ($definition in $launcherAst.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($definition.Extent.Text))
}
$launcherText = Get-Content -LiteralPath $scriptPath -Raw
$startupBody = [scriptblock]::Create($launcherText.Substring($launcherText.IndexOf('$startupLock = $null')))

function Invoke-TestCommand { $global:LASTEXITCODE = 0 }

Describe 'Workbench restart ownership' {
    BeforeEach {
        $service = @{ Name = 'Site'; Kind = 'web'; Port = 4173 }
        $started = [datetime]'2026-11-28T10:00:00Z'
        $launcher = [pscustomobject]@{
            ProcessId = 100; ParentProcessId = 1; Name = 'pwsh.exe'; CreationDate = $started
            CommandLine = 'pwsh.exe -File "' + $scriptPath + '" -Worker web'
        }
        $listenerProcess = [pscustomobject]@{
            ProcessId = 101; ParentProcessId = 100; Name = 'node.exe'; CreationDate = $started.AddSeconds(1)
            CommandLine = 'node node_modules/vite/bin/vite.js preview'
        }
        Mock Get-NetTCPConnection { [pscustomobject]@{ OwningProcess = 101 } }
        Mock Get-CimInstance { @($launcher, $listenerProcess) }
        Mock Get-RequiredCommand { 'Invoke-TestCommand' }
        Mock Invoke-TestCommand { $global:LASTEXITCODE = 0 }
    }

    It 'finds existing workers through their listener ancestry, including paths with spaces' {
        (Get-WorkbenchWorker -Service $service).ProcessId | Should Be 100
    }

    It 'allows a stopped service without inspecting processes' {
        Mock Get-NetTCPConnection { @() }
        Get-WorkbenchWorker -Service $service | Should BeNullOrEmpty
        Assert-MockCalled -Scope It Get-CimInstance -Times 0 -Exactly
    }

    It 'refuses a worker from another checkout' {
        $launcher.CommandLine = 'pwsh.exe -File "C:\another checkout\start.ps1" -Worker web'
        { Get-WorkbenchWorker -Service $service } | Should Throw 'not owned'
    }

    It 'refuses a manually started listener' {
        $listenerProcess.ParentProcessId = 999
        { Get-WorkbenchWorker -Service $service } | Should Throw 'not owned'
    }

    It 'refuses the wrong worker kind even in this checkout' {
        $launcher.CommandLine = $launcher.CommandLine.Replace('-Worker web', '-Worker api')
        { Get-WorkbenchWorker -Service $service } | Should Throw 'not owned'
    }

    It 'refuses an ancestor PID reused after the child started' {
        $launcher.CreationDate = $started.AddMinutes(1)
        { Get-WorkbenchWorker -Service $service } | Should Throw 'not owned'
    }

    It 'terminates ancestry cycles without accepting them' {
        $launcher.CommandLine = 'pwsh.exe'
        $launcher.ParentProcessId = 101
        $launcher.CreationDate = $listenerProcess.CreationDate
        { Get-WorkbenchWorker -Service $service } | Should Throw 'not owned'
    }

    It 'checks every listener on the selected port' {
        Mock Get-NetTCPConnection { @([pscustomobject]@{ OwningProcess = 101 }, [pscustomobject]@{ OwningProcess = 999 }) }
        { Get-WorkbenchWorker -Service $service } | Should Throw 'not owned'
    }

    It 'stops the verified worker process tree' {
        Mock Get-CimInstance { $launcher }
        Stop-WorkbenchWorker -Process $launcher
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 1 -Exactly
    }

    It 'does not kill a PID reused after preflight' {
        Mock Get-CimInstance { [pscustomobject]@{ CreationDate = $started.AddHours(1); CommandLine = $launcher.CommandLine } }
        { Stop-WorkbenchWorker -Process $launcher } | Should Throw 'identity changed'
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 0 -Exactly
    }

    It 'accepts a worker that exited after preflight' {
        Mock Get-CimInstance { $null }
        Stop-WorkbenchWorker -Process $launcher
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 0 -Exactly
    }

    It 'reports failure to stop the worker' {
        Mock Get-CimInstance { $launcher }
        Mock Invoke-TestCommand { $global:LASTEXITCODE = 1 }
        { Stop-WorkbenchWorker -Process $launcher } | Should Throw 'Unable to stop'
    }
}

Describe 'Frontend build publication' {
    BeforeEach {
        $caseRoot = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $webRoot = Join-Path $caseRoot 'web'
        $logRoot = Join-Path $caseRoot 'logs'
        New-Item -ItemType Directory -Path $webRoot, $logRoot, (Join-Path $webRoot 'dist') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $webRoot 'dist/index.html') -Value 'old site'
        Mock Get-RequiredCommand { 'Invoke-TestCommand' }
        Mock Invoke-TestCommand {
            $global:LASTEXITCODE = 0
            if ($args[0] -eq 'run') {
                $directory = $args[[array]::IndexOf($args, '--outDir') + 1]
                New-Item -ItemType Directory -Path $directory -Force | Out-Null
                Set-Content -LiteralPath (Join-Path $directory 'index.html') -Value 'new site'
            }
        }
    }

    It 'installs locked dependencies and publishes a successful staged build' {
        Build-WorkbenchFrontend
        (Get-Content -LiteralPath (Join-Path $webRoot 'dist/index.html')) | Should Be 'new site'
        @(Get-ChildItem -LiteralPath $logRoot).Count | Should Be 0
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 2 -Exactly
    }

    It 'reuses installed dependencies so running Vite native modules remain untouched' {
        $viteDirectory = Join-Path $webRoot 'node_modules/vite/bin'
        New-Item -ItemType Directory -Path $viteDirectory -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $viteDirectory 'vite.js') -Value ''
        Build-WorkbenchFrontend
        (Get-Content -LiteralPath (Join-Path $webRoot 'dist/index.html')) | Should Be 'new site'
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 1 -Exactly
    }

    It 'preserves the old build if dependency installation fails' {
        Mock Invoke-TestCommand { $global:LASTEXITCODE = 1 }
        { Build-WorkbenchFrontend } | Should Throw 'dependency installation failed'
        (Get-Content -LiteralPath (Join-Path $webRoot 'dist/index.html')) | Should Be 'old site'
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 1 -Exactly
    }

    It 'preserves the old build and cleans staging after compilation fails' {
        Mock Invoke-TestCommand {
            $global:LASTEXITCODE = 0
            if ($args[0] -eq 'run') {
                New-Item -ItemType Directory -Path $args[[array]::IndexOf($args, '--outDir') + 1] -Force | Out-Null
                $global:LASTEXITCODE = 1
            }
        }
        { Build-WorkbenchFrontend } | Should Throw 'previous site build was preserved'
        (Get-Content -LiteralPath (Join-Path $webRoot 'dist/index.html')) | Should Be 'old site'
        @(Get-ChildItem -LiteralPath $logRoot).Count | Should Be 0
    }

    It 'restores the previous build if publication fails' {
        Mock Move-Item { throw 'Publication failed' } -ParameterFilter { $LiteralPath -like '*web-build-*' }
        { Build-WorkbenchFrontend } | Should Throw 'Publication failed'
        (Get-Content -LiteralPath (Join-Path $webRoot 'dist/index.html')) | Should Be 'old site'
    }

    It 'retains the backup for recovery if both publication and rollback fail' {
        Mock Move-Item { throw 'Move failed' } -ParameterFilter { $LiteralPath -like '*web-build-*' -or $LiteralPath -like '*web-backup-*' }
        { Build-WorkbenchFrontend } | Should Throw 'Move failed'
        $backup = Get-ChildItem -LiteralPath $logRoot -Directory -Filter 'web-backup-*'
        (Get-Content -LiteralPath (Join-Path $backup.FullName 'index.html')) | Should Be 'old site'
    }
}

Describe 'Workbench agent operations setup' {
    BeforeEach {
        $projectRoot = Join-Path $TestDrive 'repository'
        New-Item -ItemType Directory -Path (Join-Path $projectRoot 'apps/maf') -Force | Out-Null
        $previousOperationsDirectory = $env:WORKBENCH_AGENT_OPERATIONS_DIR
        Remove-Item Env:WORKBENCH_AGENT_OPERATIONS_DIR -ErrorAction SilentlyContinue
        Mock Invoke-TestCommand {
            $script:catalogCommand = $args
            $global:LASTEXITCODE = 0
        }
    }

    AfterEach {
        $env:WORKBENCH_AGENT_OPERATIONS_DIR = $previousOperationsDirectory
    }

    It 'provisions the checkout journal with the metadata-only MAF command' {
        Initialize-WorkbenchAgentOperations -HatchExecutable 'Invoke-TestCommand' | Should Be $true
        ($script:catalogCommand -join '|') | Should Be ("run|run|--operations-catalog-to|" + (Get-WorkbenchOperationsDirectory))
    }

    It 'uses an existing override without writing to its catalog' {
        $env:WORKBENCH_AGENT_OPERATIONS_DIR = Join-Path $TestDrive 'custom journal'
        New-Item -ItemType Directory -Path $env:WORKBENCH_AGENT_OPERATIONS_DIR -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $env:WORKBENCH_AGENT_OPERATIONS_DIR 'catalog.json') -Value 'existing'
        (Get-WorkbenchOperationsDirectory) | Should Be $env:WORKBENCH_AGENT_OPERATIONS_DIR
        Initialize-WorkbenchAgentOperations -HatchExecutable 'Invoke-TestCommand' | Should Be $true
        Assert-MockCalled -Scope It Invoke-TestCommand -Times 0 -Exactly
    }
}

Describe 'Launcher rebuild routing' {
    BeforeEach {
        $projectRoot = Join-Path $TestDrive 'project'
        $logRoot = Join-Path $projectRoot 'logs'
        foreach ($model in @('embedding', 'reranking')) {
            $directory = Join-Path $projectRoot "apps/workbench/$model"
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $directory 'start.ps1') -Value 'param([switch]$StartOnly)'
        }
        $Rebuild = $false
        $RebuildAll = $false
        $script:events = @()
        $script:agentsAvailable = $true
        Mock Get-RequiredCommand { 'Invoke-TestCommand' }
        Mock Invoke-TestCommand { $global:LASTEXITCODE = 0; 'v22.12.0' }
        Mock Get-WorkbenchWorker { $script:events += "inspect:$($Service.Kind)"; [pscustomobject]@{ Kind = $Service.Kind } }
        Mock Build-WorkbenchFrontend { $script:events += 'build' }
        Mock Stop-WorkbenchWorker { $script:events += "stop:$($Process.Kind)" }
        Mock Start-LocalPostgres {}
        Mock Start-WorkbenchService {}
        Mock Initialize-WorkbenchAgentOperations { $true }
        Mock Test-ServiceResponse { $Kind -ne 'agents' -or $script:agentsAvailable }
        Mock Wait-ServiceResponse { $true }
    }

    It 'reuses healthy services on ordinary startup' {
        . $startupBody | Out-Null
        Assert-MockCalled -Scope It Build-WorkbenchFrontend -Times 0 -Exactly
        Assert-MockCalled -Scope It Stop-WorkbenchWorker -Times 0 -Exactly
        Assert-MockCalled -Scope It Start-WorkbenchService -Times 3 -Exactly -ParameterFilter { -not $FrontendBuilt }
    }

    It 'refreshes only the owned API when a running Workbench still lacks Agents' {
        $script:agentsAvailable = $false
        . $startupBody | Out-Null
        ($script:events -join ',') | Should Be 'inspect:api,stop:api'
        Assert-MockCalled -Scope It Wait-ServiceResponse -Times 1 -Exactly -ParameterFilter {
            $Kind -eq 'agents' -and $Url -eq 'http://127.0.0.1:4173/api/v1/agents'
        }
    }

    It 'keeps the existing service when catalog initialization fails' {
        Mock Initialize-WorkbenchAgentOperations { $false }
        . $startupBody | Out-Null
        Assert-MockCalled -Scope It Stop-WorkbenchWorker -Times 0 -Exactly
        Assert-MockCalled -Scope It Start-WorkbenchService -Times 3 -Exactly
    }

    It 'rebuilds only the UI when Rebuild is selected' {
        $Rebuild = $true
        . $startupBody | Out-Null
        ($script:events -join ',') | Should Be 'inspect:web,build,stop:web'
        Assert-MockCalled -Scope It Start-WorkbenchService -Times 3 -Exactly -ParameterFilter { $FrontendBuilt }
    }

    It 'builds once then restarts all application workers for RebuildAll' {
        $RebuildAll = $true
        . $startupBody | Out-Null
        ($script:events -join ',') | Should Be 'inspect:api,inspect:validator,inspect:web,build,stop:api,stop:validator,stop:web'
    }

    It 'stops no workers if the frontend build fails' {
        $RebuildAll = $true
        Mock Build-WorkbenchFrontend { throw 'Build failed' }
        { . $startupBody } | Should Throw 'Build failed'
        Assert-MockCalled -Scope It Stop-WorkbenchWorker -Times 0 -Exactly
    }

    It 'builds and stops nothing if any selected listener is unowned' {
        $RebuildAll = $true
        Mock Get-WorkbenchWorker { throw 'Foreign listener' } -ParameterFilter { $Service.Kind -eq 'web' }
        { . $startupBody } | Should Throw 'Foreign listener'
        Assert-MockCalled -Scope It Build-WorkbenchFrontend -Times 0 -Exactly
        Assert-MockCalled -Scope It Stop-WorkbenchWorker -Times 0 -Exactly
    }
}
