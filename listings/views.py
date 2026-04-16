# from django.shortcuts import render
#
#
# from django.http import HttpResponse
# from django.shortcuts import render
# from django.views import View
# from django.views.generic import ListView
# from .models import Listing
#
# def listing_manual_view(request):
#    listings = Listing.objects.filter(is_active=True)
#
#
#    html = "<h1>Collective Circle Listings</h1>"
#    for listing in listings:
#        html += f"""
#            <div>
#                <h3>{listing.title}</h3>
#                <p>Category: {listing.category.name}</p>
#                <p>Seller: {listing.seller.first_name}</p>
#            </div>
#            <hr>
#        """
#
#
#    return HttpResponse(html)
#
# def listing_render_view(request):
#    listings = Listing.objects.filter(is_active=True)
#    return render(
#        request,
#        "listings/listing_features.html",
#        {"listings": listings}
#    )
#
# class ListingBaseCBV(View):
# def get(self, request):
#        listings = Listing.objects.filter(is_active=True)
#        return render(
#            request,
#            "listings/listing_features.html",
#            {"listings": listings}
#        )
#
# class ListingGenericCBV(ListView):
#    model = Listing
#    template_name = "listings/listing_features.html"
#    context_object_name = "listings"
#
#     def get_queryset(self):
#         return Listing.objects.filter(is_active=True)
#

from django.http import HttpResponse,JsonResponse
from django.shortcuts import render,redirect
from django.views import View
from django.views.generic import ListView
from django.db.models import Count, F
from .models import Listing, Student
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView
from .models import Student, Category
import csv
import json
import logging

import requests
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.conf import settings
from django.views.decorators.http import require_http_methods

from django.contrib import messages

logger = logging.getLogger(__name__)


def listing_manual_view(request):
    listings = Listing.objects.filter(is_active=True)
    html = "<h1>Collective Circle Listings</h1>"
    for listing in listings:
        html += f"""
            <div>
                <h3>{listing.title}</h3>
                <p>Category: {listing.category.name}</p>
                <p>Seller: {listing.seller.first_name}</p>
            </div>
            <hr>
        """
    return HttpResponse(html)

@login_required
def listing_render_view(request):
    listings = Listing.objects.filter(is_active=True)
    return render(
        request,
        "listings/listing_features.html",
        {"listings": listings}
    )


class ListingBaseCBV(View):
    def get(self, request): # Fixed Indentation
        listings = Listing.objects.filter(is_active=True)
        return render(
            request,
            "listings/listing_features.html",
            {"listings": listings})


class ListingGenericCBV(ListView):
    model = Listing
    template_name = "listings/listing_features.html"
    context_object_name = "listings"

    def get_queryset(self): # Fixed Indentation
        return Listing.objects.filter(is_active=True)

# started here in week 3: Swarnika's part

def home_view(request):
    total_listings = Listing.objects.filter(is_active=True).count()
    total_students = Student.objects.filter(is_verified=True).count()
    total_categories = Category.objects.count()
    context = {
        'total_listings': total_listings,
        'total_students': total_students,
        'total_categories': total_categories,
    }
    return render(request, 'listings/home.html', context)


class ListingDetailView(DetailView):
    model = Listing
    template_name = 'listings/listing_detail.html'
    context_object_name = 'listing'


class StudentDetailView(DetailView):
    model = Student
    template_name = 'listings/student_detail.html'
    context_object_name = 'student'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['student_listings'] = self.object.listings.filter(is_active=True)
        return context


class CategoryDetailView(DetailView):
    model = Category
    template_name = 'listings/category_detail.html'
    context_object_name = 'category'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category_listings'] = self.object.listings.filter(is_active=True)
        return context

class StudentListView(ListView):
    model = Student
    template_name = 'listings/student_list.html'
    context_object_name = 'students'
    def get_queryset(self):
        return Student.objects.filter(is_verified=True)


class CategoryListView(ListView):
    model = Category
    template_name = 'listings/category_list.html'
    context_object_name = 'categories'


class ListingFilterCBV(ListView):
    model = Listing
    template_name = 'listings/listing_filter.html'
    context_object_name = 'listings'

    def get_queryset(self):
        return Listing.objects.filter(is_active=True)

    def post(self, request, *args, **kwargs):
        min_price = request.POST.get('min_price', '')
        max_price = request.POST.get('max_price', '')

        listings = Listing.objects.filter(is_active=True)
        if min_price:
            listings = listings.filter(price__gte=float(min_price))
        if max_price:
            listings = listings.filter(price__lte=float(max_price))

        return render(request, self.template_name, {
            'listings': listings,
            'min_price': min_price,
            'max_price': max_price,
            'search_type': 'POST (CBV Implementation)'
        })

def listing_search_get(request):
    query = request.GET.get('q', '')
    if query:
        listings = Listing.objects.filter(
            is_active=True,
            title__icontains=query
        ) | Listing.objects.filter(
            is_active=True,
            description__icontains=query
        )
    else:
        listings = Listing.objects.filter(is_active=True)
    context = {
        'listings': listings,
        'query': query,
        'search_type': 'GET'
    }
    return render(request, 'listings/listing_search.html', context)


# def listing_search_post(request):
#     listings = Listing.objects.filter(is_active=True)
#     min_price = None
#     max_price = None
#     if request.method == 'POST':
#         min_price = request.POST.get('min_price', '')
#         max_price = request.POST.get('max_price', '')
#         if min_price:
#             listings = listings.filter(price__gte=float(min_price))
#         if max_price:
#             listings = listings.filter(price__lte=float(max_price))
#
#     context = {
#         'listings': listings,
#         'min_price': min_price,
#         'max_price': max_price,
#         'search_type': 'POST'
#     }
#     return render(request, 'listings/listing_filter.html', context)


def listing_by_category_name(request, category_name):
    listings = Listing.objects.filter(
        is_active=True,
        category__name__iexact=category_name
    )
    context = {
        'listings': listings,
        'category_name': category_name,
        'count': listings.count()
    }
    return render(request, 'listings/listing_by_category.html', context)


def aggregation_stats(request):
    from django.db.models import Count
    total_listings = Listing.objects.filter(is_active=True).count()
    total_students = Student.objects.count()
    categories_with_counts = Category.objects.annotate(
        listing_count=Count('listings')
    ).order_by('-listing_count')
    students_with_counts = Student.objects.annotate(
        listing_count=Count('listings')
    ).filter(listing_count__gt=0).order_by('-listing_count')
    context = {
        'total_listings': total_listings,
        'total_students': total_students,
        'categories_with_counts': categories_with_counts,
        'students_with_counts': students_with_counts,
    }
    return render(request, 'listings/aggregation_stats.html', context)

def listing_api_list(request):
    listings = Listing.objects.filter(is_active=True)
    category_name = request.GET.get('cat')
    if category_name:
        listings = listings.filter(category__name__icontains=category_name)
    data = []
    for item in listings:
        data.append({
            "title": item.title,
            "price": str(item.price) if item.price else "Free",
            "category": item.category.name,
            "seller": item.seller.first_name
        })
    return JsonResponse({"listings": data, "count": len(data)}, safe=False)

def listings_per_category_api(request):
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    data = (
        Listing.objects
        .filter(is_active=True)
        .values(category_name=F("category__name"))
        .annotate(listing_count=Count("id"))
        .order_by("category_name")
    )
    return JsonResponse(list(data), safe=False)

def api_mime_demo(request):
    sample_data = {"message": "Hello, this is a MIME test"}
    if request.GET.get('type') == 'http':
        return HttpResponse(json.dumps(sample_data))
    return JsonResponse(sample_data)

def category_chart_view(request):
    return render(request, "listings/category_chart.html")

from django.db.models import Avg, F

def listings_avg_price_per_category_api(request):
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    data = (
        Listing.objects.filter(is_active=True, price__isnull=False)
        .values(category_name=F("category__name"))
        .annotate(avg_price=Avg("price"))
        .order_by("category_name")
    )
    data_list = [
        {"category_name": d["category_name"], "avg_price": float(d["avg_price"])}
        for d in data
    ]
    return JsonResponse(data_list, safe=False)

def price_line_chart_view(request):
    return render(request, "listings/price_line_chart.html")

@login_required
def external_api_demo(request):
    name = request.GET.get("name", "")
    if not name:
        return JsonResponse({"error": "Please provide a 'name' parameter"}, status=400)
    try:
        response = requests.get(
            "https://api.agify.io",
            params={"name": name},
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)
    result = {
        "query_name": name,
        "predicted_age": data.get("age"),
        "count_of_listings": Listing.objects.filter(seller__first_name__iexact=name).count()
    }
    return JsonResponse(result)

def export_students_csv(request):
    now = timezone.now()
    filename = f"students_{now.strftime('%Y-%m-%d_%H-%M')}.csv"
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(['First Name', 'Last Name', 'Email', 'Verified', 'Created At'])
    for student in Student.objects.all().order_by('first_name'):
        writer.writerow([
            student.first_name,
            student.last_name,
            student.university_email,
            student.is_verified,
            student.created_at,
        ])
    return response

def export_students_json(request):
    now = timezone.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"students_{now}.json"
    students_qs = Student.objects.all().order_by('id')
    students_list = [
        {
            "id": s.id,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "email": s.university_email,
            "is_verified": s.is_verified
        }
        for s in students_qs
    ]
    data = {
        "generated_at": timezone.now().isoformat(),
        "record_count": students_qs.count(),
        "students": students_list
    }

    response = JsonResponse(data, json_dumps_params={"indent": 2})
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def reports_view(request):
    total_students = Student.objects.count()
    verified_students = Student.objects.filter(is_verified=True).count()
    students_by_verified = Student.objects.values('is_verified').annotate(count=Count('id'))
    students_dict = {str(item['is_verified']): item['count'] for item in students_by_verified}
    context = {
        "total_students": total_students,
        "verified_students": verified_students,
        "students_by_verified": students_dict
    }
    return render(request, "listings/reports.html", context)

def gemini_ai_demo(request):
    user_text = request.GET.get("text", "")
    if not user_text:
        return JsonResponse({"error": "Please provide a 'text' parameter"}, status=400)
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = f"""
        Summarize the following text in 3 bullet points:
        {user_text}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        result = {
            "input": user_text,
            "summary": response.text
        }
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def signup_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login")
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {"form": form})
# ===== LOCAL DESCRIPTION ENGINE =====
from .ai.local_llm import generate_listing_description

@login_required
@require_http_methods(["GET", "POST"])
def create_with_local_ai(request):
    """
    Create listing description using local semantic retrieval.
    """
    if request.method == 'POST':
        # Get form data
        title = request.POST.get('title', '').strip()
        category_id = request.POST.get('category')
        price = request.POST.get('price', '0')
        basic_info = request.POST.get('basic_info', '').strip()
        
        # Validate
        if not all([title, category_id, basic_info]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
        
        try:
            category = Category.objects.get(id=category_id)
            price_float = float(price) if price else 0.0
            
            # Generate with local semantic retrieval engine.
            result = generate_listing_description(
                title=title,
                category=category.name,
                price=price_float,
                basic_info=basic_info
            )
            
            return JsonResponse({
                'success': result['success'],
                'description': result['description'],
                'source': result['source'],
                'model': 'TF-IDF Semantic Retrieval + Rule Engine (Local)',
                'confidence_score': result.get('confidence_score', 0.0),
                'error': result.get('error'),
            })
            
        except Category.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid category'}, status=400)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid price'}, status=400)
        except Exception as e:
            logger.error(f"Local AI error: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    # GET - show form
    categories = Category.objects.all()
    return render(request, 'listings/create_local_ai.html', {'categories': categories})


@login_required
@require_http_methods(["POST"])
def save_listing(request):
    """
    Save the AI-generated listing to the database.
    Expects POST data: title, category, price, description,
                       contact_method, accepted_payment

    The seller is linked via the Student profile of the logged-in user.
    Requires the logged-in User to have a linked Student record.
    """
    title = request.POST.get('title', '').strip()
    category_id = request.POST.get('category')
    price = request.POST.get('price', '') or None
    description = request.POST.get('description', '').strip()
    contact_method = request.POST.get('contact_method', '').strip()
    accepted_payment = request.POST.get('accepted_payment', 'VENMO')

    # Basic validation
    if not all([title, category_id, description]):
        messages.error(request, 'Missing required fields.')
        return redirect('create_local_ai')

    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        messages.error(request, 'Invalid category.')
        return redirect('create_local_ai')

    # Find the Student linked to this user
    # Harbor's Student model uses university_email; try matching by username or email
    try:
        # Try matching student by email == user's email
        student = Student.objects.get(university_email=request.user.email)
    except Student.DoesNotExist:
        # Fallback: first student (for dev/demo only — swap for proper auth link)
        student = Student.objects.first()
        if not student:
            messages.error(request, 'No student profile found. Please contact support.')
            return redirect('create_local_ai')

    price_val = None
    if price:
        try:
            price_val = float(price)
        except ValueError:
            pass

    # Create the listing
    listing = Listing.objects.create(
        seller=student,
        category=category,
        title=title,
        description=description,
        price=price_val,
        contact_method=contact_method or 'Contact via Harbor',
        accepted_payment=accepted_payment,
        is_active=True,
    )

    messages.success(request, f'Listing "{listing.title}" posted successfully!')
    return redirect('listing_detail', pk=listing.pk)
