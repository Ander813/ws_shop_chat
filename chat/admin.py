from django.contrib import admin
from .models import Chats, Messages


class MessagesInline(admin.StackedInline):
    model = Messages


@admin.register(Chats)
class ChatAdmin(admin.ModelAdmin):
    list_display = ['chat_room']
    inlines = [MessagesInline]
