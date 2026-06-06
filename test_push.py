import requests
import json

# Can we trigger a log in app.py?
# We can't directly call push_log, but we can call an API that logs something.
requests.post('http://localhost:5000/api/kill_command')
