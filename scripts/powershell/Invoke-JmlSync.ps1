<#
.SYNOPSIS  Joiner/Mover/Leaver synchronisation: HR CSV feed -> Microsoft Entra ID (Microsoft Graph).
.DESCRIPTION
    PowerShell implementation of the rules in docs/02-identity-lifecycle.md; the Python engine
    (src/meridian_iam/jml_engine.py) is the tested reference. HR is authoritative; users are matched on the
    Entra 'employeeId' attribute, never on name or UPN.

      Joiner  create the account (disabled until start date), set attributes and manager, add to groups.
              Accounts are created PreboardDays before start. Initial credential is a random password that is
              discarded. Hand the user a Temporary Access Pass (see runbook) so they register MFA on day 1.
      Mover   update attributes + manager; REMOVE groups of the old role, add groups of the new role.
      Leaver  disable, revoke sign-in sessions, remove all group memberships, stamp the disable date.
              Delete after RetentionDays.
    Safeguards: invalid or duplicate HR rows are skipped (quarantined); the circuit breaker aborts when the run would
    disable more than -MaxDisablePercent of enabled users (override with -Force); every change honours -WhatIf and is
    written to out/jml-*.log. The Python engine also compares feed size with the previous run; this script keeps no
    run state, so it has no truncated-feed check.
.PARAMETER HrFeed     Path to the HR CSV (columns as in data/hr_feed_day0.csv).
.PARAMETER AsOf       Processing date (default today). Use it to replay historic feeds in the lab.
.EXAMPLE   ./Invoke-JmlSync.ps1 -HrFeed ../../data/hr_feed_day0.csv -WhatIf
.EXAMPLE   ./Invoke-JmlSync.ps1 -HrFeed ../../data/hr_feed_day30.csv -AsOf 2026-10-30
.NOTES     Scopes: User.ReadWrite.All, Group.ReadWrite.All, GroupMember.ReadWrite.All, User.RevokeSessions.All
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory)][ValidateScript({ Test-Path $_ })][string]$HrFeed,
    [datetime]$AsOf = (Get-Date).Date,
    [int]$PreboardDays = 7,
    [int]$RetentionDays = 30,
    [double]$MaxDisablePercent = 5.0,
    [string]$TenantId,
    [switch]$Force
)
. "$PSScriptRoot/Common.ps1"
Initialize-IamLog 'jml'
$catalog = Get-IamCatalog
$domainSuffix = '@' + $catalog.company.domain

# ---------- 1. Load and validate the feed ---------------------------------------------------------
$raw = Import-Csv -Path $HrFeed
$required = 'employee_id', 'upn', 'department', 'job_title', 'manager_id', 'employment_type', 'status', 'start_date', 'end_date'
$missing = $required | Where-Object { $_ -notin $raw[0].PSObject.Properties.Name }
if ($missing) { throw "HR feed missing required columns: $($missing -join ', ')" }

$records = @{}; $quarantine = @()
foreach ($grp in ($raw | Group-Object employee_id)) {
    if ([string]::IsNullOrWhiteSpace($grp.Name) -or $grp.Count -gt 1) {
        $quarantine += $grp.Group; Write-IamLog "Quarantined '$($grp.Name)': missing or duplicate employee_id" 'WARN'; continue
    }
    $r = $grp.Group[0]; $reason = $null
    $spec = $catalog.titles[$r.job_title]
    $start = [datetime]::MinValue; $end = [datetime]::MinValue
    if ($r.status -notin 'Active', 'Terminated') { $reason = 'bad status' }
    elseif ($r.upn -notmatch '@') { $reason = 'bad upn' }
    elseif (-not [datetime]::TryParseExact($r.start_date, 'yyyy-MM-dd', $null, 'None', [ref]$start)) { $reason = "bad start_date '$($r.start_date)'" }
    elseif ($r.end_date -and -not [datetime]::TryParseExact($r.end_date, 'yyyy-MM-dd', $null, 'None', [ref]$end)) { $reason = "bad end_date '$($r.end_date)'" }
    elseif (-not $spec) { $reason = "unknown job_title '$($r.job_title)'" }
    elseif ($spec.department -ne $r.department) { $reason = 'department/job_title mismatch' }
    if ($reason) { $quarantine += $r; Write-IamLog "Quarantined $($r.employee_id): $reason" 'WARN'; continue }
    $records[$r.employee_id] = [pscustomobject]@{
        Row = $r; Spec = $spec; Start = $start
        End = $(if ($r.end_date) { $end } else { $null })
    }
}
Write-IamLog "Feed: $($records.Count) valid, $(@($quarantine).Count) quarantined"

# ---------- 2. Connect and read current state -------------------------------------------------------
Connect-IamLab -TenantId $TenantId -Scopes 'User.ReadWrite.All', 'Group.ReadWrite.All', 'GroupMember.ReadWrite.All', 'User.RevokeSessions.All'
$props = 'id,userPrincipalName,accountEnabled,employeeId,department,jobTitle,employeeHireDate,onPremisesExtensionAttributes'
$users = Get-MgUser -All -Property $props -Filter "endswith(userPrincipalName,'$domainSuffix')" -ConsistencyLevel eventual -CountVariable uc
$byEmp = @{}; foreach ($u in $users) { if ($u.EmployeeId) { $byEmp[$u.EmployeeId] = $u } }

function Get-DesiredState($rec) {
    $leaver = $rec.Row.status -eq 'Terminated' -or ($rec.End -and $rec.End.Date -le $AsOf.Date)
    if ($leaver) { return @{ Lifecycle = 'leaver'; Enabled = $false; Groups = @() } }
    $days = ($rec.Start.Date - $AsOf.Date).Days
    if ($days -gt $PreboardDays) { return $null }
    $ents = @($catalog.birthright_entitlements) + @($rec.Spec.entitlements)
    @{ Lifecycle = $(if ($days -gt 0) { 'preboard' } else { 'active' }); Enabled = ($days -le 0)
       Groups = (Get-IamGroupNames -Department $rec.Row.department -BusinessRole $rec.Spec.business_role -Entitlements $ents) }
}

# ---------- 3. Circuit breaker -----------------------------------------------------------------------
$enabledCount = @($users | Where-Object AccountEnabled).Count
$willDisable = @($records.Values | Where-Object {
        $d = Get-DesiredState $_; $d -and $d.Lifecycle -eq 'leaver' -and $byEmp.ContainsKey($_.Row.employee_id) -and $byEmp[$_.Row.employee_id].AccountEnabled }).Count
if ($enabledCount -ge 20 -and ($willDisable * 100.0 / $enabledCount) -gt $MaxDisablePercent -and -not $Force) {
    throw "CIRCUIT BREAKER: $willDisable disables = $([math]::Round($willDisable*100.0/$enabledCount,1))% of $enabledCount enabled users (limit $MaxDisablePercent%). Nothing changed. Review the feed or use -Force."
}

# ---------- 4. Reconcile --------------------------------------------------------------------------------
function Get-ManagedGroupIds($userId) {
    # Only groups we own (grp-*) are touched; anything else is left alone.
    Get-MgUserMemberOf -UserId $userId -All | Where-Object { $_.AdditionalProperties.displayName -like 'grp-*' -and $_.AdditionalProperties.displayName -notlike 'grp-iam-*' }
}
function Set-Membership($user, [string[]]$desiredGroups) {
    $current = @{}; foreach ($g in (Get-ManagedGroupIds $user.Id)) { $current[$g.AdditionalProperties.displayName] = $g.Id }
    foreach ($name in $desiredGroups | Where-Object { -not $current.ContainsKey($_) }) {
        if ($PSCmdlet.ShouldProcess($user.UserPrincipalName, "Add to $name")) {
            $grp = Get-OrCreateGroup -DisplayName $name
            New-MgGroupMember -GroupId $grp.Id -DirectoryObjectId $user.Id
            Write-IamLog "ADD  $($user.UserPrincipalName) -> $name" 'ACTION'
        }
    }
    foreach ($name in $current.Keys | Where-Object { $_ -notin $desiredGroups }) {
        if ($PSCmdlet.ShouldProcess($user.UserPrincipalName, "Remove from $name")) {
            Remove-MgGroupMemberByRef -GroupId $current[$name] -DirectoryObjectId $user.Id
            Write-IamLog "DEL  $($user.UserPrincipalName) x $name" 'ACTION'
        }
    }
}
function Set-Manager($user, [string]$managerEmployeeId) {
    if (-not $managerEmployeeId -or -not $byEmp.ContainsKey($managerEmployeeId)) { return }
    $ref = @{ '@odata.id' = "https://graph.microsoft.com/v1.0/users/$($byEmp[$managerEmployeeId].Id)" }
    Set-MgUserManagerByRef -UserId $user.Id -BodyParameter $ref
}

$stats = @{ Created = 0; Moved = 0; Disabled = 0; Deleted = 0; Enabled = 0; Orphans = 0 }
foreach ($id in ($records.Keys | Sort-Object)) {
    $rec = $records[$id]; $r = $rec.Row; $want = Get-DesiredState $rec
    if (-not $want) { continue }
    $user = $byEmp[$id]

    if (-not $user) {                                                    # ---- JOINER
        if ($want.Lifecycle -eq 'leaver') { continue }
        if ($PSCmdlet.ShouldProcess($r.upn, "Create user ($($want.Lifecycle))")) {
            $pw = [guid]::NewGuid().ToString('N') + 'Aa1!'
            $new = New-MgUser -UserPrincipalName $r.upn -DisplayName "$($r.first_name) $($r.last_name)" -GivenName $r.first_name -Surname $r.last_name `
                -MailNickname ($r.upn.Split('@')[0]) -EmployeeId $id -Department $r.department -JobTitle $r.job_title -OfficeLocation $r.location `
                -EmployeeType $r.employment_type -EmployeeHireDate $rec.Start.ToUniversalTime() -AccountEnabled:$want.Enabled -UsageLocation 'ZA' `
                -PasswordProfile @{ Password = $pw; ForceChangePasswordNextSignIn = $true }
            $byEmp[$id] = $new
            Set-Manager $new $r.manager_id
            Set-Membership $new $want.Groups
            Write-IamLog "CREATE $($r.upn) [$($want.Lifecycle)] role=$($rec.Spec.business_role)" 'ACTION'
            $stats.Created++
        }
        continue
    }

    if ($want.Lifecycle -eq 'leaver') {                                  # ---- LEAVER
        if ($user.AccountEnabled -or (Get-ManagedGroupIds $user.Id)) {
            if ($PSCmdlet.ShouldProcess($user.UserPrincipalName, 'Disable, revoke sessions, strip groups')) {
                Update-MgUser -UserId $user.Id -AccountEnabled:$false -OnPremisesExtensionAttributes @{ ExtensionAttribute1 = (Get-Date $AsOf -Format 'yyyy-MM-dd') }
                Revoke-MgUserSignInSession -UserId $user.Id | Out-Null
                Set-Membership $user @()
                Write-IamLog "LEAVER $($user.UserPrincipalName) disabled; sessions revoked; groups removed" 'ACTION'
                $stats.Disabled++
            }
        } else {
            $stamp = $user.OnPremisesExtensionAttributes.ExtensionAttribute1
            if ($stamp -and (($AsOf.Date - [datetime]::ParseExact($stamp, 'yyyy-MM-dd', $null)).Days -ge $RetentionDays) -and
                $PSCmdlet.ShouldProcess($user.UserPrincipalName, "Delete (retention $RetentionDays days elapsed)")) {
                Remove-MgUser -UserId $user.Id
                Write-IamLog "DELETE $($user.UserPrincipalName) after retention" 'ACTION'; $stats.Deleted++
            }
        }
        continue
    }

    $orgChanged = $user.Department -ne $r.department -or $user.JobTitle -ne $r.job_title      # ---- MOVER
    if ($orgChanged -and $PSCmdlet.ShouldProcess($user.UserPrincipalName, "Move $($user.JobTitle) -> $($r.job_title)")) {
        Update-MgUser -UserId $user.Id -Department $r.department -JobTitle $r.job_title
        Set-Manager $user $r.manager_id
        Write-IamLog "MOVER $($user.UserPrincipalName): $($user.JobTitle) -> $($r.job_title); old role access removed" 'ACTION'
        $stats.Moved++
    }
    Set-Membership $user $want.Groups                                      # also repairs drift
    if ($want.Enabled -and -not $user.AccountEnabled -and $PSCmdlet.ShouldProcess($user.UserPrincipalName, 'Enable (start date reached)')) {
        Update-MgUser -UserId $user.Id -AccountEnabled:$true
        Write-IamLog "ENABLE $($user.UserPrincipalName)" 'ACTION'; $stats.Enabled++
    }
}

# ---------- 5. Orphans: report, never auto-delete -------------------------------------------------------
$known = @($records.Keys) + @($quarantine | ForEach-Object { $_.employee_id })
# adm-*, svc-* and bg*@ accounts are owned outside HR on purpose (see docs/01-architecture.md); they are not orphans.
$nonHr = '^(adm-|svc-|bg\d+@)'
foreach ($u in $users) {
    if ($u.UserPrincipalName -match $nonHr) { continue }
    if (-not $u.EmployeeId -or $u.EmployeeId -notin $known) {
        Write-IamLog "ORPHAN candidate (no HR record): $($u.UserPrincipalName), route to owner investigation" 'WARN'; $stats.Orphans++
    }
}
Write-IamLog ("Done. " + (($stats.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ' '))
