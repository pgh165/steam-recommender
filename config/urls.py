from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('library/', include('library.urls')),
    path('deals/', include('deals.urls')),
    path('recommend/', include('recommender.urls')),
]
