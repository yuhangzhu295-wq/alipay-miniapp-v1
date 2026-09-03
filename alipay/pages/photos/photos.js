var wx = require('../../utils/platform/alipayWxCompat.js');
// ====== 我的电子照 ======
var imageService = require('../../utils/imageService.js');
var authService = require('../../utils/authService.js');
var idPhotoEntry = require('../../utils/idPhotoEntry.js');

Page({
  data: {
    photoList: [],
    hasLogin: false,
    loading: false,
    emptyTitle: '您当前还没有电子照',
    emptyDesc: '点击下方按钮，拍摄您的第一张电子照。',
    actionText: '立即拍摄'
  },

  onShow: function() {
    this.loadPhotos();
  },

  loadPhotos: function() {
    var that = this;
    var hasLogin = authService.isLoggedIn();
    if (!hasLogin) {
      this.setData({
        hasLogin: false,
        photoList: [],
        loading: false,
        emptyTitle: '未登录，点我登录哦！',
        emptyDesc: '授权后只会看到您自己的电子照。',
        actionText: '立即登录'
      });
      return;
    }
    this.setData({
      hasLogin: true,
      loading: true,
      emptyTitle: '您当前还没有电子照',
      emptyDesc: '点击下方按钮，拍摄您的第一张电子照。',
      actionText: '立即拍摄'
    });
    imageService.fetchPhotoRecords().then(function(list) {
      list = that.formatList(list);
      that.setData({ photoList: list, loading: false });
    }).catch(function(err) {
      var fallback = that.formatList(imageService.getPhotoRecords());
      that.setData({ photoList: fallback, loading: false });
      wx.showToast({ title: err && err.message ? err.message : '电子照读取失败', icon: 'none' });
    });
  },

  formatList: function(list) {
    var that = this;
    return (list || []).map(function(item) {
      item.timeText = that.formatTime(item.createdAt);
      if (item.expireAt) {
        item.remainDays = Math.max(0, Math.ceil((item.expireAt - Date.now()) / (24 * 3600 * 1000)));
      }
      return item;
    });
  },

  takePhotoNow: function() {
    if (!authService.isLoggedIn()) {
      wx.navigateTo({ url: '/pages/login/login' });
      return;
    }
    idPhotoEntry.openCaptureGuide('yicun');
  },

  previewPhoto: function(e) {
    var index = e.currentTarget.dataset.index;
    var item = this.data.photoList[index];
    if (item && (item.imagePath || item.imageUrl)) {
      var src = item.imagePath || item.imageUrl;
      wx.previewImage({
        urls: [src],
        current: src
      });
    }
  },

  saveToAlbum: function(e) {
    var that = this;
    var index = e.currentTarget.dataset.index;
    var item = that.data.photoList[index];
    if (!item) return;

    var saveFile = function(path) {
      wx.saveImageToPhotosAlbum({
        filePath: path,
        success: function() {
          wx.showToast({ title: '已保存到相册', icon: 'success' });
        },
        fail: function(err) {
          if (err.errMsg.indexOf('auth') !== -1) {
            wx.showModal({
              title: '需要权限',
              content: '请在设置中开启保存到相册权限',
              success: function(res) { if (res.confirm) wx.openSetting(); }
            });
          } else {
            wx.showToast({ title: '保存失败', icon: 'none' });
          }
        }
      });
    };

    if (item.imagePath && item.imagePath.indexOf('http') !== 0) {
      saveFile(item.imagePath);
      return;
    }

    imageService.downloadPhotoRecord(item.id).then(function(path) {
      saveFile(path);
    }).catch(function(err) {
      wx.showToast({ title: err && err.message ? err.message : '无权下载', icon: 'none' });
    });
  },

  deletePhoto: function(e) {
    var that = this;
    var index = e.currentTarget.dataset.index;
    var item = that.data.photoList[index];
    if (!item) return;
    wx.showModal({
      title: '确认删除',
      content: '删除后无法恢复',
      success: function(res) {
        if (!res.confirm) return;
        imageService.deletePhotoRecord(item.id).then(function() {
          that.loadPhotos();
          wx.showToast({ title: '已删除', icon: 'success' });
        }).catch(function(err) {
          wx.showToast({ title: err && err.message ? err.message : '删除失败', icon: 'none' });
        });
      }
    });
  },

  formatTime: function(ts) {
    var d = new Date(ts);
    var m = d.getMonth() + 1;
    var day = d.getDate();
    var h = d.getHours();
    var min = d.getMinutes();
    return m + '/' + day + ' ' + (h < 10 ? '0' : '') + h + ':' + (min < 10 ? '0' : '') + min;
  }
});
