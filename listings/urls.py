from django.urls import path
from . import views

urlpatterns = [

    # ─── Travel Buddy core routes ────────────────────────────────────────────
    path('', views.home, name='home'),
    path('trips/', views.trip_browse, name='trip_browse'),
    path('trips/<int:pk>/', views.trip_detail, name='listing_detail'),
    path('trips/map/', views.map_view, name='trip_map'),
    path('trips/create/', views.create_local_ai, name='trip_create'),
    path('trips/search/', views.trip_search, name='trip_search'),

    # Messaging
    path('messages/', views.inbox_view, name='messaging_inbox'),
    path('messages/<int:conversation_id>/', views.conversation_view, name='messaging_conversation'),
    path('messages/start/<int:user_id>/', views.start_conversation, name='start_conversation'),

    # Profile
    path('profile/', views.my_profile_view, name='my_profile'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),

    # API
    path('api/trips/', views.trip_api_list, name='api_trips'),
]
