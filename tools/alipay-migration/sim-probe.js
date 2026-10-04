const path = require('path');

const project = path.resolve(__dirname, '..', '..', 'alipay');

(async () => {
  const mini = require(require.resolve('minidev', { paths: [path.resolve(__dirname, '..', '..')] }));
  const sim = await mini.miniProject.remoteController.getSimulator({ project });
  console.log('CONNECTED');
  const page = await sim.currentPage();
  console.log('PAGE=' + JSON.stringify(page));
  await sim.disconnect ? null : null;
  process.exit(0);
})().catch((e) => {
  console.error('ERR ' + (e && e.message));
  process.exit(1);
});
