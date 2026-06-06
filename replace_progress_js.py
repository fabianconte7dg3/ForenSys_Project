import re

with open('web_app/templates/index.html', 'r') as f:
    content = f.read()

pattern_js = r'''const p(\w+)Container = document.getElementById\('([a-z]+)-progress-container'\);\s*if \(p\1Container\) \{\s*p\1Container\.style\.display = 'block';\s*document\.getElementById\('\2-progress-bar'\)\.style\.width = '0%';\s*(?:document\.getElementById\('\2-progress-bar'\)\.style\.background = [^;]+;\s*)?document\.getElementById\('\2-progress-text'\)\.textContent = 'Progreso: 0%';\s*document\.getElementById\('\2-progress-detail'\)\.textContent = ([^;]+);\s*\}'''

def repl_js(m):
    var_name = m.group(1)
    prefix = m.group(2)
    detail_str = m.group(3)
    # Define colors based on prefix
    colors = {
        'wiping': 'var(--accent-red)',
        'usb': '#a855f7',
        'ram': 'var(--accent-cyan)',
        'mobile': 'var(--accent-yellow)',
        'cloud': '#94a3b8',
        'timeline': 'var(--accent-blue)',
        'ia': 'var(--accent-green)',
        'report': 'var(--accent-purple)'
    }
    color = colors.get(prefix, 'var(--accent-cyan)')
    
    return f'''const p{var_name}Container = document.getElementById('{prefix}-progress-container');
        if (p{var_name}Container) {{
            p{var_name}Container.style.display = 'block';
            p{var_name}Container.setAttribute('value', '0');
            p{var_name}Container.setAttribute('color', '{color}');
            p{var_name}Container.detail = {detail_str};
        }}'''

new_content = re.sub(pattern_js, repl_js, content, flags=re.DOTALL)

with open('web_app/templates/index.html', 'w') as f:
    f.write(new_content)

print(f"Replaced {len(re.findall(pattern_js, content, flags=re.DOTALL))} JS occurrences.")
