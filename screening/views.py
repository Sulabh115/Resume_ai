from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.
# screening/views.py

def index(request):
    return HttpResponse("Hello from Screening App")