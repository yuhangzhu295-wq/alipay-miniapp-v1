const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');
const minidevModule = require('minidev');

const minidev = minidevModule.minidev || minidevModule.default || minidevModule;
const ROOT = path.resolve(__dirname, '..', '..');
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-migration');
const QR_PNG = path.join(REPORT_DIR, 'minidev-login-qr.png');
const QR_TXT = path.join(REPORT_DIR, 'minidev-login-qr-url.txt');
const STATUS_JSON = path.join(REPORT_DIR, 'minidev-login-status.json');

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
}

async function main() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  const events = [];
  writeJson(STATUS_JSON, {
    startedAt: new Date().toISOString(),
    status: 'STARTED',
    qrPng: QR_PNG,
  });

  await minidev.login({ clientType: 'alipay' }, (loginTask) => {
    loginTask.on('qrcode-generated', async (qrCodeUrl) => {
      events.push({ type: 'qrcode-generated', at: new Date().toISOString() });
      fs.writeFileSync(QR_TXT, qrCodeUrl + '\n');
      await QRCode.toFile(QR_PNG, qrCodeUrl, {
        type: 'png',
        width: 520,
        margin: 2,
        errorCorrectionLevel: 'M',
      });
      writeJson(STATUS_JSON, {
        status: 'QR_READY',
        qrPng: QR_PNG,
        qrText: QR_TXT,
        events,
      });
      console.log(JSON.stringify({ status: 'QR_READY', qrPng: QR_PNG, qrText: QR_TXT }));
    });
    loginTask.on('scan', () => {
      events.push({ type: 'scan', at: new Date().toISOString() });
      writeJson(STATUS_JSON, { status: 'SCANNED', qrPng: QR_PNG, events });
      console.log(JSON.stringify({ status: 'SCANNED' }));
    });
    loginTask.on('success', () => {
      events.push({ type: 'success', at: new Date().toISOString() });
      writeJson(STATUS_JSON, { status: 'SUCCESS', qrPng: QR_PNG, events });
      console.log(JSON.stringify({ status: 'SUCCESS' }));
    });
  });

  writeJson(STATUS_JSON, {
    status: 'SUCCESS',
    qrPng: QR_PNG,
    events,
  });
}

main().catch((error) => {
  writeJson(STATUS_JSON, {
    status: 'FAILED',
    message: error && error.message || String(error),
    errorCode: error && error.errorCode || '',
    scope: error && error.scope || '',
    qrPng: QR_PNG,
  });
  console.error(error);
  process.exit(1);
});
