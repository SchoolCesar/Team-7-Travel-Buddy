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
            'departure_time',
            'price',
            'seats_available',
            'contact_method',
        ]

        widgets = {
            'departure_date': forms.DateInput(attrs={'type': 'date'}),
            'departure_time': forms.TimeInput(attrs={'type': 'time'}),
            'description': forms.Textarea(attrs={'rows': 4}),
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