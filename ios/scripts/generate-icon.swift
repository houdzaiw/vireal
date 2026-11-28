import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let output = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
    .appendingPathComponent("Vireal/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png")
let context = CGContext(data: nil, width: 1024, height: 1024, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
let colors = [CGColor(red: 0.13, green: 0.28, blue: 0.34, alpha: 1), CGColor(red: 0.035, green: 0.045, blue: 0.055, alpha: 1)]
let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0,1])!
context.drawLinearGradient(gradient, start: CGPoint(x: 0, y: 1024), end: CGPoint(x: 1024, y: 0), options: [.drawsBeforeStartLocation,.drawsAfterEndLocation])
let v = CGMutablePath()
v.move(to: CGPoint(x: 210, y: 760)); v.addLines(between: [CGPoint(x: 370,y:760),CGPoint(x:512,y:368),CGPoint(x:654,y:760),CGPoint(x:814,y:760),CGPoint(x:588,y:232),CGPoint(x:436,y:232)]); v.closeSubpath()
context.addPath(v); context.setFillColor(CGColor(red: 0.72,green: 0.95,blue: 1,alpha: 1)); context.fillPath()
let star = CGMutablePath(); star.move(to: CGPoint(x: 822,y:320))
star.addLines(between: [CGPoint(x: 844,y:272),CGPoint(x:892,y:250),CGPoint(x:844,y:228),CGPoint(x:822,y:180),CGPoint(x:800,y:228),CGPoint(x:752,y:250),CGPoint(x:800,y:272)]);star.closeSubpath()
context.addPath(star);context.setFillColor(CGColor(red:0.44,green:0.85,blue:0.93,alpha:1));context.fillPath()
let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(destination, context.makeImage()!, nil)
precondition(CGImageDestinationFinalize(destination))
