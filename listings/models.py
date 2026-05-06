from django.db import models
from django.core.validators import EmailValidator, MinValueValidator, MaxValueValidator
from django.urls import reverse


class Student(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    university_email = models.EmailField(
        unique=True,
        validators=[EmailValidator()],
        help_text="Must be a valid .edu email address"
    )
    phone_number = models.CharField(max_length=15, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['university_email'],
                name='unique_student_email'
            )
        ]
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.university_email})"

    def get_absolute_url(self):
        return reverse('student_detail', args=[str(self.id)])


class Listing(models.Model):
    seller = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='travel_listings'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=1000)

    origin = models.CharField(max_length=100, blank=True)
    destination = models.CharField(max_length=100, blank=True)
    departure_date = models.DateField(null=True, blank=True)
    departure_time = models.TimeField(null=True, blank=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated cost, contribution amount, or ticket price in USD"
    )

    seats_available = models.PositiveIntegerField(
        default=1,
        help_text="Number of available seats, spots, or tickets"
    )
    contact_method = models.CharField(
        max_length=200,
        help_text="Preferred contact method, such as email, phone, or in-app message")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['seller', 'title', 'departure_date'],
                name='unique_travel_listing_per_poster'
            )
        ]

    def __str__(self):
        return f"{self.title}: {self.origin} to {self.destination}"

    def get_absolute_url(self):
        return reverse('listing_detail', args=[str(self.id)])


class Conversation(models.Model):
    student1 = models.ForeignKey(
       Student,
       on_delete=models.CASCADE,
       related_name='conversations_started'
    )
    student2 = models.ForeignKey(
       Student,
       on_delete=models.CASCADE,
       related_name='conversations_received'
    )
    listing = models.ForeignKey(
       Listing,
       on_delete=models.SET_NULL,
       null=True,
       blank=True,
       related_name='conversations'
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Conversation between {self.student1} and {self.student2}"


class Message(models.Model):
   conversation = models.ForeignKey(
       Conversation,
       on_delete=models.CASCADE,
       related_name='messages'
   )
   sender = models.ForeignKey(
       Student,
       on_delete=models.CASCADE,
       related_name='sent_messages'
   )
   receiver = models.ForeignKey(
       Student,
       on_delete=models.CASCADE,
       related_name='received_messages'
   )
   message_text = models.TextField()
   is_read = models.BooleanField(default=False)
   created_at = models.DateTimeField(auto_now_add=True)

   class Meta:
       ordering = ['-created_at']

   def __str__(self):
       return f"Message from {self.sender}"


class Review(models.Model):
    reviewer = models.ForeignKey(
       Student,
       on_delete=models.CASCADE,
       related_name='reviews_given'
    )
    reviewed_student = models.ForeignKey(
       Student,
       on_delete=models.CASCADE,
       related_name='reviews_received'
    )
    listing = models.ForeignKey(
       Listing,
       on_delete=models.CASCADE,
       related_name='reviews'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    review_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['reviewer', 'reviewed_student', 'listing'],
                name='unique_review_per_trip_or_ticket'
            )
        ]

    def __str__(self):
        return f"Review by {self.reviewer}"
