from rest_framework import serializers

from .models import Booking, ExtractionJob, GoogleAccount, ProcessedEmail, Trip, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class GoogleAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleAccount
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class ProcessedEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessedEmail
        fields = "__all__"
        read_only_fields = ["id", "created_at"]


class TripSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class ExtractionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionJob
        fields = "__all__"
        read_only_fields = ["id", "created_at", "completed_at"]
