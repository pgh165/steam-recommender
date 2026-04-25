from django.urls import path
from . import views

urlpatterns = [
    path('', views.library, name='library'),
    path('sync/', views.sync_library, name='sync_library'),
]
