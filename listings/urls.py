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
    path('api/ai/generate-trip/', views.ai_generate_trip, name='api_ai_generate_trip'),
    path('api/ai/save-trip/', views.save_ai_trip, name='api_ai_save_trip'),
    path('api/trips/<int:pk>/matches/', views.trip_match_api, name='api_trip_matches'),

    #API for assignment Member 3: The Data & API Developer
    path('api/harbor-stats/', views.harbor_stats),
    path('dashboard/', views.harbor_dashboard),
]
