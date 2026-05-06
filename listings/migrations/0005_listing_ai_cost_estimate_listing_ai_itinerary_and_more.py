from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0004_harbor_remove_listing_category_ship_delete_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="listing",
            name="ai_cost_estimate",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="listing",
            name="ai_itinerary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="listing",
            name="ai_raw_request",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="listing",
            name="ai_source",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="listing",
            name="budget_currency",
            field=models.CharField(blank=True, default="USD", max_length=10),
        ),
        migrations.AddField(
            model_name="listing",
            name="interests",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="listing",
            name="return_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="listing",
            name="travel_style",
            field=models.CharField(blank=True, max_length=50),
        ),
    ]
