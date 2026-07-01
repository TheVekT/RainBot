from django.urls import path
from .views import user_list_view, user_detail_view, chronology_view, custom_404_view

app_name = 'public_web'

urlpatterns = [
    path('users/', user_list_view, name='user_list'),
    path('users/<int:account_id>/', user_detail_view, name='user_detail'),
    path('chronology/', chronology_view, name='chronology'),
    path('404/', custom_404_view, name='test_404'),
]