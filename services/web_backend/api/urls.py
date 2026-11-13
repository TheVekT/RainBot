from django.urls import path
from . import views
from .health import api_health

urlpatterns = [
    path('health/', api_health, name='api_health'),
    path('internal/rain-event/', views.internal_rain_event, name='internal_rain_event'),
    path('rain/stream/', views.rain_stream, name='rain_stream'),
]
