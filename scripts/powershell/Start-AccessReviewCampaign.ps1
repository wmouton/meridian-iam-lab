<#
.SYNOPSIS  Creates a recurring Entra access review from a JSON template in policies/access-reviews/.
.DESCRIPTION
    Placeholders {{GROUP_ID}} and {{REVIEWER_USER_ID}} are replaced. The template reviews a sensitive group
    quarterly, uses the manager as reviewer with a fallback, and AUTO-APPLIES "deny" when no one responds
    (default-deny is what makes recertification a control rather than a formality).
.NOTES     Needs Entra ID Governance / P2. Scope: AccessReview.ReadWrite.All, Group.Read.All.
.EXAMPLE   ./Start-AccessReviewCampaign.ps1 -GroupName grp-app-erp-ap-approve -FallbackReviewerUpn controller@contoso.com -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$GroupName,
    [Parameter(Mandatory)][string]$FallbackReviewerUpn,
    [string]$Template = 'quarterly-sensitive-group-review.json',
    [string]$TenantId
)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'access-review'
Connect-IamLab -Scopes 'AccessReview.ReadWrite.All', 'Group.Read.All', 'User.Read.All' -TenantId $TenantId
$group = Get-MgGroup -Filter "displayName eq '$GroupName'"; if (-not $group) { throw "Group '$GroupName' not found" }
$rev = Get-MgUser -UserId $FallbackReviewerUpn
$path = Join-Path $script:RepoRoot "policies/access-reviews/$Template"
$json = (Get-Content -Raw $path).Replace('{{GROUP_ID}}', $group.Id).Replace('{{REVIEWER_USER_ID}}', $rev.Id).Replace('{{GROUP_NAME}}', $GroupName).Replace('{{START_DATE}}', (Get-Date -Format 'yyyy-MM-dd'))
if ($PSCmdlet.ShouldProcess($GroupName, 'Create quarterly access review')) {
    Invoke-MgGraphRequest -Method POST -Uri 'https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions' -Body $json -ContentType 'application/json' | Out-Null
    Write-IamLog "Access review created for $GroupName (reviewer fallback $FallbackReviewerUpn)" 'ACTION'
}
