// Run on macOS with: xcrun swift GenerateIcons.swift OUTPUT_RESOURCE_DIRECTORY
import AppKit
import CoreGraphics

@MainActor
func generateIcons(at destination: URL) throws {
    let files = FileManager.default
    try files.createDirectory(at: destination, withIntermediateDirectories: true)
    let iconset = destination.appendingPathComponent("CantoneseIME.iconset")
    try files.createDirectory(at: iconset, withIntermediateDirectories: true)
    for points in [16, 32, 128, 256, 512] {
        for scale in [1, 2] {
            let pixels = points * scale
            guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
                bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
                  let graphics = NSGraphicsContext(bitmapImageRep: bitmap) else { throw CocoaError(.fileWriteUnknown) }
            NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = graphics
            let side = CGFloat(pixels)
            NSColor(srgbRed: 27.0 / 255, green: 83.0 / 255, blue: 112.0 / 255, alpha: 1).setFill()
            NSBezierPath(roundedRect: NSRect(x: 0, y: 0, width: side, height: side),
                         xRadius: side * 0.13, yRadius: side * 0.13).fill()
            let font = NSFont(name: "PingFangTC-Semibold", size: side * 0.79) ?? NSFont.systemFont(ofSize: side * 0.79)
            let style: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.white]
            let glyph = "粵" as NSString
            let measured = glyph.size(withAttributes: style)
            glyph.draw(at: NSPoint(x: (side - measured.width) / 2, y: (side - measured.height) / 2), withAttributes: style)
            NSGraphicsContext.restoreGraphicsState()
            guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
            let suffix = scale == 2 ? "@2x" : ""
            try png.write(to: iconset.appendingPathComponent("icon_\(points)x\(points)\(suffix).png"))
        }
    }
    let iconutil = Process()
    iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
    iconutil.arguments = ["-c", "icns", iconset.path, "-o", destination.appendingPathComponent("CantoneseIME.icns").path]
    try iconutil.run(); iconutil.waitUntilExit()
    guard iconutil.terminationStatus == 0 else { throw CocoaError(.fileWriteUnknown) }
    for (name, text) in [("MenuCantonese", "粵"), ("MenuEnglish", "英")] {
        let url = destination.appendingPathComponent(name + ".pdf")
        var rectangle = CGRect(x: 0, y: 0, width: 18, height: 18)
        guard let context = CGContext(url as CFURL, mediaBox: &rectangle, nil) else { throw CocoaError(.fileWriteUnknown) }
        context.beginPDFPage(nil)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
        let font = NSFont(name: "PingFangTC-Medium", size: 15) ?? NSFont.systemFont(ofSize: 15)
        let style: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.black]
        let glyph = text as NSString, size = glyph.size(withAttributes: style)
        glyph.draw(at: NSPoint(x: (18 - size.width) / 2, y: (18 - size.height) / 2), withAttributes: style)
        NSGraphicsContext.restoreGraphicsState()
        context.endPDFPage(); context.closePDF()
    }
}

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write(Data("Usage: GenerateIcons.swift OUTPUT_DIRECTORY\n".utf8))
    exit(2)
}
try MainActor.assumeIsolated {
    try generateIcons(at: URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true))
}
