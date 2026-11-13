<#
.SYNOPSIS  Creates the security groups that implement the lab's RBAC model in Entra ID.
.DESCRIPTION
    Reads data/role_catalog.json and creates, idempotently:
      grp-bir-all-staff            birthright access for every employee
      grp-dept-<department>        department scoping
      grp-role-<business-role>     one per business role (assigned membership, managed by Invoke-JmlSync.ps1)
      grp-app-<app>-<role>         one per application entitlement (assign these to enterprise apps)
      grp-iam-breakglass           emergency access accounts; excluded from Conditional Access, alerted on every use
      grp-iam-pim-eligible-*       holders eligible for privileged roles via PIM
    Use -WhatIf to preview.
.EXAMPLE   ./New-LabGroups.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param([string]$TenantId)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'new-labgroups'
Connect-IamLab -Scopes 'Group.ReadWrite.All' -TenantId $TenantId

$catalog = Get-IamCatalog
$wanted = [System.Collections.Generic.SortedSet[string]]::new()
foreach ($t in $catalog.titles.Values) {
    foreach ($n in (Get-IamGroupNames -Department $t.department -BusinessRole $t.business_role -Entitlements ($catalog.birthright_entitlements + $t.entitlements))) { [void]$wanted.Add($n) }
}
foreach ($n in 'grp-iam-breakglass', 'grp-iam-pim-eligible-useradmin', 'grp-iam-pim-eligible-securityadmin') { [void]$wanted.Add($n) }

foreach ($name in $wanted) {
    if ($PSCmdlet.ShouldProcess($name, 'Create security group if missing')) {
        [void](Get-OrCreateGroup -DisplayName $name -Description 'Managed by Meridian IAM lab. Do not edit membership by hand.')
    } else {
        Write-IamLog "WhatIf: group $name" 'ACTION'
    }
}
Write-IamLog "Processed $($wanted.Count) groups"
