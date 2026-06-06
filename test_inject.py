import queue
import sys
import os

# We can't inject into a running process's memory easily.
# But we CAN tail the actual queue if we were in the same process.
# Since we are not, we can't push to log_queue from outside.
