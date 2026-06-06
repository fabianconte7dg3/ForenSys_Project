import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

# Append SW registration before the closing </body> tag
pattern = r'(</body>\s*</html>)'
replacement = r'''
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js')
      .then(registration => {
        console.log('SW registered: ', registration);
      })
      .catch(registrationError => {
        console.log('SW registration failed: ', registrationError);
      });
  });
}
</script>
\1'''

new_content = re.sub(pattern, replacement, content)

with open('web_app/templates/index.html', 'w') as f:
    f.write(new_content)
