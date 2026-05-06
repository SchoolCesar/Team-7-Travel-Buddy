from django.contrib import admin
from .models import Student, Listing, Conversation, Message, Review


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


