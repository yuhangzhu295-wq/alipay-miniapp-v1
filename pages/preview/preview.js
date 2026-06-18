// ========== 预览证件照 ==========
var specs = require('../../utils/specs.js');
var imageService = require('../../utils/imageService.js');

Page({
  data: {
    photoSrc: '',
    bgColor: '#1a73e8',
    bgName: '蓝',
    specName: '一寸',
    specId: 'yicun',
    specData: null,
    changedBgImage: ''
  },

  onLoad: function(options) {
    var data = {};
    if (options.src) data.photoSrc = decodeURIComponent(options.src);
    if (options.color) data.bgColor = decodeURIComponent(options.color);
    if (options.spec) {
      data.specId = options.spec;
      var s = specs.getSpecById(options.spec);
      if (s) {
        data.specName = s.displayName || (s.name + '照');
        data.specData = s;
      } else {
        var names = { yicun: '一寸', ercun: '二寸', dayicun: '大一寸', xiaoyicun: '小一寸', xiaoercun: '小二寸' };
        data.specName = names[options.spec] || '一寸';
      }
    }
    var colorMap = { '#1a73e8': '蓝', '#ffffff': '白', '#e53935': '红', '#81d4fa': '浅蓝', '#9e9e9e': '灰' };
    data.bgName = colorMap[data.bgColor] || '蓝';
    this.setData(data);
  },

  changeBg: function() {
    var that = this;
    wx.showActionSheet({
      itemList: ['蓝色', '白色', '红色', '浅蓝色', '灰色'],
      success: function(res) {
        var colors = ['#1a73e8', '#ffffff', '#e53935', '#81d4fa', '#9e9e9e'];
        var names = ['蓝', '白', '红', '浅蓝', '灰'];
        that.setData({ bgColor: colors[res.tapIndex], bgName: names[res.tapIndex] });
      }
    });
  },

  changeSize: function() {
    wx.navigateTo({ url: '/pages/specs/specs' });
  },

  editPhoto: function() {
    wx.navigateTo({ url: '/pages/tool-detail/tool-detail?type=editImage' });
  },

  layoutPrint: function() {
    wx.navigateTo({ url: '/pages/tool-detail/tool-detail?type=layout' });
  },

  sharePhoto: function() {
    wx.showShareMenu({ withShareTicket: true });
  },

  savePhoto: function() {
    var that = this;
    var src = that.data.changedBgImage || that.data.photoSrc;
    if (!src) { wx.showToast({ title: '没有可保存的图片', icon: 'none' }); return; }

    wx.saveImageToPhotosAlbum({
      filePath: src,
      success: function() {
        wx.showToast({ title: '已保存到相册', icon: 'success' });
        var createdAt = Date.now();
        var record = {
          id: 'photo_' + createdAt,
          imagePath: src,
          imageUrl: src && src.indexOf('http') === 0 ? src : '',
          remoteUrl: src && src.indexOf('http') === 0 ? src : '',
          specId: that.data.specId,
          specName: that.data.specName,
          sizeText: that.data.specData ? that.data.specData.mm + ' | ' + that.data.specData.px : '',
          bgColorName: that.data.bgName,
          backgroundColor: that.data.bgName,
          widthPx: that.data.specData ? (that.data.specData.widthPx || 0) : 0,
          heightPx: that.data.specData ? (that.data.specData.heightPx || 0) : 0,
          type: 'idPhoto',
          createdAt: createdAt,
          expireAt: createdAt + 24 * 3600 * 1000
        };
        var list = wx.getStorageSync('myPhotos') || [];
        list.unshift(record);
        wx.setStorageSync('myPhotos', list);
        imageService.savePhotoRecord(record);
      },
      fail: function(err) {
        if (err.errMsg.indexOf('auth') !== -1 || err.errMsg.indexOf('deny') !== -1) {
          wx.showModal({
            title: '需要权限',
            content: '请在设置中开启相册权限',
            success: function(res) { if (res.confirm) wx.openSetting(); }
          });
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      }
    });
  },

  goBack: function() {
    wx.navigateBack();
  }
});
