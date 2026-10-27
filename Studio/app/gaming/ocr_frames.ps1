# Windows built-in OCR over every PNG/JPG in a folder. Prints one tab-separated line per word:
#   file<TAB>text<TAB>x<TAB>y<TAB>w<TAB>h
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr_frames.ps1 <folder>
param([Parameter(Mandatory = $true)][string]$Folder)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { Write-Error "no OCR engine"; exit 1 }
Get-ChildItem -Path $Folder -File | Where-Object { $_.Extension -match '^\.(png|jpg|jpeg)$' } | Sort-Object Name | ForEach-Object {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($_.FullName)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $name = $_.Name
    foreach ($line in $result.Lines) {
        foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            Write-Output ("{0}`t{1}`t{2}`t{3}`t{4}`t{5}" -f $name, $w.Text, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
        }
    }
    $stream.Dispose()
}
