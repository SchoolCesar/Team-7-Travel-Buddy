import json
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.utils import timezone

from .ai import calculate_match_score, explain_buddy_match, extract_slots, generate_trip_bundle
from .models import Conversation, Location, Message, TravelPlan

User = get_user_model()


# ── Home ────────────────────────────────────────────────────────────────────

def home(request):
    """Landing page – show a handful of recent trip postings."""
    recent_trips = TravelPlan.objects.select_related("destination", "user").order_by('-created_at')[:6]
    return render(
        request,
        'listings/home.html',
        {
            'recent_trips': recent_trips,
            'total_listings': TravelPlan.objects.filter(is_open=True).count(),
            'total_students': User.objects.count(),
            'total_categories': 4,
        },
    )


# ── Browse trips ─────────────────────────────────────────────────────────────

def trip_browse(request):
    """Browse all active trip postings with optional keyword filter."""
    query = request.GET.get('q', '')
    trips = TravelPlan.objects.select_related("destination", "user").filter(is_open=True).order_by('-created_at')
    if query:
        trips = trips.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(destination__city__icontains=query)
            | Q(destination__country__icontains=query)
            | Q(destination__place_name__icontains=query)
            | Q(user__username__icontains=query)
        )
    return render(request, 'listings/listing_features.html', {'listings': trips, 'query': query, 'trips': trips})


def trip_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    return render(request, 'listings/listing_detail.html', {'listing': listing})


# ── Trip search (GET) ─────────────────────────────────────────────────────────

def trip_search(request):
    """Simple keyword search – reuses browse logic."""
    return trip_browse(request)


# ── Map view ─────────────────────────────────────────────────────────────────

def map_view(request):
    """Map page – passes trip data as JSON for the frontend map."""
    plans = TravelPlan.objects.select_related("destination", "user").filter(
        is_open=True,
        destination__latitude__isnull=False,
        destination__longitude__isnull=False,
    )
    trips = [
        {
            "id": plan.id,
            "title": plan.title,
            "description": plan.description,
            "price": str(plan.budget_max or plan.budget_min or ""),
            "latitude": plan.destination.latitude,
            "longitude": plan.destination.longitude,
            "destination": plan.destination.display_name,
            "seller": plan.user.username,
        }
        for plan in plans
    ]
    return render(request, 'listings/map.html', {
        'trips_json': json.dumps(trips),
        'trips': plans,
        'trips_count': len(trips),
    })


# ── Create trip (AI-assisted) ─────────────────────────────────────────────────

@login_required
def create_local_ai(request):
    """
    AI trip drafting endpoint.

    POST accepts either a free-form `prompt` or the legacy form fields from the
    previous listing generator page. The backend now returns travel-planning data
    powered by Ollama slot extraction and Gemini-first generation.
    """
    if request.method == 'POST':
        raw_input = _build_travel_prompt(request)
        if not raw_input:
            return JsonResponse(
                {"success": False, "error": "Please describe the destination, dates, budget, or travel style."},
                status=400,
            )

        bundle = generate_trip_bundle(raw_input)
        itinerary = bundle["itinerary"]
        cost_estimate = bundle["cost_estimate"]

        return JsonResponse(
            {
                "success": bundle["success"],
                "description": itinerary["result"],
                "itinerary": itinerary["result"],
                "cost_estimate": cost_estimate["result"],
                "slots": bundle["slots"],
                "source": bundle["primary_source"],
                "itinerary_source": itinerary["source"],
                "cost_source": cost_estimate["source"],
                "errors": bundle["errors"],
            }
        )

    return render(request, 'listings/create_local_ai.html', {'categories': []})


# ── Messaging ────────────────────────────────────────────────────────────────

@login_required
def inbox_view(request):
    """Show all conversations for the logged-in user."""
    conversations = Conversation.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).order_by('-created_at')
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
                content=body,
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
    my_trips = TravelPlan.objects.select_related("destination").filter(user=request.user).order_by('-created_at')
    return render(request, 'listings/profile.html', {
        'my_trips': my_trips,
        'received_reviews': [],
        'student': request.user,
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
        plan.to_ai_payload()
        for plan in TravelPlan.objects.select_related("destination", "user").filter(is_open=True)
    ]
    return JsonResponse({'trips': trips})


@login_required
@require_POST
def save_trip_from_ai(request):
    """
    Persist a lightweight travel plan from the legacy AI creator form.

    This keeps the current frontend working while the form is still being
    migrated from the old campus-listing flow to the new travel-buddy flow.
    """
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    raw_input = ". ".join(part for part in [title, description] if part)

    if not title or not raw_input:
        return JsonResponse({"success": False, "error": "Title and AI output are required."}, status=400)

    slots = extract_slots(raw_input)
    today = timezone.localdate()
    start_date = _safe_date(slots.start_date) or today
    duration_days = max(1, int(slots.duration_days or 3))
    end_date = _safe_date(slots.end_date) or (start_date + timedelta(days=duration_days))

    location, _ = Location.objects.get_or_create(
        city=(slots.destination or "Unspecified")[:100],
        country="Unknown",
        defaults={"place_name": slots.destination or "Unspecified"},
    )

    price = _safe_decimal(request.POST.get("price", ""))
    plan = TravelPlan.objects.create(
        user=request.user,
        title=title[:200],
        description=description,
        destination=location,
        start_date=start_date,
        end_date=end_date,
        budget_min=price,
        budget_max=price,
    )
    return redirect("my_profile")


@login_required
@require_POST
def travel_ai_generate(request):
    """Direct JSON API for travel planning from user input."""
    raw_input = _build_travel_prompt(request)
    if not raw_input:
        return JsonResponse(
            {"success": False, "error": "A prompt, destination, or trip description is required."},
            status=400,
        )
    return JsonResponse(generate_trip_bundle(raw_input))


@login_required
def trip_match_api(request, plan_id):
    """
    Return ranked buddy matches for a travel plan.

    Matching uses deterministic rules for scoring and LLMs only for the
    human-readable explanation.
    """
    base_plan = get_object_or_404(
        TravelPlan.objects.select_related("destination", "user"),
        id=plan_id,
        user=request.user,
    )
    base_payload = base_plan.to_ai_payload()

    candidates = (
        TravelPlan.objects.select_related("destination", "user")
        .filter(is_open=True)
        .exclude(id=base_plan.id)
        .exclude(user=request.user)
    )

    matches = []
    for candidate in candidates:
        candidate_payload = candidate.to_ai_payload()
        score = calculate_match_score(base_payload, candidate_payload)
        if score < 0.35:
            continue
        explanation = explain_buddy_match(base_payload, candidate_payload, score)
        matches.append(
            {
                "plan_id": candidate.id,
                "user_id": candidate.user_id,
                "username": candidate.user.username,
                "destination": candidate_payload["destination"],
                "start_date": candidate_payload["start_date"],
                "end_date": candidate_payload["end_date"],
                "travel_style": candidate_payload["travel_style"],
                "interests": candidate_payload["interests"],
                "score": score,
                "match_summary": explanation["result"],
                "match_summary_source": explanation["source"],
            }
        )

    matches.sort(key=lambda item: item["score"], reverse=True)
    return JsonResponse({"success": True, "trip_id": base_plan.id, "matches": matches})


def _build_travel_prompt(request) -> str:
    prompt = (request.POST.get("prompt") or request.POST.get("raw_input") or "").strip()
    if prompt:
        return prompt

    parts = [
        request.POST.get("title", "").strip(),
        request.POST.get("basic_info", "").strip(),
        request.POST.get("description", "").strip(),
        request.POST.get("destination", "").strip(),
        _date_phrase(request.POST.get("start_date", "").strip(), request.POST.get("end_date", "").strip()),
        _budget_phrase(request.POST.get("budget_min", "").strip(), request.POST.get("budget_max", "").strip()),
        request.POST.get("travel_style", "").strip(),
        request.POST.get("interests", "").strip(),
    ]
    return ". ".join(part for part in parts if part)


def _date_phrase(start_date: str, end_date: str) -> str:
    if start_date and end_date:
        return f"Travel dates: {start_date} to {end_date}"
    if start_date:
        return f"Start date: {start_date}"
    return ""


def _budget_phrase(budget_min: str, budget_max: str) -> str:
    budget_min_value = _safe_decimal(budget_min)
    budget_max_value = _safe_decimal(budget_max)
    if budget_min_value is not None and budget_max_value is not None:
        return f"Budget: {budget_min_value} to {budget_max_value} USD"
    if budget_max_value is not None:
        return f"Budget up to {budget_max_value} USD"
    if budget_min_value is not None:
        return f"Budget at least {budget_min_value} USD"
    return ""


def _safe_decimal(value: str):
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _safe_date(value: str):
    if not value or value == "unspecified":
        return None
    try:
        return timezone.datetime.fromisoformat(value).date()
    except ValueError:
        return None
