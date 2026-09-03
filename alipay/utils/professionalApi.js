var wx = require('./platform/alipayWxCompat.js');
var config = require('./apiConfig.js');
var imageSafetyApi = require('./imageSafetyApi.js');

/**
 * AI 生成职业形象照 - 调用后端 FastAPI 服务
 * @param {string} imagePath - 原图路径
 * @param {string} templateId - 保留兼容参数；正式版仅支持 preserve_original
 * @returns {Promise<string|null>} 形象照结果路径，失败返回 null (进行本地降级)
 */
function generateProfessionalPhoto(imagePath, templateId) {
  return new Promise(function(resolve, reject) {
    if (!config.ENABLE_AI || !config.API_BASE_URL) {
      reject(new Error('生成失败，请重新上传符合要求的照片。'));
      return;
    }

    wx.showLoading({ title: '形象照生成中...' });

    imageSafetyApi.uploadWithSafety({
      url: config.API_BASE_URL + '/api/professional-photo',
      filePath: imagePath,
      name: 'file',
      formData: { templateId: 'preserve_original' },
      timeout: 90000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.success && data.imageUrl) {
            _downloadResult(data.imageUrl).then(resolve).catch(reject);
          } else {
            var apiErr = new Error(data.message || '生成失败，请重新上传符合要求的照片。');
            apiErr.code = data.code || '';
            apiErr.quality = data.quality || null;
            reject(apiErr);
          }
        } catch (e) {
          reject(new Error('生成失败，请重新上传符合要求的照片。'));
        }
      },
      fail: function (err) {
        wx.hideLoading();
        console.error('[professional] upload failed:', err);
        reject(new Error('生成失败，请重新上传符合要求的照片。'));
      }
    }, 'professional_photo');
  });
}

function _downloadResult(imageUrl) {
  return new Promise(function (resolve, reject) {
    var fullUrl = imageUrl;
    if (imageUrl.indexOf('http') !== 0) {
      fullUrl = config.API_BASE_URL + imageUrl;
    }
    wx.downloadFile({
      url: fullUrl,
      timeout: 30000,
      success: function (res) {
        if (res.statusCode === 200) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error('下载结果失败'));
        }
      },
      fail: function (err) {
        reject(err);
      }
    });
  });
}

module.exports = {
  generateProfessionalPhoto: generateProfessionalPhoto
};
