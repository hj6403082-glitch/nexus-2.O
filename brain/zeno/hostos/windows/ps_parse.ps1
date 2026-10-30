# Zeno's PowerShell parse helper. It PARSES a command and never runs it.
#
#   powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
#       -File ps_parse.ps1 <command as UTF-8, base64>
#
# Prints one line of JSON for zeno/hostos/windows/ps_policy.py:
#   errors   parse errors (any error means the command is refused)
#   nodes    every syntax-tree node: id, parent id, type name, source offsets and text,
#            and its simple (string, number, bool, enum) properties
#   aliases  the built-in alias table, so the policy sees through rm, iex, saps...
#
# Works in Windows PowerShell 5.1 and PowerShell 7. Module auto-loading is off, and the
# one module it needs (for ConvertTo-Json) is loaded from PowerShell's own folder, so no
# module from a user-writable folder can ever run here.

$ErrorActionPreference = 'Stop'
$PSModuleAutoLoadingPreference = 'None'
# No Join-Path: it lives in a module that auto-loading would have to load.
Import-Module -Name "$PSHOME/Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

if ($args.Count -ne 1) {
    [Console]::Error.WriteLine('usage: ps_parse.ps1 <base64 UTF-8 command>')
    exit 2
}
$text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String([string]$args[0]))

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$parseErrors)

$all = @($ast.FindAll({ $true }, $true))
$ids = [System.Collections.Generic.Dictionary[System.Management.Automation.Language.Ast, int]]::new()
for ($i = 0; $i -lt $all.Count; $i++) {
    $ids[$all[$i]] = $i
}

$nodes = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt $all.Count; $i++) {
    $node = $all[$i]
    $parent = -1
    if ($null -ne $node.Parent -and $ids.ContainsKey($node.Parent)) {
        $parent = $ids[$node.Parent]
    }
    $props = [ordered]@{}
    foreach ($property in $node.PSObject.Properties) {
        try {
            $value = $property.Value
        } catch {
            continue
        }
        if ($null -eq $value) {
            continue
        }
        if ($value -is [string] -or $value -is [bool] -or $value -is [int] -or
            $value -is [long] -or $value -is [double] -or $value -is [System.Enum]) {
            $props[$property.Name] = [string]$value
        }
    }
    if ($node -is [System.Management.Automation.Language.CommandAst]) {
        $name = $node.GetCommandName()
        if ($null -ne $name) {
            $props['CommandName'] = $name
        }
    }
    if ($node -is [System.Management.Automation.Language.VariableExpressionAst]) {
        $props['VariablePath'] = $node.VariablePath.UserPath
    }
    if ($node -is [System.Management.Automation.Language.TypeExpressionAst] -or
        $node -is [System.Management.Automation.Language.TypeConstraintAst]) {
        $props['TypeName'] = $node.TypeName.FullName
    }
    $nodes.Add([ordered]@{
        id     = $i
        parent = $parent
        type   = $node.GetType().Name
        start  = $node.Extent.StartOffset
        end    = $node.Extent.EndOffset
        text   = $node.Extent.Text
        props  = $props
    })
}

# The built-in aliases (-NoProfile means there are no others), read without any cmdlet.
$aliases = [ordered]@{}
foreach ($entry in [System.Management.Automation.Runspaces.InitialSessionState]::CreateDefault().Commands) {
    if ($entry -is [System.Management.Automation.Runspaces.SessionStateAliasEntry]) {
        $aliases[$entry.Name] = [string]$entry.Definition
    }
}

$errors = @()
foreach ($parseError in @($parseErrors)) {
    if ($null -ne $parseError) {
        $errors += [string]$parseError.Message
    }
}

$result = [ordered]@{
    errors  = $errors
    nodes   = $nodes
    aliases = $aliases
}
[Console]::Out.Write(($result | ConvertTo-Json -Depth 6 -Compress))
