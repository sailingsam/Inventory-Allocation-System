from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Public profile representation (no secrets)."""

    class Meta:
        model = User
        fields = ("id", "email", "role", "first_name", "last_name", "date_joined")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Self-service registration. Always creates a CUSTOMER — privileged roles are created by
    an Admin via the user-management endpoint or the seed script (operators can't self-promote).
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "email", "password", "first_name", "last_name")
        read_only_fields = ("id",)

    def create(self, validated_data):
        return User.objects.create_user(role=Role.CUSTOMER, **validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """JWT login keyed on email; embeds role in the token and returns the user profile."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    """Accepts a refresh token to blacklist (logout)."""

    refresh = serializers.CharField()


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin-only user management: create/list/update users with an explicit role."""

    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "email", "role", "password", "is_active", "date_joined")
        read_only_fields = ("id", "date_joined")

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "This field is required."})
        role = validated_data.pop("role", Role.CUSTOMER)
        return User.objects.create_user(password=password, role=role, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
