import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TravelBuddy.settings')
django.setup()

from listings.models import Student, Category, Listing

# Clear everything
Listing.objects.all().delete()
Student.objects.all().delete()
Category.objects.all().delete()

# Create Categories
cats = [
    Category(name="Tutoring", category_type="SERVICE", description="Academic tutoring"),
    Category(name="Home Services", category_type="SERVICE", description="Cleaning services"),
    Category(name="Fundraisers", category_type="FUNDRAISER", description="Charity events"),
    Category(name="Clothing & Accessories", category_type="SELLER", description="Clothing items"),
    Category(name="Event Tickets", category_type="SELLER", description="Event tickets"),
]
Category.objects.bulk_create(cats)
print(f"Created {Category.objects.count()} categories")

# Create Students
studs = [
    Student(first_name="Sarah", last_name="Johnson", university_email="sjohnson2@illinois.edu", phone_number="217-555-0101", bio="CS student", is_verified=True),
    Student(first_name="Michael", last_name="Chen", university_email="mchen45@illinois.edu", phone_number="217-555-0102", bio="Math major", is_verified=True),
    Student(first_name="Priya", last_name="Patel", university_email="ppatel23@illinois.edu", phone_number="217-555-0105", bio="Chemistry TA", is_verified=True),
    Student(first_name="Maria", last_name="Garcia", university_email="mgarcia@illinois.edu", phone_number="217-555-0107", bio="Ticket seller", is_verified=True),
    Student(first_name="Alex", last_name="Williams", university_email="awill99@illinois.edu", phone_number="217-555-0108", bio="Econ major", is_verified=True),
]
Student.objects.bulk_create(studs)
print(f"Created {Student.objects.count()} students")

# Create Listings
tutoring = Category.objects.get(name="Tutoring")
home = Category.objects.get(name="Home Services")
fund = Category.objects.get(name="Fundraisers")
cloth = Category.objects.get(name="Clothing & Accessories")
tick = Category.objects.get(name="Event Tickets")

sarah = Student.objects.get(first_name="Sarah")
michael = Student.objects.get(first_name="Michael")
priya = Student.objects.get(first_name="Priya")
maria = Student.objects.get(first_name="Maria")
alex = Student.objects.get(first_name="Alex")

lists = [
    Listing(seller=sarah, category=tutoring, title="Python Tutoring", description="CS help", price=25, contact_method="email", accepted_payment="VENMO", is_active=True),
    Listing(seller=michael, category=tutoring, title="Calculus Tutoring", description="Math help", price=20, contact_method="phone", accepted_payment="CASH", is_active=True),
    Listing(seller=priya, category=tutoring, title="Chemistry Help", description="Chem help", price=15, contact_method="email", accepted_payment="VENMO", is_active=True),
    Listing(seller=alex, category=tutoring, title="Essay Editing", description="Writing help", price=18, contact_method="email", accepted_payment="PAYPAL", is_active=True),
    Listing(seller=sarah, category=home, title="Cleaning Service", description="Apartment cleaning", price=40, contact_method="phone", accepted_payment="CASH", is_active=True),
    Listing(seller=priya, category=fund, title="Bake Sale", description="Charity bake sale", price=3, contact_method="email", accepted_payment="CASH", is_active=True),
    Listing(seller=michael, category=cloth, title="Champion Hoodie", description="Vintage hoodie", price=45, contact_method="phone", accepted_payment="VENMO", is_active=True),
    Listing(seller=michael, category=cloth, title="Ray-Ban Sunglasses", description="Designer sunglasses", price=60, contact_method="phone", accepted_payment="VENMO", is_active=True),
    Listing(seller=maria, category=tick, title="Basketball Tickets", description="Illinois game", price=30, contact_method="phone", accepted_payment="VENMO", is_active=True),
    Listing(seller=alex, category=fund, title="Car Wash", description="Charity car wash", price=10, contact_method="email", accepted_payment="CASH", is_active=True),
]
Listing.objects.bulk_create(lists)
print(f"Created {Listing.objects.count()} listings")

print("✅ ALL DATA LOADED!")
