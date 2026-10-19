param(
    [switch]$Headless,
    [string]$AppDataRoot = [Environment]::GetFolderPath('ApplicationData'),
    [string]$DocumentsRoot = [Environment]::GetFolderPath('MyDocuments'),
    [string]$HoudiniPrefs = '',
    [string]$BlenderVersion = '5.2',
    [string]$ContentLibrary = '',
    [switch]$SkipBlender,
    [switch]$SkipHoudini
)
$ErrorActionPreference = 'Stop'
$releaseRoot = $PSScriptRoot
$sourceRoot = Join-Path $releaseRoot 'payload'
if (!$HoudiniPrefs) { $HoudiniPrefs = Join-Path $DocumentsRoot 'houdini22.0' }
$contentDefault = Join-Path $DocumentsRoot 'BinaryCGI\Software_Development\BCGI_Content_Library_SAM_v001_20261008'
if (!$Headless) {
    Add-Type -AssemblyName System.Windows.Forms
    $form = New-Object Windows.Forms.Form
    $form.Text = 'Blender2Houdini SAM v011 | 20261019'; $form.Width = 680; $form.Height = 370; $form.StartPosition = 'CenterScreen'
    $intro = New-Object Windows.Forms.Label; $intro.Text = 'Close Blender and Houdini before installing. No administrator access needed.'; $intro.SetBounds(15,15,640,30); $form.Controls.Add($intro)
    $houCheck = New-Object Windows.Forms.CheckBox; $houCheck.Text = 'Install Houdini connector'; $houCheck.Checked = !$SkipHoudini; $houCheck.SetBounds(15,50,300,25); $form.Controls.Add($houCheck)
    $houPath = New-Object Windows.Forms.TextBox; $houPath.Text = $HoudiniPrefs; $houPath.SetBounds(15,80,625,25); $form.Controls.Add($houPath)
    $blendCheck = New-Object Windows.Forms.CheckBox; $blendCheck.Text = 'Install Blender add-on (enable in Blender Preferences after restart)'; $blendCheck.Checked = !$SkipBlender; $blendCheck.SetBounds(15,115,625,25); $form.Controls.Add($blendCheck)
    $blendLabel = New-Object Windows.Forms.Label; $blendLabel.Text = 'Blender version'; $blendLabel.SetBounds(15,150,120,25); $form.Controls.Add($blendLabel)
    $blendSelect = New-Object Windows.Forms.ComboBox; $blendSelect.SetBounds(140,147,120,25); $blendSelect.Text = $BlenderVersion
    $blenderBase = Join-Path $AppDataRoot 'Blender Foundation\Blender'
    if (Test-Path -LiteralPath $blenderBase) { Get-ChildItem -LiteralPath $blenderBase -Directory | Where-Object Name -Match '^\d+\.\d+$' | ForEach-Object { [void]$blendSelect.Items.Add($_.Name) } }
    $form.Controls.Add($blendSelect)
    $contentCheck = New-Object Windows.Forms.CheckBox; $contentCheck.Text = 'Optional: connect existing BCGI Content Library'; $contentCheck.SetBounds(15,185,620,25); $form.Controls.Add($contentCheck)
    $contentPath = New-Object Windows.Forms.TextBox; $contentPath.Text = $contentDefault; $contentPath.SetBounds(15,215,625,25); $form.Controls.Add($contentPath)
    $installButton = New-Object Windows.Forms.Button; $installButton.Text = 'Install / Update'; $installButton.SetBounds(460,265,180,35); $installButton.DialogResult = [Windows.Forms.DialogResult]::OK; $form.Controls.Add($installButton); $form.AcceptButton = $installButton
    if ($form.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { exit 0 }
    $SkipHoudini = !$houCheck.Checked; $SkipBlender = !$blendCheck.Checked; $HoudiniPrefs = $houPath.Text.Trim(); $BlenderVersion = $blendSelect.Text.Trim()
    if ($contentCheck.Checked) { $ContentLibrary = $contentPath.Text.Trim() }
}
if (!$SkipBlender -and $BlenderVersion -notmatch '^\d+\.\d+$') { throw 'Enter a Blender version such as 5.2 or 4.5.' }
if ($ContentLibrary -and !(Test-Path -LiteralPath (Join-Path $ContentLibrary 'content_ui.py'))) { throw 'BCGI Content Library folder not found. Choose its existing folder or leave the optional box off.' }
$base = Join-Path $AppDataRoot 'BinaryCGI\Blender2Houdini'
$runtime = Join-Path $base 'v011'
$exchange = Join-Path $DocumentsRoot 'BinaryCGI\Blender2Houdini\exchange'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_ffff'
$backup = Join-Path $base ('backups\' + $stamp)
$backups = New-Object System.Collections.Generic.List[string]
function Backup-OwnedPath([string]$path, [string]$name) {
    if (Test-Path -LiteralPath $path) {
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        Copy-Item -LiteralPath $path -Destination (Join-Path $backup $name) -Recurse -Force
        $backups.Add($path)
    }
}
New-Item -ItemType Directory -Path $base,$exchange -Force | Out-Null
$configPath = Join-Path $base 'settings.json'
Backup-OwnedPath $configPath 'settings.json'
$config = @{version='v011';date='20261019';exchange=$exchange;runtime=$runtime;content_library=$ContentLibrary}
if ((Test-Path -LiteralPath $configPath) -and !$ContentLibrary) {
    $oldConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($oldConfig.content_library) { $config.content_library = $oldConfig.content_library }
}
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding UTF8
if (!$SkipBlender) {
    $addonPath = Join-Path $AppDataRoot ('Blender Foundation\Blender\' + $BlenderVersion + '\scripts\addons\blender2houdini_sam')
    Backup-OwnedPath $addonPath 'blender2houdini_sam'
    New-Item -ItemType Directory -Path $addonPath -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceRoot 'blender2houdini_sam\*') -Destination $addonPath -Recurse -Force
}
if (!$SkipHoudini) {
    Backup-OwnedPath $runtime 'runtime_v011'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceRoot 'connector\*') -Destination $runtime -Recurse -Force
    $packages = Join-Path $HoudiniPrefs 'packages'; $toolbar = Join-Path $HoudiniPrefs 'toolbar'
    New-Item -ItemType Directory -Path $packages,$toolbar -Force | Out-Null
    $packagePath = Join-Path $packages 'Blender2Houdini_SAM.json'; $shelfPath = Join-Path $toolbar 'Blender2Houdini_SAM_v001.shelf'
    Backup-OwnedPath $packagePath 'Blender2Houdini_SAM.json'; Backup-OwnedPath $shelfPath 'Blender2Houdini_SAM_v001.shelf'
    $packageJson = @{env=@(@{B2H_SAM_ROOT=$runtime},@{B2H_EXCHANGE_FOLDER=$exchange},@{KARMA_XPU_DISABLE_EMBREE_DEVICE='1'});path=(Join-Path $runtime 'houdini')} | ConvertTo-Json -Depth 8
    # Houdini rejects Windows PowerShell's UTF-8 BOM in package JSON.
    [IO.File]::WriteAllText($packagePath,$packageJson,(New-Object Text.UTF8Encoding $false))
    $doc = New-Object System.Xml.XmlDocument; $decl=$doc.CreateXmlDeclaration('1.0','UTF-8',$null); [void]$doc.AppendChild($decl)
    $shelves = $doc.CreateElement('shelfDocument'); [void]$doc.AppendChild($shelves)
    $shelf = $doc.CreateElement('toolshelf'); $shelf.SetAttribute('name','b2h_sam_v001'); $shelf.SetAttribute('label','Blender2Houdini SAM v011'); [void]$shelves.AppendChild($shelf)
    $rootLiteral = ($runtime.Replace('\','/') | ConvertTo-Json -Compress)
    function Add-BridgeTool([string]$name,[string]$label,[string]$code) {
        $member=$doc.CreateElement('memberTool'); $member.SetAttribute('name',$name); [void]$shelf.AppendChild($member)
        $tool=$doc.CreateElement('tool'); $tool.SetAttribute('name',$name); $tool.SetAttribute('label',$label); $tool.SetAttribute('icon',(Join-Path $runtime 'icons\blender.png')); [void]$shelves.AppendChild($tool)
        $script=$doc.CreateElement('script'); $script.SetAttribute('scriptType','python')
        $python = "import sys, hou`nsys.path.insert(0,$rootLiteral)`ntry:`n" + (($code -split "`n" | ForEach-Object { ' '+$_ }) -join "`n") + "`nexcept Exception as e:`n hou.ui.setStatusMessage('Blender2Houdini: '+str(e),hou.severityType.Error)"
        [void]$script.AppendChild($doc.CreateCDataSection($python)); [void]$tool.AppendChild($script)
    }
    Add-BridgeTool 'b2h_import_sam_v001' 'Import Blender PBR' "import houdini_importer`nhoudini_importer.import_latest()"
    Add-BridgeTool 'b2h_send_sam_v001' 'Send to Blender' "import houdini_exporter`nhoudini_exporter.send_selected()"
    Add-BridgeTool 'b2h_use_karma_sam' 'Use Karma' "import material_builders`nmaterial_builders.use_selected('karma')"
    Add-BridgeTool 'b2h_use_materialx_sam' 'Use MaterialX' "import material_builders`nmaterial_builders.use_selected('materialx')"
    Add-BridgeTool 'b2h_reconnect_textures_sam' 'Reconnect Textures / Choose Exchange' "import texture_reconnect`ntexture_reconnect.choose_folder()"
    Add-BridgeTool 'b2h_start_receiver_sam' 'Connect / Auto Receive' "import auto_import_bridge`nauto_import_bridge.start()"
    if ($config.content_library) { Add-BridgeTool 'b2h_content_library_sam' 'BCGI Content' "import optional_content`noptional_content.open_library()" }
    foreach ($setName in @('shelf_set_1','solaris_1')) {
        $set=$doc.CreateElement('shelfSetEdit'); $set.SetAttribute('name',$setName); $member=$doc.CreateElement('addMemberToolshelf'); $member.SetAttribute('name','b2h_sam_v001'); [void]$set.AppendChild($member); [void]$shelves.AppendChild($set)
    }
    $doc.Save($shelfPath)
}
$report = @{version='v011';date='20261019';blender_installed=(!$SkipBlender);houdini_installed=(!$SkipHoudini);houdini_preferences=$HoudiniPrefs;exchange=$exchange;runtime=$runtime;backup=$backup;backed_up_paths=@($backups);content_library=$config.content_library;note='Restart apps. Enable Blender add-on in Preferences. Existing blend files: click Use Installed Exchange Folder.'}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $base 'install_report.json') -Encoding UTF8
Write-Output ($report | ConvertTo-Json -Depth 8)
if (!$Headless) { [Windows.Forms.MessageBox]::Show("Installed SAM v011.`nRestart Houdini and Blender.`nBlender Preferences > Add-ons: enable Blender2Houdini SAM v011.`nIn older .blend files click Use Installed Exchange Folder.`n`nExchange: $exchange",'Installation complete') | Out-Null }
