from django.urls import path
from . import views

urlpatterns = [
    path('', views.deals_list, name='deals'),
    path('game/<int:app_id>/', views.game_detail, name='game_detail'),
    path('compare/', views.price_compare, name='price_compare'),
    path('search/', views.search_games, name='search_games'),
]
