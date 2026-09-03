var wx = require('../../utils/platform/alipayWxCompat.js');
// ====== 实用工具 ======
Page({
  data: {
    tools: [
      { id: 'verifyPhoto', name: 'AI 证件照质检', desc: '本地大模型智能评估', icon: '🔍', bg: '#e0f7fa', badge: 'NEW' },
      { id: 'changeBg', name: '证件照更换底色', desc: '一键更换背景色', icon: '🎨', bg: '#fce4ec' },
      { id: 'customSize', name: '自定义尺寸', desc: '自定义像素尺寸', icon: '📐', bg: '#f3e5f5', badge: 'HOT' },
      { id: 'editImage', name: '图片编辑', desc: '裁剪压缩与调色', icon: '✏️', bg: '#e3f2fd' },
      { id: 'formatConvert', name: '图片格式转换', desc: '多种格式互转', icon: '🔄', bg: '#e8f5e9' },
      { id: 'colorize', name: '黑白图片上色', desc: '智能识别填充色彩', icon: '🎭', bg: '#fff3e0' },
      { id: 'addWatermark', name: '图片加水印', desc: '文字图片水印添加', icon: '💧', bg: '#e1f5fe' },
      { id: 'removeWatermark', name: '图片去水印', desc: '框选水印智能处理', icon: '🧹', bg: '#fbe9e7' },
      { id: 'layout', name: '自定义排版', desc: '多图排版更美观', icon: '🧩', bg: '#f3e5f5' },
      { id: 'collect', name: '证件照采集', desc: '在线拍摄快速采集', icon: '📷', bg: '#e3f2fd' }
    ]
  },

  openTool: function(e) {
    var id = e.currentTarget.dataset.id;
    if (id) {
      wx.navigateTo({ url: '/pages/tool-detail/tool-detail?type=' + id });
    }
  },

  shareApp: function() {
    wx.showShareMenu({ withShareTicket: true });
  },

  onShareAppMessage: function() {
    return { title: '证件照生成器 - 快速制作标准证件照', path: '/pages/index/index' };
  }
});
