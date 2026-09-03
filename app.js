// ====== 全局 App ======
var authService = require('./utils/authService.js');
var apiConfig = require('./utils/apiConfig.js');

App({
  onLaunch() {
    var apiRuntimeInfo = apiConfig.getApiRuntimeInfo ? apiConfig.getApiRuntimeInfo() : {};
    console.log('[api-config] startup', {
      envVersion: apiRuntimeInfo.envVersion || 'unknown',
      storedApiTarget: apiRuntimeInfo.storedApiTarget || '',
      actualApiBaseUrl: apiRuntimeInfo.actualApiBaseUrl || apiConfig.API_BASE_URL
    });
    // 检查登录状态
    const myPhotos = authService.isLoggedIn() ? (wx.getStorageSync(authService.getPhotoStorageKey()) || []) : []
    this.globalData.photoCount = myPhotos.length
  },

  globalData: {
    userInfo: null,
    photoCount: 0,
    specs: {
      yicun:        { name: '一寸',   size: '25×35mm',  px: '295×413px',  dpi: 300 },
      ercun:        { name: '二寸',   size: '35×49mm',  px: '413×579px',  dpi: 300 },
      dayicun:      { name: '大一寸', size: '33×48mm',  px: '390×567px',  dpi: 300 },
      xiaoyicun:    { name: '小一寸', size: '22×32mm',  px: '260×378px',  dpi: 300 },
      xiaoercun:    { name: '小二寸', size: '35×45mm',  px: '413×531px',  dpi: 300 },
      idcard:       { name: '身份证',  size: '26×32mm',  px: '358×441px',  dpi: 350 },
      passport:     { name: '护照',    size: '33×48mm',  px: '390×567px',  dpi: 300 },
      visa_us:      { name: '美国签证', size: '51×51mm',  px: '600×600px',  dpi: 300 },
      visa_japan:   { name: '日本签证', size: '45×45mm',  px: '531×531px',  dpi: 300 },
      shenggen:     { name: '申根签证', size: '35×45mm',  px: '413×531px',  dpi: 300 },
      driver:       { name: '驾驶证',  size: '22×32mm',  px: '260×378px',  dpi: 300 },
      ciza:         { name: '一寸(磁卡)', size: '25×35mm', px: '295×413px', dpi: 300 }
    },
    colors: [
      { id: 'blue',      name: '蓝色',   hex: '#1a73e8' },
      { id: 'white',     name: '白色',   hex: '#ffffff' },
      { id: 'red',       name: '红色',   hex: '#e53935' },
      { id: 'lightblue', name: '浅蓝色', hex: '#81d4fa' },
      { id: 'gray',      name: '灰色',   hex: '#9e9e9e' }
    ]
  }
})
