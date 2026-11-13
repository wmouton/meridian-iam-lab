<#
.SYNOPSIS  Reports enabled users with no successful sign-in for N days (dormant-account audit).
.NOTES     Needs User.Read.All + AuditLog.Read.All. signInActivity requires Entra ID P1/P2.
           Users who have never signed in are reported separately using their creation date.
.EXAMPLE   ./Audit-StaleAccounts.ps1 -DaysInactive 90
#>
[CmdletBinding()]
param([int]$DaysInactive = 90, [string]$OutFile, [string]$TenantId)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'audit-stale'
Connect-IamLab -Scopes 'User.Read.All', 'AuditLog.Read.All' -TenantId $TenantId
$cutoff = (Get-Date).ToUniversalTime().AddDays(-$DaysInactive)
$users = Get-MgUser -All -Filter 'accountEnabled eq true' -Property 'id,displayName,userPrincipalName,userType,createdDateTime,signInActivity,department,jobTitle'
$report = foreach ($u in $users) {
    $last = $u.SignInActivity.LastSuccessfulSignInDateTime
    if (-not $last) { $last = $u.SignInActivity.LastSignInDateTime }
    $status = if (-not $last) { if ($u.CreatedDateTime -lt $cutoff) { 'NeverSignedIn' } else { $null } } elseif ($last -lt $cutoff) { 'Stale' } else { $null }
    if ($status) {
        [pscustomobject]@{
            UserPrincipalName = $u.UserPrincipalName; DisplayName = $u.DisplayName; UserType = $u.UserType
            Department = $u.Department; JobTitle = $u.JobTitle; Status = $status
            LastSignIn = $last; DaysInactive = $(if ($last) { [int]((Get-Date).ToUniversalTime() - $last).TotalDays } else { $null })
        }
    }
}
if (-not $OutFile) { $OutFile = Join-Path $script:RepoRoot ('out/stale-accounts-{0:yyyyMMdd}.csv' -f (Get-Date)) }
New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null
$report | Sort-Object DaysInactive -Descending | Export-Csv -NoTypeInformation -Path $OutFile
Write-IamLog "$(@($report).Count) of $(@($users).Count) enabled users exceed $DaysInactive days inactivity. Report: $OutFile"
