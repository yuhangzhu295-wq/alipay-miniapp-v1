// ====== 个人中心 ======
var authService = require('../../utils/authService.js');

Page({
  data: {
    userInfo: null,
    hasLogin: false,
    greetingText: '未登录，点我登录哦！',
    welcomeText: '登录后电子照仅对当前账号可见'
  },

  onShow() {
    this.refreshUserInfo();
  },

  refreshUserInfo() {
    var app = typeof getApp === 'function' ? getApp() : null;
    var auth = authService.getAuth();
    var storedUser = auth ? (auth.userInfo || authService.getUserInfo()) : null;
    this.setData({
      userInfo: storedUser || null,
      hasLogin: !!auth,
      greetingText: auth ? ('Hi，' + ((storedUser && storedUser.nickName) || '微信用户')) : '未登录，点我登录哦！',
      welcomeText: auth ? '欢迎使用证件照生成器小程序' : '登录后电子照仅对当前账号可见'
    });
    if (app && app.globalData) {
      app.globalData.userInfo = storedUser || null;
    }
  },

  handleUserCardTap() {
    this.refreshUserInfo();
    if (this.data.hasLogin) return;
    wx.navigateTo({ url: '/pages/login/login' });
  },

  goOrders() {
    wx.navigateTo({ url: '/pages/photos/photos' });
  },

  goFAQ() {
    wx.showModal({
      title: '常见问题',
      content: '1. 如何更换底色？\n进入小工具→证件照更换底色\n2. 保存后照片在哪？\n在电子照列表或系统相册\n3. 最多保存多久？\n本应用不提供照片永久存储功能，后端处理图片将在24小时后自动删除，请及时保存到本地。',
      showCancel: false
    });
  },

  goGuide() {
    wx.showModal({
      title: '拍摄攻略',
      content: '1. 正面面对光源\n2. 背景简洁干净\n3. 头部居中\n4. 免冠正面照',
      showCancel: false
    });
  },

  contactService() {
    wx.showModal({
      title: '联系客服',
      content: '如有问题，请通过小程序反馈留言',
      showCancel: false
    });
  },

  addToMiniProgram() {
    wx.showModal({
      title: '添加到我的小程序',
      content: '请点击右上角"..."菜单，选择"添加到我的小程序"即可',
      showCancel: false
    });
  },

  onShareAppMessage() {
    return {
      title: '证件照与图片工具',
      path: '/pages/index/index'
    };
  }
});
