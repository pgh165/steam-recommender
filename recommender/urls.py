from django.urls import path
from . import views

urlpatterns = [
    path('', views.recommend, name='recommend'),
    path('run/', views.recommend_run, name='recommend_run'),
    path('chat/', views.chat, name='recommend_chat'),
]
