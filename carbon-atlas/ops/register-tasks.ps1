# Register the two carbon-atlas tasks in the Windows Task Scheduler.
#
# Run it one time, in a normal PowerShell window. See RUNNING.md section 3.
#
#   powershell -ExecutionPolicy Bypass -File ops\register-tasks.ps1
#
# To remove both tasks:
#   Unregister-ScheduledTask -TaskName 'carbon-atlas daily','carbon-atlas snap' -Confirm:$false
#
# The script registers the tasks with the S4U logon type, so they run while nobody is
# signed in. If the policy of the machine refuses S4U, the script falls back to
# Interactive and prints a warning. Read the warning: an Interactive task runs only
# while the user has a session, and a forecast snapshot that the program misses is lost
# for ever.

param(
  # The project directory.
  [string]$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,

  # pythonw.exe, and not python.exe. pythonw opens no console window.
  [string]$PythonW = (Join-Path $ProjectDir '.venv\Scripts\pythonw.exe'),

  # The LOCAL time of the measurement run. Read the note on time zones below.
  [string]$DailyAt = '05:00',

  # The LOCAL time of the first forecast snapshot. The next 3 follow every 6 hours.
  [string]$SnapFirstAt = '00:00',

  # S4U   Run whether the user is signed in or not. No password is kept. The task gets
  #       a local token, which is sufficient: the program calls public HTTPS endpoints
  #       and writes to a local directory. Some machines need the "Log on as a batch
  #       job" right, or administrator rights, to register an S4U task.
  # Interactive
  #       Run only while the user has a session. ⚠ A task of this type does not start
  #       while the user is signed out, and the Task Scheduler gives no alarm. It only
  #       keeps the last result of the last run that did start.
  [ValidateSet('S4U', 'Interactive')]
  [string]$LogonType = 'S4U'
)

if (-not (Test-Path $PythonW)) {
  Write-Error "pythonw.exe not found at $PythonW. Make the virtual environment first."
  exit 1
}

# ⚠ Time zones. The trigger time is LOCAL, and it moves with summer time. The
# ScheduledTasks cmdlets give no way to anchor a trigger to UTC. Only a hand-written
# task XML, with a `Z` on the StartBoundary, can do that.
#
# ARCHITECTURE.md section 2, REFERENCE.md section 7 and FORECASTS.md section 9 name the
# snapshot hours as "00, 06, 12 and 18 UTC". Those hours hold only on a machine whose
# local time is UTC. The interval of 6 hours is exact in every time zone. The absolute
# hours are not. The script prints the UTC hours of this machine at the end of the run.

# These 5 settings are the reason to use this script and not the default dialog.
#
#   StartWhenAvailable          A laptop is asleep at 05:00. Without this setting the run
#                               of that day does not happen. With it, the task starts a
#                               short time after the machine wakes.
#   AllowStartIfOnBatteries     The default is to skip the run on battery power.
#   DontStopIfGoingOnBatteries  The default stops a run that is in progress.
#   MultipleInstances IgnoreNew A late run must not start beside the next run. The store
#                               gives write access to one process only.
#   ExecutionTimeLimit 2 h      A stuck request must not hold the lock for ever.
#
# None of the 5 settings has an effect on a signed-out machine. Only the logon type does.
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$script:LogonUsed = $LogonType

function New-AtlasPrincipal([string]$Type) {
  New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType $Type -RunLevel Limited
}

# Register one task. If S4U fails, register it again as Interactive and say what that costs.
function Register-AtlasTask {
  param([string]$Name, $Action, $Trigger, [string]$Description)

  try {
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger `
      -Settings $settings -Principal (New-AtlasPrincipal $script:LogonUsed) -Force `
      -Description $Description -ErrorAction Stop | Out-Null
    return
  }
  catch {
    if ($script:LogonUsed -ne 'S4U') { throw }
    Write-Warning "S4U registration of '$Name' failed: $($_.Exception.Message)"
  }

  $script:LogonUsed = 'Interactive'
  Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger `
    -Settings $settings -Principal (New-AtlasPrincipal 'Interactive') -Force `
    -Description $Description -ErrorAction Stop | Out-Null

  Write-Warning "'$Name' is now an Interactive task. It runs only while $env:USERNAME is signed in."
  Write-Warning "A forecast snapshot in a signed-out window is lost for ever. See RUNNING.md section 3."
}

# --- Task 1: the measurement collection, one time each day -------------------
$actionDaily = New-ScheduledTaskAction -Execute $PythonW -Argument '-m atlas daily' -WorkingDirectory $ProjectDir
$triggerDaily = New-ScheduledTaskTrigger -Daily -At $DailyAt

Register-AtlasTask -Name 'carbon-atlas daily' -Action $actionDaily -Trigger $triggerDaily `
  -Description 'carbon-atlas: collect the measurements of the last 2 days, rebuild the views, export the portal JSON.'

# --- Task 2: the forecast snapshot, 4 times each day -------------------------
# A forecast curve is not in the history of most publishers. A snapshot that the program
# does not make is lost for ever. See REFERENCE.md section 7.
$actionSnap = New-ScheduledTaskAction -Execute $PythonW -Argument '-m atlas snap' -WorkingDirectory $ProjectDir
$triggerSnap = New-ScheduledTaskTrigger -Once -At $SnapFirstAt -RepetitionInterval (New-TimeSpan -Hours 6)

Register-AtlasTask -Name 'carbon-atlas snap' -Action $actionSnap -Trigger $triggerSnap `
  -Description 'carbon-atlas: capture the forward forecast curve of each source. 4 times each day.'

Write-Host 'Registered:'
Get-ScheduledTask -TaskName 'carbon-atlas *' |
  Format-Table TaskName, State, @{ Name = 'LogonType'; Expression = { $_.Principal.LogonType } }

# The true UTC hours of this machine. Report these, and not the hours in the documents.
function Get-UtcHour([string]$LocalHhMm) {
  return ([datetime]::Parse($LocalHhMm)).ToUniversalTime().ToString('HH:mm')
}

Write-Host ''
Write-Host "The times are local. The time zone of this machine is: $([TimeZoneInfo]::Local.Id)"
Write-Host ("  daily     {0} local = {1} UTC" -f $DailyAt, (Get-UtcHour $DailyAt))
Write-Host ("  snapshots {0} local = {1} UTC, then every 6 hours" -f $SnapFirstAt, (Get-UtcHour $SnapFirstAt))
Write-Host 'Summer time moves each UTC hour by 1 h. The interval of 6 hours does not change.'

Write-Host ''
Write-Host 'To test one run now:   Start-ScheduledTask -TaskName "carbon-atlas daily"'
Write-Host 'To see the last result: Get-ScheduledTaskInfo -TaskName "carbon-atlas daily"'
Write-Host 'The program log is in:  store\log\'
