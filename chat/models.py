from django.contrib.auth.models import User
from django.db import models


class Chats(models.Model):
    chat_room = models.GenericIPAddressField()

    @staticmethod
    def get_messages(room_ip):
        try:
            return Chats.objects.get(chat_room=room_ip).messages.order_by('-sent').all()
        except models.DoesNotExist:
            return None

    def __str__(self):
        return f"Chat_{self.chat_room}"

    class Meta:
        verbose_name = 'Chat'
        verbose_name_plural = 'Chats'


class Messages(models.Model):
    content = models.TextField()
    sent = models.DateTimeField(auto_now_add=True)
    chat = models.ForeignKey(Chats, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='user_massages', on_delete=models.CASCADE, null=True)
