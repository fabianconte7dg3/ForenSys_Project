const fs = require('fs');
const html = fs.readFileSync('web_app/templates/index.html', 'utf8');
const scriptRegex = /<script>([\s\S]*?)<\/script>/g;
let match;
let count = 1;
while ((match = scriptRegex.exec(html)) !== null) {
  const code = match[1];
  try {
    new Function(code);
    console.log(`Script ${count} parsed successfully.`);
  } catch (e) {
    console.error(`Error in script ${count}:`, e.message);
    const lines = code.split('\n');
    const errLineMatch = e.stack.match(/<anonymous>:(\d+)/);
    if (errLineMatch) {
      const lineNum = parseInt(errLineMatch[1]);
      console.log('Error near:', lines[lineNum - 2]);
      console.log('Error line:', lines[lineNum - 1]);
      console.log('Error after:', lines[lineNum]);
    }
  }
  count++;
}
