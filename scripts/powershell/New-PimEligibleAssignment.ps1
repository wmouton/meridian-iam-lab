<#
.SYNOPSIS  Makes a user ELIGIBLE (not permanently active) for an Entra directory role through PIM.
.DESCRIPTION
    Implements the "no standing privilege" model: the user activates the role just in time, with MFA,
    justification and (configured in PIM settings) approval and a short maximum duration.
    Role-policy settings (max 1-8h activation, MFA on activation, justification, approval, notifications) are
    configured per role in the portal (see docs/06-privileged-access.md): they are policy, not assignment.
.NOTES     Needs Entra ID P2 / Governance. Scope: RoleManagement.ReadWrite.Directory.
.EXAMPLE   ./New-PimEligibleAssignment.ps1 -UserPrincipalName alex@contoso.com -RoleName 'User Administrator' -Months 6 -Justification 'IAM analyst - TKT-1042'
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$UserPrincipalName,
    [Parameter(Mandatory)][string]$RoleName,
    [ValidateRange(1, 12)][int]$Months = 6,
    [Parameter(Mandatory)][string]$Justification,
    [string]$TenantId
)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'pim-eligible'
Connect-IamLab -Scopes 'RoleManagement.ReadWrite.Directory', 'User.Read.All' -TenantId $TenantId
$user = Get-MgUser -UserId $UserPrincipalName
$role = Get-MgRoleManagementDirectoryRoleDefinition -Filter "displayName eq '$RoleName'"
if (-not $role) { throw "Role '$RoleName' not found." }
$params = @{
    Action = 'adminAssign'; Justification = $Justification; RoleDefinitionId = $role.Id; DirectoryScopeId = '/'; PrincipalId = $user.Id
    ScheduleInfo = @{ StartDateTime = (Get-Date).ToUniversalTime(); Expiration = @{ Type = 'afterDateTime'; EndDateTime = (Get-Date).ToUniversalTime().AddMonths($Months) } }
}
if ($PSCmdlet.ShouldProcess("$UserPrincipalName", "Eligible for '$RoleName' for $Months month(s)")) {
    New-MgRoleManagementDirectoryRoleEligibilityScheduleRequest -BodyParameter $params | Out-Null
    Write-IamLog "ELIGIBLE $UserPrincipalName -> $RoleName until $((Get-Date).AddMonths($Months).ToString('yyyy-MM-dd')) ($Justification)" 'ACTION'
}
