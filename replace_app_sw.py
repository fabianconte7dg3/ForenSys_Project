import re

with open('web_app/app.py', 'r') as f:
    content = f.read()

# Add a route for /sw.js
if '@app.route("/sw.js")' not in content:
    pattern = r"(@app\.route\('/', methods=\['GET'\]\)\ndef index\(\):\n    return render_template\('index\.html'\))"
    replacement = r'''\1

@app.route('/sw.js', methods=['GET'])
def sw():
    response = send_from_directory('static', 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response'''
    
    new_content = re.sub(pattern, replacement, content)
    with open('web_app/app.py', 'w') as f:
        f.write(new_content)
