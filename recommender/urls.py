from django.urls import path
from . import views

urlpatterns = [
    path('', views.recommend, name='recommend'),
    path('chat/', views.chat, name='recommend_chat'),
]
