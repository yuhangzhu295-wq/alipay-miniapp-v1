// ====== 首页 ======
var idPhotoEntry = require('../../utils/idPhotoEntry.js');
Page({
  data: {
    coreFeatures: [
      {
        id: 'idPhoto',
        title: '证件照',
        desc: '一键生成合规证件照',
        icon: 'id',
        className: 'core-id',
        route: '/pages/specs/specs'
      },
      {
        id: 'removeWatermark',
        title: '图片去水印',
        desc: '智能去除水印',
        icon: 'wm',
        className: 'core-watermark',
        route: '/pages/tool-detail/tool-detail?type=removeWatermark'
      },
      {
        id: 'compressImage',
        title: '图片大小压缩',
        desc: '快速压缩图片大小',
        icon: 'zip',
        className: 'core-compress',
        route: '/pages/tool-detail/tool-detail?type=editImage'
      }
    ],
    hotSpecs: [
      { id: 'yicun', name: '一寸', size: '25×35mm', icon: 'person', thumbBg: '#eef3ff' },
      { id: 'ercun', name: '二寸', size: '35×49mm', icon: 'person2', thumbBg: '#fff4e7' },
      { id: 'dayicun', name: '大一寸', size: '33×48mm', icon: 'person3', thumbBg: '#ecfbf2' },
      { id: 'xiaoyicun', name: '小一寸', size: '22×32mm', icon: 'person4', thumbBg: '#fff7df' },
      { id: 'jianli', name: '简历照片', size: '25×35mm', icon: 'doc', thumbBg: '#edf5ff' }
    ],
    moreTools: [
      { id: 'editImage', name: '图片编辑', icon: 'edit', route: '/pages/tool-detail/tool-detail?type=editImage' },
      { id: 'changeBg', name: '证件照换底色', icon: 'palette', route: '/pages/tool-detail/tool-detail?type=changeBg' },
      { id: 'customSize', name: '自定义尺寸', icon: 'ruler', route: '/pages/tool-detail/tool-detail?type=customSize' },
      { id: 'formatConvert', name: '图片格式转换', icon: 'convert', route: '/pages/tool-detail/tool-detail?type=formatConvert' },
      { id: 'colorize', name: '黑白图片上色', icon: 'color', route: '/pages/tool-detail/tool-detail?type=colorize' },
      { id: 'more', name: '更多功能', icon: 'more', route: '/pages/tools/tools' }
    ]
  },

  onLoad: function() {
    wx.setNavigationBarTitle({ title: '' });
  },

  goSearch: function() {
    wx.navigateTo({ url: '/pages/specs/specs' });
  },

  goSpecs: function() {
    wx.navigateTo({ url: '/pages/specs/specs' });
  },

  goCustomSize: function() {
    wx.navigateTo({ url: '/pages/tool-detail/tool-detail?type=customSize' });
  },

  goCoreFeature: function(e) {
    var route = e.currentTarget.dataset.route;
    if (route) {
      wx.navigateTo({ url: route });
    }
  },

  selectHotSpec: function(e) {
    var id = e.currentTarget.dataset.id;
    idPhotoEntry.openCaptureGuide(id);
  },

  goTool: function(e) {
    var route = e.currentTarget.dataset.route;
    if (!route) return;
    if (route.indexOf('/pages/tools/tools') === 0) {
      wx.switchTab({ url: route });
      return;
    }
    wx.navigateTo({ url: route });
  },

  onShareAppMessage: function() {
    return { title: '证件照与图片工具', path: '/pages/index/index' };
  }
});
