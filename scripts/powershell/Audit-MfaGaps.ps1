<#
.SYNOPSIS  Finds users without MFA registered, prioritising administrators and passwordless/phishing-resistant gaps.
.NOTES     Needs AuditLog.Read.All (+ Reports.Read.All). Registration details require Entra ID P1/P2.
.EXAMPLE   ./Audit-MfaGaps.ps1
#>
[CmdletBinding()]
param([string]$OutFile, [string]$TenantId)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'audit-mfa'
Connect-IamLab -Scopes 'AuditLog.Read.All', 'Reports.Read.All' -TenantId $TenantId
$details = Get-MgReportAuthenticationMethodUserRegistrationDetail -All
$report = foreach ($d in $details) {
    $finding = if (-not $d.IsMfaRegistered -and $d.IsAdmin) { 'CRITICAL_ADMIN_NO_MFA' }
               elseif (-not $d.IsMfaRegistered) { 'NO_MFA' }
               elseif ($d.IsAdmin -and -not ($d.MethodsRegistered | Where-Object { $_ -in 'fido2', 'windowsHelloForBusiness', 'x509CertificateMultiFactor', 'passKeyDeviceBound' })) { 'ADMIN_NOT_PHISHING_RESISTANT' }
               elseif ($d.MethodsRegistered -contains 'mobilePhone' -and $d.MethodsRegistered.Count -eq 1) { 'SMS_ONLY' }
               else { $null }
    if ($finding) {
        [pscustomobject]@{ UserPrincipalName = $d.UserPrincipalName; IsAdmin = $d.IsAdmin; IsMfaRegistered = $d.IsMfaRegistered
            DefaultMethod = $d.DefaultMfaMethod; Methods = ($d.MethodsRegistered -join ';'); Finding = $finding }
    }
}
if (-not $OutFile) { $OutFile = Join-Path $script:RepoRoot ('out/mfa-gaps-{0:yyyyMMdd}.csv' -f (Get-Date)) }
New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null
$report | Sort-Object Finding, UserPrincipalName | Export-Csv -NoTypeInformation -Path $OutFile
$total = @($details).Count; $gaps = @($report).Count
Write-IamLog "MFA findings for $gaps of $total users ($([math]::Round(100 * (1 - $gaps / [math]::Max($total,1)), 1))% clean). Report: $OutFile"
