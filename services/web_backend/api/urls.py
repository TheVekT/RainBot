from django.urls import path
from . import views

urlpatterns = [
    path('internal/rain-event/', views.internal_rain_event, name='internal_rain_event'),
    path('rain/stream/', views.rain_stream, name='rain_stream'),
]