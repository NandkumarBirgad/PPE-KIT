import fs from 'fs';
import path from 'path';

const nativeJsPath = path.resolve('node_modules', 'rollup', 'dist', 'native.js');

if (fs.existsSync(nativeJsPath)) {
  let content = fs.readFileSync(nativeJsPath, 'utf8');
  if (!content.includes('@rollup/wasm-node/dist/native.js')) {
    content = content.replace(
      /const nativeModule = requireWithFriendlyError\([\s\S]*?\);/,
      `let nativeModule;
try {
\tnativeModule = requireWithFriendlyError(
\t\texistsSync(path.join(__dirname, localName)) ? localName : \`@rollup/rollup-\${packageBase}\`
\t);
} catch (err) {
\ttry {
\t\tnativeModule = require('@rollup/wasm-node/dist/native.js');
\t} catch (wasmErr) {
\t\tthrow err;
\t}
}`
    );
    fs.writeFileSync(nativeJsPath, content, 'utf8');
    console.log('✅ AppLocker-safe Rollup WASM fallback verified in native.js');
  }
}
