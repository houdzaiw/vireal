import Foundation
import ImageIO
import UniformTypeIdentifiers

enum PhotoProcessor {
    @concurrent static func jpeg(from data: Data) async throws -> Data {
        guard data.count <= 30 * 1024 * 1024,
              let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: 2048,
              ] as CFDictionary) else { throw ClientError.invalidMedia }
        try Task.checkCancellation()
        for quality in [0.85, 0.65, 0.45] {
            let result = NSMutableData()
            guard let destination = CGImageDestinationCreateWithData(result, UTType.jpeg.identifier as CFString, 1, nil) else { throw ClientError.invalidMedia }
            // Encoding a new image strips original EXIF/location and bakes in orientation.
            CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
            guard CGImageDestinationFinalize(destination) else { throw ClientError.invalidMedia }
            if result.length <= 5 * 1024 * 1024 { return result as Data }
        }
        throw ClientError.photoTooLarge
    }
}
