var PHOTO_RETENTION_MS = 24 * 3600 * 1000;
var apiConfig = require('./apiConfig.js');
var authService = require('./authService.js');

/**
 * 统一图片处理服务层
 * 所有工具页复用此模块，避免重复写上传/保存逻辑
 */

/**
 * 选择图片（相册或拍摄）
 * @returns {Promise<string>} tempFilePath
 */
function chooseImage() {
  return new Promise(function(resolve, reject) {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: function(res) {
        resolve(res.tempFiles[0].tempFilePath);
      },
      fail: function(err) {
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '选择图片失败', icon: 'none' });
        }
        reject(err);
      }
    });
  });
}

/**
 * 拍照
 * @returns {Promise<string>} tempFilePath
 */
function takePhoto() {
  return new Promise(function(resolve, reject) {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera'],
      success: function(res) {
        resolve(res.tempFiles[0].tempFilePath);
      },
      fail: function(err) {
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '拍照失败', icon: 'none' });
        }
        reject(err);
      }
    });
  });
}

/**
 * 获取图片元信息
 * @param {string} path 图片路径
 * @returns {Promise<object>} { width, height, path }
 */
function getImageMeta(path) {
  return new Promise(function(resolve, reject) {
    wx.getImageInfo({
      src: path,
      success: function(info) {
        resolve({ width: info.width, height: info.height, path: info.path || path });
      },
      fail: function(err) {
        wx.showToast({ title: '图片加载失败', icon: 'none' });
        reject(err);
      }
    });
  });
}

/**
 * 绘制图片到 Canvas
 * @param {object} canvas wx.canvas对象
 * @param {string} imagePath
 * @param {number} imgW 原图宽
 * @param {number} imgH 原图高
 * @param {number} targetW 目标宽
 * @param {number} targetH 目标高
 * @param {string} mode 'contain' | 'cover'
 * @returns {Promise}
 */
function drawImageToCanvas(canvas, imagePath, imgW, imgH, targetW, targetH, mode) {
  mode = mode || 'contain';
  return new Promise(function(resolve, reject) {
    var ctx = canvas.getContext('2d');
    var img = canvas.createImage();
    img.onload = function() {
      var scaleX = targetW / imgW;
      var scaleY = targetH / imgH;
      var scale, drawW, drawH, drawX, drawY;

      if (mode === 'cover') {
        scale = Math.max(scaleX, scaleY);
      } else {
        scale = Math.min(scaleX, scaleY);
      }

      drawW = imgW * scale;
      drawH = imgH * scale;
      drawX = (targetW - drawW) / 2;
      drawY = (targetH - drawH) / 2;

      ctx.drawImage(img, drawX, drawY, drawW, drawH);
      resolve();
    };
    img.onerror = function() { reject(new Error('图片渲染失败')); };
    img.src = imagePath;
  });
}

/**
 * 导出 Canvas 为临时文件
 * @param {object} canvas
 * @param {string} fileType 'jpg' or 'png'
 * @param {number} quality 0-1
 * @returns {Promise<string>} tempFilePath
 */
function exportCanvas(canvas, fileType, quality) {
  return new Promise(function(resolve, reject) {
    wx.canvasToTempFilePath({
      canvas: canvas,
      fileType: fileType || 'jpg',
      quality: quality || 0.95,
      success: function(res) { resolve(res.tempFilePath); },
      fail: function(err) { reject(err); }
    });
  });
}

/**
 * 保存图片到系统相册
 * @param {string} filePath
 * @returns {Promise}
 */
function saveToAlbum(filePath) {
  return new Promise(function(resolve, reject) {
    wx.saveImageToPhotosAlbum({
      filePath: filePath,
      success: function() {
        wx.showToast({ title: '已保存到相册', icon: 'success' });
        resolve();
      },
      fail: function(err) {
        if (err.errMsg.indexOf('auth') !== -1 || err.errMsg.indexOf('deny') !== -1) {
          wx.showModal({
            title: '需要权限',
            content: '请在设置中开启保存到相册权限',
            confirmText: '去设置',
            success: function(res) { if (res.confirm) wx.openSetting(); }
          });
        } else {
          wx.showToast({ title: '保存失败，请重试', icon: 'none' });
        }
        reject(err);
      }
    });
  });
}

/**
 * 保存处理记录到本地存储
 * @param {object} record { id, type, title, imagePath, originalPath, specId, specName, sizeText, createdAt, expireAt }
 */
function getLocalPhotoList() {
  if (!authService.isLoggedIn()) {
    return [];
  }
  return wx.getStorageSync(authService.getPhotoStorageKey()) || [];
}

function setLocalPhotoList(list) {
  if (!authService.isLoggedIn()) {
    return;
  }
  wx.setStorageSync(authService.getPhotoStorageKey(), list || []);
  wx.setStorageSync('myPhotos', list || []);
}

function normalizeRecord(record) {
  record = record || {};
  return {
    id: record.id || ('photo_' + Date.now()),
    imagePath: record.imagePath || '',
    imageUrl: record.imageUrl || record.remoteUrl || '',
    thumbnailUrl: record.thumbnailUrl || record.imageUrl || record.remoteUrl || '',
    originalPath: record.originalPath || '',
    type: record.type || 'tool',
    title: record.title || '证件照',
    specId: record.specId || '',
    specName: record.specName || '',
    sizeText: record.sizeText || '',
    widthPx: record.widthPx || 0,
    heightPx: record.heightPx || 0,
    backgroundColor: record.backgroundColor || record.bgColorName || '',
    createdAt: record.createdAt || Date.now(),
    expireAt: record.expireAt || ((record.createdAt || Date.now()) + PHOTO_RETENTION_MS)
  };
}

function savePhotoRecord(record) {
  var item = normalizeRecord(record);
  if (authService.isLoggedIn()) {
    var list = getLocalPhotoList();
    list.unshift(item);
    setLocalPhotoList(list);
  } else {
    var guest = wx.getStorageSync('myPhotos:guest') || [];
    guest.unshift(item);
    wx.setStorageSync('myPhotos:guest', guest);
  }

  return new Promise(function(resolve) {
    if (!authService.isLoggedIn() || !item.imageUrl || typeof wx.request !== 'function') {
      resolve({ success: false, localOnly: true, record: item });
      return;
    }
    wx.request({
      url: apiConfig.API_BASE_URL + '/api/user/photos',
      method: 'POST',
      header: Object.assign({ 'content-type': 'application/json' }, authService.getAuthHeader()),
      data: {
        imageUrl: item.imageUrl,
        thumbnailUrl: item.thumbnailUrl || item.imageUrl,
        specId: item.specId,
        specName: item.specName || item.title,
        widthPx: item.widthPx,
        heightPx: item.heightPx,
        backgroundColor: item.backgroundColor,
        sizeText: item.sizeText,
        source: item.type || 'id_photo',
        type: item.type || 'idPhoto'
      },
      timeout: 15000,
      success: function(res) {
        var data = res.data || {};
        if (res.statusCode === 200 && data.success && data.photo) {
          item.id = data.photo.id || item.id;
          item.imageUrl = data.photo.imageUrl || item.imageUrl;
          item.thumbnailUrl = data.photo.thumbnailUrl || item.thumbnailUrl;
          var list = getLocalPhotoList().filter(function(local) {
            return local.id !== record.id && local.id !== item.id;
          });
          list.unshift(item);
          setLocalPhotoList(list);
          resolve({ success: true, record: item, photo: data.photo });
          return;
        }
        resolve({ success: false, localOnly: true, record: item, error: data.message || 'sync failed' });
      },
      fail: function(err) {
        resolve({ success: false, localOnly: true, record: item, error: err && err.errMsg });
      }
    });
  });
}

/**
 * 清理过期照片（超过24小时）
 */
function cleanupExpiredPhotos() {
  var now = Date.now();
  var list = getLocalPhotoList();
  var valid = [];
  for (var i = 0; i < list.length; i++) {
    if (!list[i].expireAt || list[i].expireAt > now) {
      valid.push(list[i]);
    }
  }
  if (valid.length !== list.length) {
    setLocalPhotoList(valid);
  }
  return valid;
}

/**
 * 获取所有照片记录
 * @returns {Array}
 */
function getPhotoRecords() {
  if (!authService.isLoggedIn()) {
    return [];
  }
  return cleanupExpiredPhotos();
}

function fetchPhotoRecords() {
  return new Promise(function(resolve, reject) {
    if (!authService.isLoggedIn()) {
      resolve([]);
      return;
    }
    if (typeof wx.request !== 'function') {
      resolve(getPhotoRecords());
      return;
    }
    wx.request({
      url: apiConfig.API_BASE_URL + '/api/user/photos',
      method: 'GET',
      header: authService.getAuthHeader(),
      timeout: 15000,
      success: function(res) {
        var data = res.data || {};
        if (res.statusCode === 200 && data.success && Array.isArray(data.photos)) {
          var list = data.photos.map(function(item) {
            return {
              id: item.id,
              imagePath: item.imageUrl || '',
              imageUrl: item.imageUrl || '',
              thumbnailUrl: item.thumbnailUrl || item.imageUrl || '',
              type: item.type || item.source || 'idPhoto',
              title: item.specName || '证件照',
              specId: item.specId || '',
              specName: item.specName || '证件照',
              sizeText: item.sizeText || '',
              widthPx: item.widthPx || 0,
              heightPx: item.heightPx || 0,
              backgroundColor: item.backgroundColor || '',
              createdAt: item.createdAtEpoch ? Math.round(item.createdAtEpoch * 1000) : Date.now(),
              expireAt: item.expiresAtEpoch ? Math.round(item.expiresAtEpoch * 1000) : (Date.now() + PHOTO_RETENTION_MS)
            };
          });
          setLocalPhotoList(list);
          resolve(list);
          return;
        }
        reject(new Error(data.message || '我的电子照读取失败'));
      },
      fail: function(err) {
        reject(new Error((err && err.errMsg) || '我的电子照读取失败'));
      }
    });
  });
}

/**
 * 删除照片记录
 * @param {string} id
 */
function deletePhotoRecord(id) {
  var list = getLocalPhotoList().filter(function(item) { return item.id !== id; });
  setLocalPhotoList(list);
  return new Promise(function(resolve, reject) {
    if (!authService.isLoggedIn() || typeof wx.request !== 'function') {
      resolve({ success: true, localOnly: true });
      return;
    }
    wx.request({
      url: apiConfig.API_BASE_URL + '/api/user/photos/' + encodeURIComponent(id),
      method: 'DELETE',
      header: authService.getAuthHeader(),
      timeout: 15000,
      success: function(res) {
        var data = res.data || {};
        if (res.statusCode === 200 && data.success) {
          resolve(data);
        } else {
          reject(new Error(data.message || '删除失败'));
        }
      },
      fail: function(err) {
        reject(new Error((err && err.errMsg) || '删除失败'));
      }
    });
  });
}

function downloadPhotoRecord(id) {
  return new Promise(function(resolve, reject) {
    if (!authService.isLoggedIn()) {
      reject(new Error('AUTH_REQUIRED'));
      return;
    }
    wx.downloadFile({
      url: apiConfig.API_BASE_URL + '/api/user/photos/' + encodeURIComponent(id) + '/download',
      header: authService.getAuthHeader(),
      timeout: 30000,
      success: function(res) {
        if (res.statusCode === 200 && res.tempFilePath) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error('下载失败，当前用户无权访问该电子照'));
        }
      },
      fail: function(err) {
        reject(new Error((err && err.errMsg) || '下载失败'));
      }
    });
  });
}

module.exports = {
  chooseImage: chooseImage,
  takePhoto: takePhoto,
  getImageMeta: getImageMeta,
  drawImageToCanvas: drawImageToCanvas,
  exportCanvas: exportCanvas,
  saveToAlbum: saveToAlbum,
  savePhotoRecord: savePhotoRecord,
  cleanupExpiredPhotos: cleanupExpiredPhotos,
  getPhotoRecords: getPhotoRecords,
  fetchPhotoRecords: fetchPhotoRecords,
  deletePhotoRecord: deletePhotoRecord,
  downloadPhotoRecord: downloadPhotoRecord,
  PHOTO_RETENTION_MS: PHOTO_RETENTION_MS
};
