from django.urls import path
from . import views

urlpatterns = [

    # ─── Travel Buddy core routes ────────────────────────────────────────────
    path('', views.home, name='home'),
    path('trips/', views.trip_browse, name='trip_browse'),
    path('browse/', views.trip_browse, name='listing_list'),
    path('trips/map/', views.map_view, name='trip_map'),
    path('trips/create/', views.create_local_ai, name='trip_create'),
    path('ai/create/', views.create_local_ai, name='create_local_ai'),
    path('trips/save/', views.save_trip_from_ai, name='save_listing'),
    path('trips/search/', views.trip_search, name='trip_search'),

    # Messaging
    path('messages/', views.inbox_view, name='messaging_inbox'),
    path('messages/<int:conversation_id>/', views.conversation_view, name='messaging_conversation'),
    path('messages/start/<int:user_id>/', views.start_conversation, name='start_conversation'),

    # Profile
    path('profile/', views.my_profile_view, name='my_profile'),

    # API
    path('api/trips/', views.trip_api_list, name='api_trips'),
    path('api/ai/generate/', views.travel_ai_generate, name='api_ai_generate'),
    path('api/trips/<int:plan_id>/matches/', views.trip_match_api, name='api_trip_matches'),
]
