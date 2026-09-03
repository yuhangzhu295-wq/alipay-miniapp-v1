var wx = require('../../utils/platform/alipayWxCompat.js');
var authService = require('../../utils/authService.js');

Page({
  data: {
    userInfo: null,
    saving: false
  },

  onLoad() {
    var storedUser = wx.getStorageSync('userInfo') || null;
    this.setData({ userInfo: storedUser });
  },

  chooseAvatar(e) {
    var avatarUrl = e.detail && e.detail.avatarUrl;
    var userInfo = Object.assign({}, this.data.userInfo || {}, {
      avatarUrl: avatarUrl || ''
    });
    this.setData({ userInfo: userInfo });
  },

  onNicknameInput(e) {
    var nickName = e.detail && e.detail.value;
    var userInfo = Object.assign({}, this.data.userInfo || {}, {
      nickName: nickName || ''
    });
    this.setData({ userInfo: userInfo });
  },

  saveProfile() {
    var userInfo = this.data.userInfo || {};
    if (!userInfo.avatarUrl && !userInfo.nickName) {
      wx.showToast({ title: '请先选择头像或填写昵称', icon: 'none' });
      return;
    }
    if (!userInfo.nickName) {
      userInfo.nickName = '支付宝用户';
    }
    var that = this;
    that.setData({ saving: true });
    authService.loginWithProfile(userInfo).then(function(auth) {
      var app = typeof getApp === 'function' ? getApp() : null;
      if (app && app.globalData) {
        app.globalData.userInfo = auth.userInfo || userInfo;
      }
      that.setData({ saving: false });
      wx.showToast({ title: '授权成功', icon: 'success' });
      setTimeout(function() {
        wx.navigateBack({ delta: 1 });
      }, 250);
    }).catch(function(err) {
      that.setData({ saving: false });
      wx.showToast({ title: err && err.message ? err.message : '授权失败', icon: 'none' });
    });
  }
});
