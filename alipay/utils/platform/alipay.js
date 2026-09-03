function hasMy() {
  return typeof my !== 'undefined' && my;
}

function callMy(name, options, fallback) {
  if (hasMy() && typeof my[name] === 'function') return my[name](options || {});
  if (typeof fallback === 'function') return fallback(options || {});
  if (options && typeof options.fail === 'function') options.fail({ errMsg: name + ':fail unavailable' });
  return null;
}

module.exports = {
  isAlipay: true,
  hasMy: hasMy,
  callMy: callMy
};
