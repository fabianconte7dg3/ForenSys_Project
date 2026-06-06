import subprocess
import os

cmd = "sudo python3 /home/ciber-admin/ForenSys_Project/scripts/../dummy_wiping.py"
env = os.environ.copy()
env['PYTHONUNBUFFERED'] = '1'

proc = subprocess.Popen(
    cmd, shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    env=env,
    start_new_session=True,
)

print("Reading...")
for line in iter(proc.stdout.readline, ''):
    print("GOT LINE:", repr(line))
