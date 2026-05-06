"""
Travel Buddy – new views to APPEND to the bottom of listings/views.py
Keep all existing Harbor views above these.
"""

import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ai import calculate_match_score, explain_buddy_match, generate_trip_bundle
from .models import Listing, Conversation, Message, Review, Student, Ship  # adjust if your model names differ
from .forms import ListingForm


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


def trip_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    related_matches = []
    if listing.destination and listing.departure_date:
        related_matches = _find_candidate_matches(listing)[:3]
    return render(request, 'listings/listing_detail.html', {'listing': listing, 'related_matches': related_matches})


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
    """Create a new trip posting and support AI-assisted draft generation."""
    student, _ = Student.objects.get_or_create(
        university_email=request.user.email,
        defaults={
            'first_name': request.user.first_name or request.user.username or 'Travel',
            'last_name': request.user.last_name or 'Buddy',
            'is_verified': True,
        },
    )

    if request.method == 'POST':
        form = ListingForm(request.POST)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.seller = student
            listing.save()
            return redirect('trip_browse')
    else:
        form = ListingForm()

    return render(request, 'listings/create_local_ai.html', {'form': form})


# ── Messaging ────────────────────────────────────────────────────────────────

@login_required
def inbox_view(request):
    """Show all conversations for the logged-in user."""
    student = get_object_or_404(Student, university_email=request.user.email)
    conversations = Conversation.objects.filter(
        Q(student1=student) | Q(student2=student)
    ).order_by('-updated_at')
    return render(request, 'listings/inbox.html', {'conversations': conversations})


@login_required
def conversation_view(request, conversation_id):
    """Display a single conversation thread and handle new messages."""
    student = get_object_or_404(Student, university_email=request.user.email)
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
    )
    # Only participants can view
    if student not in (conversation.student1, conversation.student2):
        return redirect('messaging_inbox')

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            receiver = conversation.student2 if conversation.student1 == student else conversation.student1
            Message.objects.create(
                conversation=conversation,
                sender=student,
                receiver=receiver,
                message_text=body,
            )
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['last_message_at'])
            return redirect('messaging_conversation', conversation_id=conversation_id)

    messages = conversation.messages.order_by('created_at')
    return render(request, 'listings/conversation.html', {
        'conversation': conversation,
        'messages': messages,
    })


@login_required
def start_conversation(request, user_id):
    """Start (or resume) a conversation with another user."""
    student = get_object_or_404(Student, university_email=request.user.email)
    other_user = get_object_or_404(Student, id=user_id)
    # Look for an existing conversation between the two users
    conversation = Conversation.objects.filter(
        Q(student1=student, student2=other_user) |
        Q(student1=other_user, student2=student)
    ).first()
    if not conversation:
        conversation = Conversation.objects.create(
            student1=student,
            student2=other_user,
        )
    return redirect('messaging_conversation', conversation_id=conversation.id)


# ── Profile ──────────────────────────────────────────────────────────────────

@login_required
def my_profile_view(request):
    """Show the logged-in user's profile and their trip postings."""
    student = get_object_or_404(Student, university_email=request.user.email)
    my_trips = Listing.objects.filter(seller=student).order_by('-created_at')
    received_reviews = Review.objects.filter(reviewed_student=student).order_by('-created_at')
    return render(request, 'listings/profile.html', {
        'my_trips': my_trips,
        'received_reviews': received_reviews,
        'student': student,
    })


def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    trips = Listing.objects.filter(seller=student).order_by('-created_at')

    return render(request, 'listings/student_detail.html', {
        'student': student,
        'trips': trips,
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
    trips = [
        {
            **listing.to_ai_payload(),
            'ai_itinerary': listing.ai_itinerary,
            'ai_cost_estimate': listing.ai_cost_estimate,
            'ai_source': listing.ai_source,
        }
        for listing in Listing.objects.select_related('seller').filter(is_active=True)
    ]
    return JsonResponse({'trips': trips})


@login_required
@require_POST
def ai_generate_trip(request):
    """
    Generate an AI trip bundle from a natural-language request.

    This powers trip creation, itinerary preview, and cost estimation without
    forcing the user to manually fill every field first.
    """
    raw_input = _build_trip_prompt(request)
    if not raw_input:
        return JsonResponse(
            {'success': False, 'error': 'Please provide a trip request, destination, or travel description.'},
            status=400,
        )

    bundle = generate_trip_bundle(raw_input)
    slots = bundle['slots']

    return JsonResponse(
        {
            'success': bundle['success'],
            'raw_input': raw_input,
            'slots': slots,
            'trip_preview': {
                'title': _build_trip_title(slots, raw_input),
                'origin': request.POST.get('origin', '').strip(),
                'destination': slots.get('destination'),
                'departure_date': slots.get('start_date'),
                'return_date': slots.get('end_date'),
                'travel_style': slots.get('travel_style'),
                'interests': slots.get('interests'),
                'seats_available': slots.get('group_size') or 1,
            },
            'itinerary': bundle['itinerary'],
            'cost_estimate': bundle['cost_estimate'],
            'primary_source': bundle['primary_source'],
            'errors': bundle['errors'],
        }
    )


@login_required
@require_POST
def save_ai_trip(request):
    """Persist an AI-generated trip into the current Listing model."""
    student = get_object_or_404(Student, university_email=request.user.email)
    raw_input = _build_trip_prompt(request)
    if not raw_input:
        return JsonResponse({'success': False, 'error': 'Missing trip request.'}, status=400)

    bundle = generate_trip_bundle(raw_input)
    slots = bundle['slots']
    listing = Listing.objects.create(
        seller=student,
        title=request.POST.get('title', '').strip() or _build_trip_title(slots, raw_input),
        description=request.POST.get('description', '').strip() or bundle['itinerary']['result'][:1000],
        origin=request.POST.get('origin', '').strip(),
        destination=slots.get('destination') or request.POST.get('destination', '').strip(),
        departure_date=_coerce_date(slots.get('start_date')),
        return_date=_coerce_date(slots.get('end_date')),
        price=_coerce_decimal(request.POST.get('price')) or _infer_price_from_budget(slots.get('budget')),
        seats_available=max(1, _coerce_int(request.POST.get('seats_available')) or slots.get('group_size') or 1),
        travel_style=slots.get('travel_style') or '',
        interests=slots.get('interests') or '',
        budget_currency=slots.get('budget_currency') or 'USD',
        ai_raw_request=raw_input,
        ai_itinerary=bundle['itinerary']['result'] or '',
        ai_cost_estimate=bundle['cost_estimate']['result'] or '',
        ai_source=bundle['primary_source'],
        contact_method=request.POST.get('contact_method', '').strip() or student.university_email,
    )

    return JsonResponse(
        {
            'success': True,
            'listing_id': listing.id,
            'redirect_url': listing.get_absolute_url(),
            'primary_source': bundle['primary_source'],
        }
    )


@login_required
def trip_match_api(request, pk):
    """
    Return ranked travel buddy matches for a trip listing.

    The score is deterministic, while the summary text is generated by AI.
    """
    listing = get_object_or_404(Listing.objects.select_related('seller'), pk=pk)
    matches = _find_candidate_matches(listing)
    return JsonResponse({'success': True, 'trip_id': listing.id, 'matches': matches})

#Below this is the code for Member 3: The Data & API Developer
#this is the .aggregate() to calculate things with the test data

def harbor_stats(request):
    total_cargo = Ship.objects.aggregate(total=Sum('cargo_weight'))
    total_ships = Ship.objects.count()
    avg_cargo = Ship.objects.aggregate(avg=Avg('cargo_weight'))

    ships_by_country = (
        Ship.objects.values('country')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    ships_per_harbor = (
        Ship.objects.values('harbor__name')
        .annotate(count=Count('id'))
    )

    data = {
        "total_cargo_weight": total_cargo['total'] or 0,
        "total_ships": total_ships,
        "average_cargo_weight": avg_cargo['avg'] or 0,
        "ships_by_country": list(ships_by_country),
        "ships_per_harbor": list(ships_per_harbor),
    }

    return JsonResponse(data)

def harbor_dashboard(request):
    return render(request, 'listings/dashboard.html')


def _build_trip_prompt(request):
    parts = [
        request.POST.get('prompt', '').strip(),
        request.POST.get('raw_input', '').strip(),
        request.POST.get('title', '').strip(),
        request.POST.get('description', '').strip(),
        request.POST.get('destination', '').strip(),
        request.POST.get('origin', '').strip(),
        request.POST.get('interests', '').strip(),
        request.POST.get('travel_style', '').strip(),
    ]
    date_phrase = _date_phrase(
        request.POST.get('departure_date', '').strip(),
        request.POST.get('return_date', '').strip(),
    )
    if date_phrase:
        parts.append(date_phrase)
    price = request.POST.get('price', '').strip()
    if price:
        parts.append(f"Estimated budget: {price} USD")
    return ". ".join(part for part in parts if part)


def _date_phrase(start_date, end_date):
    if start_date and end_date:
        return f"Travel dates: {start_date} to {end_date}"
    if start_date:
        return f"Travel starts on {start_date}"
    return ""


def _build_trip_title(slots, raw_input):
    destination = slots.get('destination') or 'Trip'
    duration = slots.get('duration_days')
    if duration:
        return f"{duration}-day trip to {destination}"
    return f"Trip to {destination}"


def _coerce_date(value):
    if not value or value == 'unspecified':
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _coerce_decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _coerce_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _infer_price_from_budget(budget):
    if not budget:
        return None
    budget = str(budget).lower()
    if budget in {'low', 'budget'}:
        return Decimal('500.00')
    if budget in {'high', 'luxury'}:
        return Decimal('2500.00')
    return Decimal('1200.00')


def _find_candidate_matches(listing):
    base_plan = listing.to_ai_payload()
    candidates = (
        Listing.objects.select_related('seller')
        .filter(is_active=True)
        .exclude(pk=listing.pk)
        .exclude(seller=listing.seller)
    )

    ranked = []
    for candidate in candidates:
        candidate_plan = candidate.to_ai_payload()
        score = calculate_match_score(base_plan, candidate_plan)
        if score < 0.35:
            continue
        explanation = explain_buddy_match(base_plan, candidate_plan, score)
        ranked.append(
            {
                'listing_id': candidate.id,
                'student_id': candidate.seller_id,
                'student_name': str(candidate.seller),
                'title': candidate.title,
                'destination': candidate.destination,
                'departure_date': candidate.departure_date.isoformat() if candidate.departure_date else None,
                'return_date': candidate.return_date.isoformat() if candidate.return_date else None,
                'travel_style': candidate.travel_style,
                'interests': candidate.interests,
                'score': score,
                'match_summary': explanation['result'],
                'match_source': explanation['source'],
            }
        )

    ranked.sort(key=lambda item: item['score'], reverse=True)
    return ranked
