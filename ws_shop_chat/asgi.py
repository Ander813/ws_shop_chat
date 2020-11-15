import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddleware
from django.core.asgi import get_asgi_application
import chat.routing


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ws_shop_chat.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddleware(
        URLRouter(chat.routing.websocket_urlpatterns)
    )
})

