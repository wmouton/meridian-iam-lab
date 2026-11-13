<#
.SYNOPSIS  Shared helpers for the Meridian IAM lab PowerShell scripts. Dot-source this file.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path

function Write-IamLog {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR', 'ACTION')][string]$Level = 'INFO'
    )
    $line = '{0} [{1}] {2}' -f (Get-Date).ToUniversalTime().ToString('s'), $Level, $Message
    switch ($Level) {
        'ERROR' { Write-Error $line -ErrorAction Continue }
        'WARN'  { Write-Warning $line }
        default { Write-Host $line }
    }
    if ($script:IamLogPath) { Add-Content -Path $script:IamLogPath -Value $line }
}

function Initialize-IamLog {
    param([Parameter(Mandatory)][string]$Name)
    $dir = Join-Path $script:RepoRoot 'out'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $script:IamLogPath = Join-Path $dir ('{0}-{1:yyyyMMdd-HHmmss}.log' -f $Name, (Get-Date))
}

function Connect-IamLab {
    <#
    .SYNOPSIS  Connect to Microsoft Graph with only the scopes a script needs.
    .DESCRIPTION
        Interactive (delegated) sign-in by default, which is fine for a lab. For scheduled runs use an
        app registration with a certificate: -ClientId, -TenantId, -CertificateThumbprint. Never use client secrets
        in scripts and never commit credentials.
    #>
    param(
        [Parameter(Mandatory)][string[]]$Scopes,
        [string]$TenantId, [string]$ClientId, [string]$CertificateThumbprint
    )
    if ($ClientId -and $CertificateThumbprint -and $TenantId) {
        Connect-MgGraph -TenantId $TenantId -ClientId $ClientId -CertificateThumbprint $CertificateThumbprint -NoWelcome
    } else {
        Connect-MgGraph -Scopes $Scopes -NoWelcome
    }
    $ctx = Get-MgContext
    Write-IamLog "Connected to tenant $($ctx.TenantId) as $($ctx.Account) with scopes: $($ctx.Scopes -join ', ')"
}

function Get-IamCatalog {
    Get-Content -Raw -Path (Join-Path $script:RepoRoot 'data/role_catalog.json') | ConvertFrom-Json -AsHashtable
}

function Get-IamGroupNames {
    <# Mirrors iamlib.group_names() in Python so both implementations produce identical group names. #>
    param([string]$Department, [string]$BusinessRole, [string[]]$Entitlements)
    $names = [System.Collections.Generic.SortedSet[string]]::new()
    [void]$names.Add('grp-bir-all-staff')
    [void]$names.Add("grp-dept-$($Department.ToLower())")
    [void]$names.Add("grp-role-$($BusinessRole.ToLower())")
    foreach ($e in $Entitlements) { [void]$names.Add('grp-app-' + $e.ToLower().Replace(':', '-').Replace('_', '-')) }
    return @($names)
}

function Get-OrCreateGroup {
    param([Parameter(Mandatory)][string]$DisplayName, [string]$Description = '', [switch]$WhatIf)
    $escaped = $DisplayName.Replace("'", "''")
    $existing = Get-MgGroup -Filter "displayName eq '$escaped'" -ConsistencyLevel eventual -CountVariable c
    if ($existing) { return $existing | Select-Object -First 1 }
    if ($WhatIf) { Write-IamLog "WhatIf: would create group $DisplayName" 'ACTION'; return $null }
    Write-IamLog "Creating group $DisplayName" 'ACTION'
    New-MgGroup -DisplayName $DisplayName -Description $Description -MailEnabled:$false -MailNickname ($DisplayName -replace '[^a-zA-Z0-9]', '') -SecurityEnabled:$true
}
