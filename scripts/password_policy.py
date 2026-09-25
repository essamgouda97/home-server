"""Shared enrollment policy. Never return/log estimator output (it contains the password)."""
from pathlib import Path
import re
import sys
import threading

sys.path.insert(0, str(Path.home()/'.local/share/home-server/people-python/4.5.0'))
from zxcvbn import zxcvbn

_lock = threading.Lock()

def validate_password(password, username='', name=''):
    if not isinstance(password, str) or not 16 <= len(password) <= 72 or any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise ValueError('Use a password of 16–72 characters without control characters.')
    # Bound estimator work; personalized dictionary matching stays local.
    words = re.findall(r'\w+', name)
    inputs = [username, name, ''.join(words), ''.join(reversed(words)), 'workspace', 'home-server', 'egouda'] + words
    with _lock:
        score = zxcvbn(password, user_inputs=inputs)['score']
    if score < 4:
        raise ValueError('This password is too predictable. Use a password manager to generate a unique password, or use several unrelated words. Avoid names, repeated patterns and common phrases.')
