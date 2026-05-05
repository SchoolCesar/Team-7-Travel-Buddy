from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    email = models.EmailField(unique=True)

    bio = models.TextField(max_length=500, blank=True)
    avatar = models.URLField(blank=True)

    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email


class Location(models.Model):
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    place_name = models.CharField(max_length=200, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.city}, {self.country}"

    @property
    def display_name(self) -> str:
        if self.place_name:
            return f"{self.place_name}, {self.city}, {self.country}"
        return f"{self.city}, {self.country}"

class TravelPlan(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="travel_plans"
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    destination = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="travel_plans"
    )

    start_date = models.DateField()
    end_date = models.DateField()

    budget_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    group_size = models.PositiveIntegerField(default=1)  # 想要几个人一起
    flexibility = models.CharField(
        max_length=20,
        choices=[
            ("LOW", "Low"),
            ("MEDIUM", "Medium"),
            ("HIGH", "High"),
        ],
        default="MEDIUM"
    )

    is_open = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.destination}"

    @property
    def duration_days(self) -> int:
        return max(1, (self.end_date - self.start_date).days)

    @property
    def price(self):
        return self.budget_max or self.budget_min

    @property
    def seller(self):
        return self.user

    @property
    def category(self):
        preference = getattr(self.user, "preference", None)
        return getattr(preference, "get_travel_style_display", lambda: "Travel")()

    def get_absolute_url(self) -> str:
        return f"/trips/{self.pk}/"

    def to_ai_payload(self) -> dict:
        preference = getattr(self.user, "preference", None)
        return {
            "id": self.pk,
            "title": self.title,
            "description": self.description,
            "destination": self.destination.display_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "duration_days": self.duration_days,
            "budget_min": float(self.budget_min) if self.budget_min is not None else None,
            "budget_max": float(self.budget_max) if self.budget_max is not None else None,
            "group_size": self.group_size,
            "flexibility": self.flexibility,
            "travel_style": getattr(preference, "travel_style", "RELAX").lower(),
            "interests": getattr(preference, "interests", ""),
            "user_id": self.user_id,
            "username": self.user.username,
        }


class TravelPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preference"
    )

    interests = models.CharField(max_length=300, blank=True)  # food, hiking, museum...

    travel_style = models.CharField(
        max_length=50,
        choices=[
            ("RELAX", "Relaxed"),
            ("ADVENTURE", "Adventure"),
            ("BUDGET", "Budget"),
            ("LUXURY", "Luxury"),
        ],
        default="RELAX"
    )

    preferred_group_size = models.PositiveIntegerField(default=2)

    max_distance_km = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"{self.user.email} preference"


class BuddyRequest(models.Model):
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_requests"
    )

    travel_plan = models.ForeignKey(
        TravelPlan,
        on_delete=models.CASCADE,
        related_name="buddy_requests"
    )

    message = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.from_user} -> {self.travel_plan}"

class Match(models.Model):
    travel_plan = models.ForeignKey(
        TravelPlan,
        on_delete=models.CASCADE,
        related_name="matches"
    )

    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="match_user1")
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="match_user2")

    score = models.FloatField(default=0.0)  # matching score

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("travel_plan", "user1", "user2")

    def __str__(self):
        return f"{self.user1} & {self.user2}"

class Conversation(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conv1")
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conv2")

    travel_plan = models.ForeignKey(
        TravelPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def updated_at(self):
        latest_message = self.messages.order_by("-created_at").first()
        return latest_message.created_at if latest_message else self.created_at


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )

    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def body(self):
        return self.content
