import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

# Replace HTML progress containers
pattern_html = r'<div id="([a-z]+)-progress-container"\s*style="display: none; margin-top: 20px;">\s*<div.*?>\s*<span id="\1-progress-text".*?</span>\s*<span id="\1-progress-detail".*?</span>\s*</div>\s*<div.*?>\s*<div id="\1-progress-bar".*?background:\s*([^;]+);.*?></div>\s*</div>\s*</div>'
def repl_html(m):
    id_prefix = m.group(1)
    color = m.group(2).strip()
    return f'<forensys-progress id="{id_prefix}-progress-container" style="display: none; margin-top: 20px;" color="{color}"></forensys-progress>'

new_content = re.sub(pattern_html, repl_html, content, flags=re.DOTALL)

with open('web_app/templates/index.html', 'w') as f:
    f.write(new_content)

print(f"Replaced {len(re.findall(pattern_html, content, flags=re.DOTALL))} HTML occurrences.")
