from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
import redis
from django.conf import settings
import json

redis_instance = redis.StrictRedis(host=settings.REDIS_HOST,
                                   port=settings.REDIS_PORT,
                                   db=0)
redis_instance.incr("chat:chat_room")


class ChatConsumer(AsyncWebsocketConsumer):
    chat_room = "chat:chat_room"
    room_number = redis_instance.get(chat_room).decode('utf-8')

    async def connect(self):
        self.room_group_name = f"chat_{self.room_number}"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        self.room_number = redis_instance.incr(self.chat_room)
        await self.send(text_data=json.dumps({
            "message": "Hi, any questions?"
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data_json = json.loads(text_data)
        message = data_json['message']

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": 'chat.message',
                "room_id": self.room_number,
                "message": message,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "room_id": event['room_id'],
            "message": event['message'],
        }))


class ModeratorChatConsumer(AsyncWebsocketConsumer):
    room_group_names = []

    async def connect(self):
        self.user = self.scope['user']
        if await sync_to_async(self.user.groups.filter)(name="moderator"):
            for group in redis_instance.scan_iter("asgi:group:*"):
                group = group.decode('utf-8').split(':')[-1]
                await self.channel_layer.group_add(
                    group,
                    self.channel_name
                )
                self.room_group_names.append(group)

            await self.accept()
        else:
            await self.close(code=403)

    async def disconnect(self, close_code):
        for group in self.room_group_names:
            await self.channel_layer.group_discard(
                group,
                self.channel_name
            )

    async def receive(self, text_data):
        data_json = json.loads(text_data)
        message = data_json['message']

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": 'chat.message',
                "room_id": self.room_number,
                "message": message,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "room_id": event['room_id'],
            "message": event['message'],
        }))

