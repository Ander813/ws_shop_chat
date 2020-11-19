from django.contrib import admin
from .models import Chats, Messages, EmailMessages


class MessagesInline(admin.StackedInline):
    model = Messages


@admin.register(Chats)
class ChatAdmin(admin.ModelAdmin):
    list_display = ['chat_room']
    inlines = [MessagesInline]


@admin.register(EmailMessages)
class EmailMessageAdmin(admin.ModelAdmin):
    actions = ['mark_as_replied']
    list_display = ['email', 'replied', 'sent']
    list_editable = ['replied']
    readonly_fields = ['sent']

    def mark_as_replied(self, request, queryset):
        queryset.update(replied=True)
    mark_as_replied.short_description = "Mark replied"
