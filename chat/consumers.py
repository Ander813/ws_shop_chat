from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
import redis
from django.conf import settings
import json

from chat.models import Chats, Messages

redis_instance = redis.StrictRedis(host=settings.REDIS_HOST,
                                   port=settings.REDIS_PORT,
                                   db=0)


class CustomAsyncWebsocketConsumer(AsyncWebsocketConsumer):

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
        room_ip = data['room_name'].split(':')[-1]
        messages = await database_sync_to_async(Chats.get_messages)(room_ip)
        messages_json = {"messages": await self.messages_to_json(messages)}

        await self.send_message(messages_json)

    async def new_message(self, data):
        chat = Chats.objects.get(chat_room=data['room_name'].split(':')[-1])
        message = chat.messages.create(sender=self.scope['user'], 
                                       content=data['message'])
        content = {'room_name': data['room_name'],
                   'message': await self.message_to_json(message)}
        await self.send_chat_message(content)

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
            'sender': message.sender.username
        }

    async def send_chat_message(self, data):
        await self.channel_layer.group_send(
            data['room_name'], {
                'type': 'chat.message',
                'message': data['message'],
                'room_name': data['room_name']
            }
        )

    commands = {
        'fetch_messages': fetch_messages,
        'send_message': new_message,
    }

    async def send_message(self, message):
        await self.send(text_data=json.dumps(message))


class ChatConsumer(CustomAsyncWebsocketConsumer):

    async def get_moderators_list(self):
        encoded_moderators_list = await sync_to_async(redis_instance.lrange) \
            ('chat:moderators', 0, -1)
        return list(map(lambda x: x.decode('utf-8'),
                        encoded_moderators_list))

    async def connect(self):
        ip = str(self.scope['client'][0]) + str(self.scope['client'][1])
        self.room_name = f"chat_{ip}"
        await self.group_add(self.room_name, self.channel_name)
        self.moderators_list = await self.get_moderators_list()

        await self.accept()

        if self.moderators_list:
            for moderator in self.moderators_list:
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
        for moderator in self.moderators_list:
            await self.group_discard(self.room_name, moderator)
        await self.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        data_json = json.loads(text_data)
        message = data_json['message']

        await self.fetch_messages({'room_name': '127.0.0.1'})

        """await self.channel_layer.group_send(
            self.room_name,
            {
                "type": 'chat.message',
                "room_name": self.room_name,
                "message": message,
            }
        )"""

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event['message'],
        }))


class ModeratorChatConsumer(CustomAsyncWebsocketConsumer):
    room_group_names = []
    moderators_key = 'chat:moderators'

    async def connect(self):
        self.user = self.scope['user']
        if await database_sync_to_async(self.user.groups.filter)(name="moderator"):
            for group in redis_instance.scan_iter("asgi:group:*"):
                group = group.decode('utf-8').split(':')[-1]
                await self.group_add(group, self.channel_name)
                self.room_group_names.append(group)

            await self.accept()

            await sync_to_async(redis_instance.lpush) \
                (self.moderators_key, self.channel_name)
        else:
            await self.close(code=403)

    async def disconnect(self, close_code):
        for group in self.room_group_names:
            await self.group_discard(group, self.channel_name)
        await sync_to_async(redis_instance.lrem) \
            (self.moderators_key, 0, self.channel_name)

    async def receive(self, text_data):
        data_json = json.loads(text_data)
        message = data_json['message']

        await self.fetch_messages({'room_name': '127.0.0.1'})

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "room_name": event['room_name'],
            "message": event['message'],
        }))
