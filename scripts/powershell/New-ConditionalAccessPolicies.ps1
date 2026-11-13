<#
.SYNOPSIS  Deploys the lab's Conditional Access baseline from policies/conditional-access/*.json.
.DESCRIPTION
    Policies are created in REPORT-ONLY mode by default (state = enabledForReportingButNotEnforced) so you can
    review the impact in Sign-in logs -> Conditional Access before enforcing. Placeholders in the JSON are replaced
    from parameters: {{BREAKGLASS_GROUP_ID}}, {{BLOCKED_COUNTRIES_LOCATION_ID}}. Idempotent by displayName.
    Always keep at least two excluded break-glass accounts or you can lock yourself out of the tenant.
.EXAMPLE   ./New-ConditionalAccessPolicies.ps1 -BreakGlassGroupName grp-iam-breakglass -WhatIf
.EXAMPLE   ./New-ConditionalAccessPolicies.ps1 -BreakGlassGroupName grp-iam-breakglass -State enabled   # after review
.NOTES     Scopes: Policy.ReadWrite.ConditionalAccess, Policy.Read.All, Group.Read.All, Application.Read.All.
           CA004/CA005 (risk-based) require Entra ID P2. Skip files with -Exclude if unlicensed.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$BreakGlassGroupName,
    [string]$BlockedCountriesLocationId = '',
    [ValidateSet('enabledForReportingButNotEnforced', 'enabled', 'disabled')][string]$State = 'enabledForReportingButNotEnforced',
    [string[]]$Exclude = @(),
    [string]$TenantId
)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'ca-deploy'
Connect-IamLab -Scopes 'Policy.ReadWrite.ConditionalAccess', 'Policy.Read.All', 'Group.Read.All', 'Application.Read.All' -TenantId $TenantId

$bg = Get-MgGroup -Filter "displayName eq '$BreakGlassGroupName'"
if (-not $bg) { throw "Break-glass group '$BreakGlassGroupName' not found. Run New-LabGroups.ps1 and add two emergency accounts first." }
if ($State -eq 'enabled') {
    $members = @(Get-MgGroupMember -GroupId $bg.Id)
    if ($members.Count -lt 2) { throw "Refusing to enforce: break-glass group has $($members.Count) member(s); need at least 2." }
}

$existing = @{}; Get-MgIdentityConditionalAccessPolicy -All | ForEach-Object { $existing[$_.DisplayName] = $_ }
foreach ($file in Get-ChildItem (Join-Path $script:RepoRoot 'policies/conditional-access') -Filter 'CA*.json' | Sort-Object Name) {
    if ($file.BaseName -in $Exclude -or ($Exclude | Where-Object { $file.Name -like "$_*" })) { Write-IamLog "Skipping $($file.Name)"; continue }
    $json = (Get-Content -Raw $file.FullName).Replace('{{BREAKGLASS_GROUP_ID}}', $bg.Id).Replace('{{BLOCKED_COUNTRIES_LOCATION_ID}}', $BlockedCountriesLocationId)
    if ($json -match '\{\{.*?\}\}') { Write-IamLog "$($file.Name) has unresolved placeholder $($Matches[0]), skipped" 'WARN'; continue }
    $body = $json | ConvertFrom-Json -AsHashtable
    $body.state = $State
    if ($existing.ContainsKey($body.displayName)) {
        if ($PSCmdlet.ShouldProcess($body.displayName, "Update policy (state=$State)")) {
            Update-MgIdentityConditionalAccessPolicy -ConditionalAccessPolicyId $existing[$body.displayName].Id -BodyParameter $body
            Write-IamLog "UPDATED $($body.displayName) [$State]" 'ACTION'
        }
    } elseif ($PSCmdlet.ShouldProcess($body.displayName, "Create policy (state=$State)")) {
        New-MgIdentityConditionalAccessPolicy -BodyParameter $body | Out-Null
        Write-IamLog "CREATED $($body.displayName) [$State]" 'ACTION'
    }
}
