import requests, json, time, sys

url = "http://localhost:5000/api/logs/stream"
r = requests.get(url, stream=True)
for line in r.iter_lines():
    if line:
        decoded = line.decode('utf-8')
        if decoded.startswith('data: '):
            data = json.loads(decoded[6:])
            print(data['msg'], flush=True)
            if data.get('level') in ['success', 'error']:
                sys.exit(0)
