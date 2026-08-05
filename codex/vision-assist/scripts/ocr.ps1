param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Region,
    [int]$Scale = 1,
    [switch]$Grayscale
)

Add-Type -AssemblyName System.Drawing

# Prepare bitmap: optional crop -> upscale -> grayscale
$src = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $Path))
try {
    if ($Region) {
        $parts = $Region -split ','
        if ($parts.Count -ne 4) { throw "Region must be x,y,width,height" }
        $x = [int]$parts[0]; $y = [int]$parts[1]
        $w = [int]$parts[2]; $h = [int]$parts[3]
        $crop = New-Object System.Drawing.Bitmap($w, $h)
        $g = [System.Drawing.Graphics]::FromImage($crop)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($src, 0, 0, [System.Drawing.Rectangle]::new($x, $y, $w, $h), [System.Drawing.GraphicsUnit]::Pixel)
        $g.Dispose()
        $src.Dispose()
        $src = $crop
    }
    if ($Scale -gt 1) {
        $scaled = New-Object System.Drawing.Bitmap(($src.Width * $Scale), ($src.Height * $Scale))
        $g = [System.Drawing.Graphics]::FromImage($scaled)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($src, 0, 0, $scaled.Width, $scaled.Height)
        $g.Dispose()
        $src.Dispose()
        $src = $scaled
    }
    if ($Grayscale) {
        $gray = New-Object System.Drawing.Bitmap($src.Width, $src.Height)
        $g = [System.Drawing.Graphics]::FromImage($gray)
        $matrix = New-Object System.Drawing.Imaging.ColorMatrix
        $matrix.Matrix00 = 0.299; $matrix.Matrix01 = 0.299; $matrix.Matrix02 = 0.299
        $matrix.Matrix10 = 0.587; $matrix.Matrix11 = 0.587; $matrix.Matrix12 = 0.587
        $matrix.Matrix20 = 0.114; $matrix.Matrix21 = 0.114; $matrix.Matrix22 = 0.114
        $matrix.Matrix33 = 1
        $attrs = New-Object System.Drawing.Imaging.ImageAttributes
        $attrs.SetColorMatrix($matrix)
        $g.DrawImage($src, (New-Object System.Drawing.Rectangle(0, 0, $src.Width, $src.Height)), 0, 0, $src.Width, $src.Height, [System.Drawing.GraphicsUnit]::Pixel, $attrs)
        $g.Dispose()
        $src.Dispose()
        $src = $gray
    }

    $tmp = [System.IO.Path]::GetTempFileName() + ".png"
    $src.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)

    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType = WindowsRuntime]

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    function Await($WinRtTask, $ResultType) {
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(-1) | Out-Null
        $netTask.Result
    }

    $bytes = [System.IO.File]::ReadAllBytes($tmp)
    $mem = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $writer = New-Object Windows.Storage.Streams.DataWriter($mem)
    $writer.WriteBytes($bytes)
    $null = Await ($writer.StoreAsync()) ([uint32])
    $writer.DetachStream() | Out-Null
    $mem.Seek(0)

    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($mem)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($engine -eq $null) { throw "No OCR engine available on this machine" }
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

    Write-Output ("===== OCR result =====")
    Write-Output ("Language: " + $engine.RecognizerLanguage.DisplayName)
    Write-Output ("Image (processed): " + $src.Width + "x" + $src.Height)
    $i = 0
    foreach ($line in $result.Lines) {
        $i++
        $minX = $null; $minY = $null; $maxX = $null; $maxY = $null
        foreach ($wd in $line.Words) {
            $bb = $wd.BoundingRect
            $bx = [double]$bb.X; $by = [double]$bb.Y
            $bw = [double]$bb.Width; $bh = [double]$bb.Height
            if ($null -eq $minX) {
                $minX = $bx; $minY = $by; $maxX = $bx + $bw; $maxY = $by + $bh
            } else {
                if ($bx -lt $minX) { $minX = $bx }
                if ($by -lt $minY) { $minY = $by }
                if (($bx + $bw) -gt $maxX) { $maxX = $bx + $bw }
                if (($by + $bh) -gt $maxY) { $maxY = $by + $bh }
            }
        }
        if ($null -ne $minX) {
            Write-Output ("{0,3}: ({1},{2},{3},{4}) {5}" -f $i, [int]$minX, [int]$minY, [int]($maxX - $minX), [int]($maxY - $minY), $line.Text)
        } else {
            Write-Output ("{0,3}: {1}" -f $i, $line.Text)
        }
    }
    Write-Output ("===== end (total lines: " + $i + ") =====")

    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
finally {
    if ($src) { $src.Dispose() }
}
