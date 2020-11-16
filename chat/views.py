from django.shortcuts import render
from django.http import HttpResponse


def index(request):
    return HttpResponse("just test")

def moderator_chat(request):
    return render(request, 'chat/moderator_chat.html')