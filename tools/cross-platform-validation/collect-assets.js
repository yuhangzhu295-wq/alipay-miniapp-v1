/*
 * Download only public Pexels test images into the validation report tree.
 * This file is deliberately outside alipay/ so none of these fixtures can
 * enter a production mini-program package.
 */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const ASSET_DIR = path.join(ROOT, 'reports', 'alipay-final-validation', 'assets');
const MANIFEST = path.join(ROOT, 'reports', 'alipay-final-validation', '01-assets', 'asset-manifest.json');

// Pexels License: https://www.pexels.com/license/
// These URLs are public CDN variants of photographs listed on Pexels.
const ASSETS = [
  {
    id: 'portrait_A',
    file: 'portrait_A.jpg',
    sourceUrl: 'https://images.pexels.com/photos/220453/pexels-photo-220453.jpeg?auto=compress&cs=tinysrgb&w=1800',
    purpose: 'normal single-person front portrait with a simple background',
  },
  {
    id: 'portrait_B',
    file: 'portrait_B.jpg',
    sourceUrl: 'https://images.pexels.com/photos/774909/pexels-photo-774909.jpeg?auto=compress&cs=tinysrgb&w=1800',
    purpose: 'normal single-person front portrait with hair detail',
  },
  {
    id: 'portrait_C',
    file: 'portrait_C.jpg',
    sourceUrl: 'https://images.pexels.com/photos/614810/pexels-photo-614810.jpeg?auto=compress&cs=tinysrgb&w=1800',
    purpose: 'normal single-person portrait with a different environment',
  },
  {
    id: 'negative_group',
    file: 'negative_group.jpg',
    sourceUrl: 'https://images.pexels.com/photos/3184360/pexels-photo-3184360.jpeg?auto=compress&cs=tinysrgb&w=1800',
    purpose: 'negative multi-person identity-photo input',
  },
  {
    id: 'negative_profile',
    file: 'negative_profile.jpg',
    sourceUrl: 'https://images.pexels.com/photos/1681010/pexels-photo-1681010.jpeg?auto=compress&cs=tinysrgb&w=1800',
    purpose: 'negative profile-facing identity-photo input',
  },
  {
    id: 'watermark_source',
    file: 'watermark_source.jpg',
    sourceUrl: 'https://images.pexels.com/photos/373912/pexels-photo-373912.jpeg?auto=compress&cs=tinysrgb&w=2200',
    purpose: 'public ordinary scene source for watermark, compression, conversion and edit checks',
  },
];

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function jpegDimensions(buffer) {
  if (buffer.readUInt16BE(0) !== 0xffd8) return null;
  let offset = 2;
  while (offset + 9 < buffer.length) {
    if (buffer[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    const marker = buffer[offset + 1];
    offset += 2;
    if (marker === 0xd8 || marker === 0xd9) continue;
    const length = buffer.readUInt16BE(offset);
    const sof = marker >= 0xc0 && marker <= 0xc3;
    if (sof && offset + 7 < buffer.length) {
      return {
        width: buffer.readUInt16BE(offset + 5),
        height: buffer.readUInt16BE(offset + 3),
        format: 'JPEG',
      };
    }
    offset += length;
  }
  return null;
}

async function fetchAsset(asset) {
  const outputPath = path.join(ASSET_DIR, asset.file);
  let data;
  if (fs.existsSync(outputPath)) {
    data = fs.readFileSync(outputPath);
  } else {
    const response = await fetch(asset.sourceUrl, {
      headers: { 'User-Agent': 'photo-generator-validation/1.0' },
      redirect: 'follow',
    });
    if (!response.ok) throw new Error(`${asset.id}: HTTP ${response.status}`);
    data = Buffer.from(await response.arrayBuffer());
    if (data.length < 4096) throw new Error(`${asset.id}: downloaded body is unexpectedly small`);
    fs.writeFileSync(outputPath, data);
  }
  const dimensions = jpegDimensions(data);
  if (!dimensions) throw new Error(`${asset.id}: expected a JPEG image`);
  return {
    id: asset.id,
    sourceUrl: asset.sourceUrl,
    sourceSite: 'Pexels',
    licenseInfo: 'Pexels License (https://www.pexels.com/license/)',
    localPath: path.relative(ROOT, outputPath).replace(/\\/g, '/'),
    sha256: sha256(data),
    bytes: data.length,
    width: dimensions.width,
    height: dimensions.height,
    format: dimensions.format,
    testPurpose: asset.purpose,
  };
}

async function main() {
  fs.mkdirSync(ASSET_DIR, { recursive: true });
  fs.mkdirSync(path.dirname(MANIFEST), { recursive: true });
  const records = [];
  for (const asset of ASSETS) records.push(await fetchAsset(asset));
  const manifest = {
    generatedAt: new Date().toISOString(),
    collectionPolicy: 'Public Pexels images only. Generated derivatives are written outside the product package.',
    assets: records,
  };
  fs.writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify(manifest, null, 2));
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
