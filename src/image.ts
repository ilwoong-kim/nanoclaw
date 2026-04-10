import sharp from 'sharp';
import path from 'path';
import fs from 'fs';
import { logger } from './logger.js';
import { ImageAttachment } from './types.js';

const MAX_DIMENSION = 1568;
const JPEG_QUALITY = 85;
const MAX_IMAGES_PER_BATCH = 5;

export { MAX_IMAGES_PER_BATCH };

/**
 * Resize an image so the longest side is at most MAX_DIMENSION,
 * convert to JPEG, and save to outputDir.
 * Returns null on error (never throws — image failure must not block message delivery).
 *
 * @param containerBasePath - container-relative prefix for the output path (e.g. "/workspace/group/attachments")
 */
export async function processImage(
  inputPath: string,
  outputDir: string,
  containerBasePath: string,
): Promise<ImageAttachment | null> {
  try {
    const outputName = `processed_${Date.now()}_${Math.random().toString(36).slice(2, 6)}.jpg`;
    const outputPath = path.join(outputDir, outputName);

    fs.mkdirSync(outputDir, { recursive: true });

    await sharp(inputPath)
      .resize(MAX_DIMENSION, MAX_DIMENSION, {
        fit: 'inside',
        withoutEnlargement: true,
      })
      .jpeg({ quality: JPEG_QUALITY })
      .toFile(outputPath);

    logger.info({ inputPath, outputPath }, 'Image processed for vision');

    return {
      path: `${containerBasePath}/${outputName}`,
      mediaType: 'image/jpeg',
      filename: outputName,
    };
  } catch (err) {
    logger.warn(
      { inputPath, err },
      'Failed to process image, falling back to text-only',
    );
    return null;
  }
}

/**
 * Detect MIME type from file extension.
 */
export function detectMimeType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  const mimeMap: Record<string, string> = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
  };
  return mimeMap[ext] || 'image/jpeg';
}
