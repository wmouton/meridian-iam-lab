<#
.SYNOPSIS  Lists directory role assignments and flags standing (permanent, active) privilege.
.DESCRIPTION
    Target state (docs/06-privileged-access.md): privileged roles are ELIGIBLE via PIM, activated just in time.
    The only permanent active holders should be the break-glass accounts. Everything else is a finding.
.NOTES     Needs RoleManagement.Read.Directory, User.Read.All, Group.Read.All.
.EXAMPLE   ./Audit-PrivilegedRoles.ps1 -BreakGlassUpn bg1@contoso.onmicrosoft.com,bg2@contoso.onmicrosoft.com
#>
[CmdletBinding()]
param([string[]]$BreakGlassUpn = @(), [string]$OutFile, [string]$TenantId)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'audit-privroles'
Connect-IamLab -Scopes 'RoleManagement.Read.Directory', 'User.Read.All', 'Group.Read.All' -TenantId $TenantId

$defs = @{}; Get-MgRoleManagementDirectoryRoleDefinition -All | ForEach-Object { $defs[$_.Id] = $_ }
$highImpact = 'Global Administrator', 'Privileged Role Administrator', 'Privileged Authentication Administrator', 'User Administrator',
              'Security Administrator', 'Conditional Access Administrator', 'Exchange Administrator', 'Application Administrator', 'Helpdesk Administrator'

function Resolve-Principal($id) {
    try { $o = Get-MgDirectoryObject -DirectoryObjectId $id; $o.AdditionalProperties.userPrincipalName ?? $o.AdditionalProperties.displayName ?? $id }
    catch { $id }
}

$rows = @()
foreach ($a in Get-MgRoleManagementDirectoryRoleAssignmentScheduleInstance -All) {      # ACTIVE
    $role = $defs[$a.RoleDefinitionId].DisplayName; $who = Resolve-Principal $a.PrincipalId
    $standing = $a.AssignmentType -eq 'Assigned' -and -not $a.EndDateTime
    $isBg = $who -in $BreakGlassUpn
    $rows += [pscustomobject]@{ Role = $role; Principal = $who; State = 'Active'; AssignmentType = $a.AssignmentType; Permanent = $standing
        HighImpact = $role -in $highImpact; Finding = $(if ($standing -and -not $isBg) { 'STANDING_PRIVILEGE' } elseif ($standing -and $isBg) { 'BREAK_GLASS_OK' } else { '' }) }
}
foreach ($e in Get-MgRoleManagementDirectoryRoleEligibilityScheduleInstance -All) {      # ELIGIBLE
    $rows += [pscustomobject]@{ Role = $defs[$e.RoleDefinitionId].DisplayName; Principal = (Resolve-Principal $e.PrincipalId); State = 'Eligible'
        AssignmentType = 'Eligible'; Permanent = -not $e.EndDateTime; HighImpact = $defs[$e.RoleDefinitionId].DisplayName -in $highImpact; Finding = '' }
}
$globalAdmins = @($rows | Where-Object { $_.Role -eq 'Global Administrator' -and $_.State -eq 'Active' })
if ($globalAdmins.Count -gt 5) { Write-IamLog "Too many active Global Administrators: $($globalAdmins.Count) (recommended: 2 break-glass + a handful)" 'WARN' }
if (-not $OutFile) { $OutFile = Join-Path $script:RepoRoot ('out/privileged-roles-{0:yyyyMMdd}.csv' -f (Get-Date)) }
New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null
$rows | Sort-Object Finding, Role | Export-Csv -NoTypeInformation -Path $OutFile
Write-IamLog "$(@($rows).Count) assignments; $(@($rows | Where-Object Finding -eq 'STANDING_PRIVILEGE').Count) standing-privilege findings. Report: $OutFile"
