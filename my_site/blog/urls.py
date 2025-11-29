from . import views
from django.urls import path


urlpatterns = [
    path('', views.index, name='index'),
    path('posts', views.posts, name='posts_list'),
]