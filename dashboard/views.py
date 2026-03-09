from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.
# Dashboard/views.py

def index(request):
    return HttpResponse("Hello from Dashboard App")