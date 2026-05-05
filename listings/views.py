"""
Travel Buddy – new views to APPEND to the bottom of listings/views.py
Keep all existing Harbor views above these.
"""

import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.db.models import Q

from .models import Listing, Conversation, Message, Review   # adjust if your model names differ

User = get_user_model()


# ── Home ────────────────────────────────────────────────────────────────────

def home(request):
    """Landing page – show a handful of recent trip postings."""
    recent_trips = Listing.objects.order_by('-created_at')[:6]
    return render(request, 'listings/home.html', {'recent_trips': recent_trips})


# ── Browse trips ─────────────────────────────────────────────────────────────

def trip_browse(request):
    """Browse all active trip postings with optional keyword filter."""
    query = request.GET.get('q', '')
    trips = Listing.objects.order_by('-created_at')
    if query:
        trips = trips.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    return render(request, 'listings/listing_list.html', {'listings': trips, 'query': query})


# ── Trip search (GET) ─────────────────────────────────────────────────────────

def trip_search(request):
    """Simple keyword search – reuses browse logic."""
    return trip_browse(request)


# ── Map view ─────────────────────────────────────────────────────────────────

def map_view(request):
    """Map page – passes trip data as JSON for the frontend map."""
    trips = Listing.objects.values(
        'id', 'title', 'description', 'price',
        'latitude', 'longitude',         # add these fields to your model if not present
    )
    return render(request, 'listings/map.html', {
        'trips_json': json.dumps(list(trips)),
    })


# ── Create trip (AI-assisted) ─────────────────────────────────────────────────

@login_required
def create_local_ai(request):
    """Create a new trip posting (stub – wire up your form/model here)."""
    if request.method == 'POST':
        # TODO: replace with your TripForm once it exists
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', 0)
        if title:
            Listing.objects.create(
                title=title,
                description=description,
                price=price,
                user=request.user,
            )
            return redirect('trip_browse')
    return render(request, 'listings/create_listing.html')


# ── Messaging ────────────────────────────────────────────────────────────────

@login_required
def inbox_view(request):
    """Show all conversations for the logged-in user."""
    conversations = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).order_by('-updated_at')
    return render(request, 'listings/inbox.html', {'conversations': conversations})


@login_required
def conversation_view(request, conversation_id):
    """Display a single conversation thread and handle new messages."""
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
    )
    # Only participants can view
    if request.user not in (conversation.user1, conversation.user2):
        return redirect('messaging_inbox')

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                body=body,
            )
            return redirect('messaging_conversation', conversation_id=conversation_id)

    messages = conversation.messages.order_by('created_at')
    return render(request, 'listings/conversation.html', {
        'conversation': conversation,
        'messages': messages,
    })


@login_required
def start_conversation(request, user_id):
    """Start (or resume) a conversation with another user."""
    other_user = get_object_or_404(User, id=user_id)
    # Look for an existing conversation between the two users
    conversation = Conversation.objects.filter(
        Q(user1=request.user, user2=other_user) |
        Q(user1=other_user, user2=request.user)
    ).first()
    if not conversation:
        conversation = Conversation.objects.create(
            user1=request.user,
            user2=other_user,
        )
    return redirect('messaging_conversation', conversation_id=conversation.id)


# ── Profile ──────────────────────────────────────────────────────────────────

@login_required
def my_profile_view(request):
    """Show the logged-in user's profile and their trip postings."""
    my_trips = Listing.objects.filter(user=request.user).order_by('-created_at')
    received_reviews = Review.objects.filter(reviewee=request.user).order_by('-created_at')
    return render(request, 'listings/profile.html', {
        'my_trips': my_trips,
        'received_reviews': received_reviews,
    })

#
# # ── Ratings ──────────────────────────────────────────────────────────────────
#
# @login_required
# def leave_rating(request, user_id):
#     """Leave a safety/reliability rating for another user."""
#     reviewee = get_object_or_404(User, id=user_id)
#     if request.method == 'POST':
#         rating = request.POST.get('rating')
#         comment = request.POST.get('comment', '').strip()
#         if rating:
#             Review.objects.update_or_create(
#                 reviewer=request.user,
#                 reviewee=reviewee,
#                 defaults={'rating': int(rating), 'comment': comment},
#             )
#             return redirect('my_profile')
#     existing = Review.objects.filter(reviewer=request.user, reviewee=reviewee).first()
#     return render(request, 'listings/leave_rating.html', {
#         'reviewee': reviewee,
#         'existing': existing,
#     })
#

# ── Trip API (JSON) ───────────────────────────────────────────────────────────

@login_required
def trip_api_list(request):
    """Return all trips as JSON for the matching engine / map frontend."""
    trips = list(Listing.objects.values(
        'id', 'title', 'description', 'price', 'user__username',
        'latitude', 'longitude',
    ))
    return JsonResponse({'trips': trips})

