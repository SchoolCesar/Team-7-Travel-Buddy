from django import forms
from .models import Listing


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = [
            'title',
            'description',
            'origin',
            'destination',
            'departure_date',
            'return_date',
            'departure_time',
            'price',
            'seats_available',
            'travel_style',
            'interests',
            'budget_currency',
            'ai_raw_request',
            'ai_itinerary',
            'ai_cost_estimate',
            'ai_source',
            'contact_method',
        ]

        widgets = {
            'departure_date': forms.DateInput(attrs={'type': 'date'}),
            'return_date': forms.DateInput(attrs={'type': 'date'}),
            'departure_time': forms.TimeInput(attrs={'type': 'time'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'interests': forms.Textarea(attrs={'rows': 2}),
            'ai_raw_request': forms.HiddenInput(),
            'ai_itinerary': forms.HiddenInput(),
            'ai_cost_estimate': forms.HiddenInput(),
            'ai_source': forms.HiddenInput(),
        }

    def clean_seats_available(self):
        seats = self.cleaned_data.get('seats_available')
        if seats is not None and seats < 1:
            raise forms.ValidationError("Available spots must be at least 1.")
        return seats

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise forms.ValidationError("Total cost cannot be negative.")
        return price
