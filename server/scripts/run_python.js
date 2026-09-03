const { spawnSync } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const PYTHON = process.env.PYTHON || "C:\\Users\\zyu33\\AppData\\Local\\Programs\\Python\\Python313\\python.exe";

const argv = process.argv.slice(2);
if (!argv.length) {
  console.error("Usage: node server/scripts/run_python.js <script.py> [...args]");
  process.exit(2);
}

const [script, ...rest] = argv;
const scriptPath = path.isAbsolute(script) ? script : path.resolve(ROOT, script);
const result = spawnSync(PYTHON, [scriptPath, ...rest], {
  cwd: ROOT,
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(result.error.message || String(result.error));
  process.exit(1);
}

process.exit(result.status == null ? 1 : result.status);
