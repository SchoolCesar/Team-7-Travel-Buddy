from django.contrib import admin
from .models import Student, Listing, Conversation, Message, Review, Harbor, Ship


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'university_email', 'is_verified', 'created_at']
    list_filter = ['is_verified', 'created_at']
    search_fields = ['first_name', 'last_name', 'university_email']


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ['title', 'seller', 'price', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
   list_display = ['student1', 'student2', 'listing', 'last_message_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
   list_display = ['sender', 'receiver', 'created_at', 'is_read']
   list_filter = ['is_read']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
       list_display = ['reviewer', 'reviewed_student', 'rating', 'created_at']
       list_filter = ['rating']


#Below this is the code for Member 3: The Data & API Developer
#I added Harbor and Ship to admin which you can find with this url http://127.0.0.1:8000/admin/
#these are also temporary until we pick exact data to use

@admin.register(Harbor)
class HarborAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']


@admin.register(Ship)
class ShipAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'cargo_weight', 'harbor']
    list_filter = ['country', 'harbor']
    search_fields = ['name', 'country']