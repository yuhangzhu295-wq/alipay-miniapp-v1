var apiConfig = require('./apiConfig.js');

var AUTH_KEY = 'userAuth';
var USER_INFO_KEY = 'userInfo';
var TOKEN_KEY = 'token';
var CLIENT_ID_KEY = 'userClientId';

function safeGet(key, fallback) {
  try {
    var value = wx.getStorageSync(key);
    return value || fallback;
  } catch (e) {
    return fallback;
  }
}

function safeSet(key, value) {
  try {
    wx.setStorageSync(key, value);
  } catch (e) {}
}

function safeRemove(key) {
  try {
    wx.removeStorageSync(key);
  } catch (e) {}
}

function getClientUserId() {
  var clientId = safeGet(CLIENT_ID_KEY, '');
  if (!clientId) {
    clientId = 'client_' + Date.now() + '_' + Math.random().toString(16).slice(2);
    safeSet(CLIENT_ID_KEY, clientId);
  }
  return clientId;
}

function getAuth() {
  var auth = safeGet(AUTH_KEY, null);
  if (auth && auth.token && auth.userId) {
    return auth;
  }
  return null;
}

function getUserInfo() {
  var auth = getAuth();
  if (auth && auth.userInfo) return auth.userInfo;
  return safeGet(USER_INFO_KEY, null);
}

function isLoggedIn() {
  return !!getAuth();
}

function getUserId() {
  var auth = getAuth();
  return auth ? auth.userId : '';
}

function getPhotoStorageKey() {
  var userId = getUserId();
  return userId ? ('myPhotos:' + userId) : 'myPhotos:guest';
}

function getAuthHeader() {
  var auth = getAuth();
  if (!auth || !auth.token) return {};
  return {
    Authorization: 'Bearer ' + auth.token,
    'X-User-Token': auth.token
  };
}

function loginWithProfile(userInfo) {
  userInfo = userInfo || {};
  return new Promise(function(resolve, reject) {
    var requestLogin = function(code) {
      wx.request({
        url: apiConfig.API_BASE_URL + '/api/auth/login',
        method: 'POST',
        header: { 'content-type': 'application/json' },
        data: {
          code: code || '',
          clientUserId: getClientUserId(),
          userInfo: {
            nickName: userInfo.nickName || '微信用户',
            avatarUrl: userInfo.avatarUrl || ''
          }
        },
        timeout: 15000,
        success: function(res) {
          var data = res.data || {};
          if (res.statusCode === 200 && data.success && data.token && data.userId) {
            var auth = {
              userId: data.userId,
              token: data.token,
              provider: data.provider || '',
              openidBound: !!data.openidBound,
              userInfo: data.userInfo || userInfo,
              loginAt: Date.now()
            };
            safeSet(AUTH_KEY, auth);
            safeSet(TOKEN_KEY, data.token);
            safeSet(USER_INFO_KEY, auth.userInfo);
            resolve(auth);
          } else {
            reject(new Error(data.message || '登录失败，请稍后重试'));
          }
        },
        fail: function(err) {
          reject(new Error((err && err.errMsg) || '登录服务暂不可用'));
        }
      });
    };

    if (typeof wx.login === 'function') {
      wx.login({
        success: function(res) {
          requestLogin(res && res.code ? res.code : '');
        },
        fail: function() {
          requestLogin('');
        }
      });
    } else {
      requestLogin('');
    }
  });
}

function requireLogin(message) {
  return new Promise(function(resolve, reject) {
    var auth = getAuth();
    if (auth) {
      resolve(auth);
      return;
    }
    wx.showModal({
      title: '需要登录',
      content: message || '请先授权登录后查看我的电子照。',
      confirmText: '去登录',
      success: function(res) {
        if (res.confirm) {
          wx.navigateTo({ url: '/pages/login/login' });
        }
        reject(new Error('AUTH_REQUIRED'));
      }
    });
  });
}

function logout() {
  safeRemove(AUTH_KEY);
  safeRemove(TOKEN_KEY);
  safeRemove(USER_INFO_KEY);
}

module.exports = {
  getClientUserId: getClientUserId,
  getAuth: getAuth,
  getUserInfo: getUserInfo,
  isLoggedIn: isLoggedIn,
  getUserId: getUserId,
  getAuthHeader: getAuthHeader,
  getPhotoStorageKey: getPhotoStorageKey,
  loginWithProfile: loginWithProfile,
  requireLogin: requireLogin,
  logout: logout
};
