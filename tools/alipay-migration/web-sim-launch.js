const path = require('path');

const projectRoot = path.resolve(__dirname, '..', '..');

(async () => {
  const mini = require(require.resolve('minidev', { paths: [projectRoot] }));
  const build = await mini.minidev.dev({
    project: path.join(projectRoot, 'alipay'),
    port: 8811
  });
  console.log('BUILD_OK');
  const prevLauncher = global.__prevLauncher;
  void prevLauncher;
  const launcher = await mini.minidev.devWebSimulator({
    project: path.join(projectRoot, 'alipay'),
    clientType: 'alipay',
    port: 9021
  }, build);
  console.log('SIMULATOR_URL=' + launcher.separated.simulator.replace('___uuid___', 'websim-' + Date.now()));
  console.log('DEVTOOL_URL=' + launcher.separated.devtool.replace('___uuid___', 'websim-' + Date.now()));
  console.log('READY');
  setInterval(() => {}, 1 << 30);
})().catch((e) => {
  console.error('ERR ' + (e && (e.stack || e.message)));
  process.exit(1);
});
