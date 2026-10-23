# Microsoft IME icon guidelines: 32-bit alpha at every DPI; branding is a
# white box with black glyph, modes are white glyphs with a 50% black outline.
# Checked-in ICOs are build inputs; ordinary builds do not render fonts.
param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'icons'))
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$fontFamily = New-Object System.Drawing.FontFamily('Microsoft JhengHei UI')
$sizes = @(16,20,24,32,40,48,64,256)
foreach ($asset in @(@{file='cantonese.ico'; glyph=[char]0x7cb5; brand=$true},
                     @{file='mode-cantonese.ico'; glyph=[char]0x7cb5; brand=$false},
                     @{file='mode-english.ico'; glyph=[char]0x82f1; brand=$false})) {
    $images = @()
    foreach ($size in $sizes) {
        $bitmap = New-Object System.Drawing.Bitmap($size,$size,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $scale = $size/16.0
        $path = New-Object System.Drawing.Drawing2D.GraphicsPath
        $path.AddString([string]$asset.glyph,$fontFamily,[int][System.Drawing.FontStyle]::Bold,
            [single]($size * 0.80),[System.Drawing.PointF]::Empty,[System.Drawing.StringFormat]::GenericTypographic)
        $bounds = $path.GetBounds()
        $transform = New-Object System.Drawing.Drawing2D.Matrix
        $transform.Translate([single](($size-$bounds.Width)/2-$bounds.X),[single](($size-$bounds.Height)/2-$bounds.Y))
        $path.Transform($transform)
        $outline = [System.Drawing.Color]::FromArgb(128,0,0,0)
        if ($asset.brand) {
            $rect = New-Object System.Drawing.RectangleF([single]$scale,[single]$scale,[single]($size-2*$scale),[single]($size-2*$scale))
            $graphics.FillRectangle([System.Drawing.Brushes]::White,$rect)
            $pen = New-Object System.Drawing.Pen($outline,[single]$scale)
            $graphics.DrawRectangle($pen,$rect.X,$rect.Y,$rect.Width,$rect.Height)
            $graphics.FillPath([System.Drawing.Brushes]::Black,$path)
        } else {
            # A pen centered on the contour followed by a white fill leaves a
            # one-pixel outer stroke at 16px, scaled with the requested DPI.
            $pen = New-Object System.Drawing.Pen($outline,[single](2*$scale))
            $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $graphics.DrawPath($pen,$path)
            $graphics.FillPath([System.Drawing.Brushes]::White,$path)
        }
        $graphics.Flush()
        $stream = New-Object System.IO.MemoryStream
        $writer = New-Object System.IO.BinaryWriter($stream)
        $bits = 32
        $stride = [int]([Math]::Ceiling(($size * $bits)/32.0)*4)
        $maskStride = [int]([Math]::Ceiling($size/32.0)*4)
        $writer.Write([int]40); $writer.Write([int]$size); $writer.Write([int]($size*2))
        $writer.Write([int16]1); $writer.Write([int16]$bits); $writer.Write([int]0)
        $writer.Write([int](($stride+$maskStride)*$size)); $writer.Write([int]0); $writer.Write([int]0)
        $writer.Write([int]0); $writer.Write([int]0)
        for ($y=$size-1; $y -ge 0; $y--) {
            $row = New-Object byte[] $stride
            for ($x=0; $x -lt $size; $x++) {
                $pixel = $bitmap.GetPixel($x,$y)
                $row[$x*4] = $pixel.B; $row[$x*4+1] = $pixel.G
                $row[$x*4+2] = $pixel.R; $row[$x*4+3] = $pixel.A
            }
            $writer.Write($row)
        }
        for ($y=$size-1; $y -ge 0; $y--) {
            $row = New-Object byte[] $maskStride
            for ($x=0; $x -lt $size; $x++) {
                if ($bitmap.GetPixel($x,$y).A -eq 0) { $row[[int][Math]::Floor($x/8)] = $row[[int][Math]::Floor($x/8)] -bor (128 -shr ($x%8)) }
            }
            $writer.Write($row)
        }
        $writer.Flush(); $images += ,$stream.ToArray()
        $writer.Dispose(); $stream.Dispose(); $pen.Dispose(); $transform.Dispose(); $path.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
    }
    $path = Join-Path $OutputDirectory $asset.file
    $file = [System.IO.File]::Create($path); $writer = New-Object System.IO.BinaryWriter($file)
    $writer.Write([int16]0); $writer.Write([int16]1); $writer.Write([int16]$images.Count)
    $offset = 6 + 16*$images.Count
    for ($i=0; $i -lt $sizes.Count; $i++) {
        $dimension = if ($sizes[$i] -eq 256) {0} else {$sizes[$i]}
        $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
        $writer.Write([byte]0); $writer.Write([byte]0); $writer.Write([int16]1)
        $writer.Write([int16]32); $writer.Write([int]$images[$i].Length); $writer.Write([int]$offset)
        $offset += $images[$i].Length
    }
    foreach ($bytes in $images) { $writer.Write([byte[]]$bytes) }
    $writer.Dispose(); $file.Dispose()
    Get-FileHash -LiteralPath $path -Algorithm SHA256
}
$fontFamily.Dispose()
