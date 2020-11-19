from json.decoder import JSONDecodeError

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
import redis
from django.conf import settings
import json
import time


from chat.models import Chats, EmailMessages

redis_instance = redis.StrictRedis(host=settings.REDIS_HOST,
                                   port=settings.REDIS_PORT,
                                   db=0)


class BaseChatConsumer(AsyncWebsocketConsumer):
    moderators_key = 'chat:moderators'

    async def get_moderators_list(self):
        encoded_moderators_list = await sync_to_async(redis_instance.lrange) \
            (self.moderators_key, 0, -1)
        return list(map(lambda x: x.decode('utf-8'),
                        encoded_moderators_list))

    async def group_add(self, room_name, channel_name):
        await self.channel_layer.group_add(
            room_name,
            channel_name
        )

    async def group_discard(self, room_name, channel_name):
        await self.channel_layer.group_discard(
            room_name,
            channel_name
        )

    async def fetch_messages(self, data):
        room_ip = data['room_name'].split('_')[-1]
        messages = await database_sync_to_async(Chats.get_messages)(room_ip)
        messages_json = {"messages": await self.messages_to_json(messages)}

        await self.send_message(messages_json)

    async def new_message(self, data):
        if await self.get_moderators_list():
            message = await self.create_new_message_db(data)

            content = {'room_name': data['room_name'],
                       'message': await self.message_to_json(message)}
            await self.send_chat_message(content)
        else:
            await self.new_email_message(data)

    async def create_new_message_db(self, data):
        chat, _ = await database_sync_to_async(
            Chats.objects.get_or_create)(chat_room=data['room_name'].split('_')[-1])
        if self.scope['user'].is_anonymous:
            message = await database_sync_to_async(
                chat.messages.create)(sender=None,
                                      content=data['message'])
        else:
            message = await database_sync_to_async(
                chat.messages.create)(sender=self.scope['user'],
                                      content=data['message'])
        return message

    async def new_email_message(self, data):
        try:
            message = await database_sync_to_async(
                EmailMessages.objects.create)(email=data['email'],
                                             content=data['message'])
            await self.send_message({
                "message": {
                    "sent": time.time(),
                    "sender": "System",
                    "content": "Thank you for your message, we will reply as soon as we can"
                }
            })
        except KeyError:
            await self.send_message({'error': 'no email'})

    async def messages_to_json(self, messages):
        messages_list = []
        for message in messages:
            messages_list.append(
                await self.message_to_json(message)
            )
        return messages_list

    async def message_to_json(self, message):
        return {
            'content': message.content,
            'sent': str(message.sent),
            'sender': message.sender.username if not self.scope['user'].is_anonymous else None
        }

    async def send_chat_message(self, data):
        await self.channel_layer.group_send(
            data['room_name'], {
                'type': 'chat.message',
                'message': data['message'],
                'room_name': data['room_name']
            }
        )

    async def send_message(self, message):
        await self.send(text_data=json.dumps(message))

    commands = {
        'fetch_messages': fetch_messages,
        'new_message': new_message,
        'email_message': new_email_message,
    }


class ChatConsumer(BaseChatConsumer):

    async def connect(self):
        ip = self.scope['client'][0]
        self.room_name = f"chat_{ip}"
        await self.group_add(self.room_name, self.channel_name)
        moderators_list = await self.get_moderators_list()

        await self.accept()

        if moderators_list:
            for moderator in moderators_list:
                await self.group_add(self.room_name, moderator)
            await self.send(text_data=json.dumps({
                "message": "Hi, any questions?"
            }))

        else:
            await self.send(text_data=json.dumps({
                "status": "no_moderators",
                "message": "There is no moderators at the moment. "
                           "We will get an email and reply you as soon as we can."
            }))

    async def disconnect(self, close_code):
        for moderator in await self.get_moderators_list():
            await self.group_discard(self.room_name, moderator)
        await self.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data_json = json.loads(text_data)
        except JSONDecodeError:
            data_json = None

        try:
            command_func = self.commands[data_json['command']]
        except KeyError:
            command_func = None

        if command_func:
            data_json['room_name'] = self.room_name
            await command_func(self, data_json)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event['message'],
        }))


class ModeratorChatConsumer(BaseChatConsumer):

    async def connect(self):
        self.user = self.scope['user']
        if await database_sync_to_async(self.user.groups.filter)(name="moderator"):
            for group in await sync_to_async(redis_instance.scan_iter)("asgi:group:*"):
                group = group.decode('utf-8').split(':')[-1]
                await self.group_add(group, self.channel_name)

            await self.accept()

            await sync_to_async(redis_instance.lpush) \
                (self.moderators_key, self.channel_name)
        else:
            await self.close(code=403)

    async def disconnect(self, close_code):
        for group in await sync_to_async(redis_instance.scan_iter)("asgi:group:*"):
            group = group.decode('utf-8').split(':')[-1]
            await self.group_discard(group, self.channel_name)
        await sync_to_async(redis_instance.lrem) \
            (self.moderators_key, 0, self.channel_name)

    async def receive(self, text_data):
        try:
            data_json = json.loads(text_data)
        except JSONDecodeError:
            data_json = None

        try:
            command_func = self.commands[data_json['command']]
        except KeyError:
            command_func = None

        if command_func:
            await command_func(self, data_json)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "room_name": event['room_name'],
            "message": event['message'],
        }))
