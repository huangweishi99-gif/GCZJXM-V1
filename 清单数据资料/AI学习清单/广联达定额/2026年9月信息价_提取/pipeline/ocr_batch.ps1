param([string]$PngDir, [string]$JsonDir)

Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.InteropServices.WindowsRuntime
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapPixelFormat, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapAlphaMode, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

$lang = [Windows.Globalization.Language]::new("zh-Hans-CN")
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if ($null -eq $engine) { Write-Host "ENGINE_FAIL"; exit 1 }
Write-Host "ENGINE_OK"

$asTaskM = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod } | Select-Object -First 1
$gm = $asTaskM.MakeGenericMethod([Windows.Media.Ocr.OcrResult])

$pngs = Get-ChildItem $PngDir -Filter *.png | Sort-Object Name
foreach ($f in $pngs) {
    $outJson = Join-Path $JsonDir ($f.BaseName + ".json")
    if (Test-Path $outJson) { Write-Host ("SKIP " + $f.Name); continue }
    try {
        $bmp = New-Object System.Drawing.Bitmap($f.FullName)
        $rect = [System.Drawing.Rectangle]::new(0, 0, $bmp.Width, $bmp.Height)
        $bits = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $bytes = New-Object byte[] ($bits.Stride * $bits.Height)
        [System.Runtime.InteropServices.Marshal]::Copy($bits.Scan0, $bytes, 0, $bytes.Length)
        $w = $bmp.Width; $h = $bmp.Height
        $bmp.UnlockBits($bits); $bmp.Dispose()

        $buf = [System.Runtime.InteropServices.WindowsRuntime.WindowsRuntimeBufferExtensions]::AsBuffer($bytes)
        $sbmp = [Windows.Graphics.Imaging.SoftwareBitmap]::new(
            [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, $w, $h,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)
        $sbmp.CopyFromBuffer($buf)

        $ocrOp = $engine.RecognizeAsync($sbmp)
        $task = $gm.Invoke($null, @($ocrOp))
        $task.Wait()
        $result = $task.Result

        $lines = New-Object System.Collections.ArrayList
        foreach ($line in $result.Lines) {
            $words = New-Object System.Collections.ArrayList
            foreach ($wd in $line.Words) {
                $br = $wd.BoundingRect
                [void]$words.Add(@{ t = $wd.Text; x = [int]$br.X; y = [int]$br.Y; w = [int]$br.Width; h = [int]$br.Height })
            }
            [void]$lines.Add(@{ text = $line.Text; words = $words })
        }
        $obj = @{ page = $f.BaseName; lines = $lines }
        ($obj | ConvertTo-Json -Depth 6 -Compress) | Out-File -Encoding UTF8 $outJson
        Write-Host ("OK " + $f.Name + " lines=" + $result.Lines.Count)
    } catch {
        Write-Host ("FAIL " + $f.Name + " " + $_.Exception.Message)
    }
}
Write-Host "BATCH_DONE"
