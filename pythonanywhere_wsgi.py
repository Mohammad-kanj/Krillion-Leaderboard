# Paste this into PythonAnywhere's WSGI configuration file.
# (Web tab -> Code section -> click the WSGI file link, delete what's there,
#  paste this, and replace YOURUSERNAME with your PythonAnywhere username.)
import sys

path = '/home/YOURUSERNAME/krillion-leaderboard'
if path not in sys.path:
    sys.path.insert(0, path)

from wsgi import application
