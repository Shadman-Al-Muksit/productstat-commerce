import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, ".next/standalone");
const server = resolve(output, "server.js");
if (!existsSync(server)) {
  console.error("Missing production build. Run npm run build first.");
  process.exit(1);
}
mkdirSync(resolve(output, ".next"), { recursive: true });
cpSync(resolve(root, "public"), resolve(output, "public"), { recursive: true });
cpSync(resolve(root, ".next/static"), resolve(output, ".next/static"), {
  recursive: true,
});
const child = spawn(process.execPath, [server], {
  cwd: output,
  env: {
    ...process.env,
    HOSTNAME: process.env.PRODUCTSTAT_BIND || "127.0.0.1",
    PORT: process.env.PORT || "3000",
  },
  stdio: "inherit",
});
process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
child.on("error", (error) => {
  console.error(error.message);
  process.exit(1);
});
child.on("exit", (code) => process.exit(code ?? 0));
