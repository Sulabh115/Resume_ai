from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.
# jpobs/views.py

def index(request):
    return HttpResponse("Hello from Jobs App")