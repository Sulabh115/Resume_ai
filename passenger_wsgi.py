import os
import sys

# Set the path to your Django project root (where manage.py is)
# We assume this file is in the same directory as manage.py
sys.path.insert(0, os.path.dirname(__file__))

# Tell Django where your settings module is
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'resume_ai.settings')

# Import the WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
