from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, User
from .permissions import IsAdmin
from .serializers import (
    AdminUserSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """Public self-service registration (creates a CUSTOMER)."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]  # bonus: rate-limit registration abuse
    queryset = User.objects.all()


class LoginView(TokenObtainPairView):
    """Email + password -> access & refresh tokens (+ user profile)."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]  # bonus: rate-limit credential stuffing


class MeView(generics.RetrieveAPIView):
    """Authenticated user's own profile."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """Blacklist a refresh token so it can no longer be used (logout)."""

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_205_RESET_CONTENT)


class AdminUserViewSet(viewsets.ModelViewSet):
    """Admin-only user management (create operators/admins, list, deactivate, change roles)."""

    queryset = User.objects.all().order_by("id")
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]

    def perform_update(self, serializer):
        # Guard against self-lockout: an admin may not deactivate or demote their own
        # account (the only changes that would revoke their own access mid-session).
        instance = serializer.instance
        if instance.id == self.request.user.id:
            new_role = serializer.validated_data.get("role", instance.role)
            new_active = serializer.validated_data.get("is_active", instance.is_active)
            if new_role != Role.ADMIN or not new_active:
                raise ValidationError(
                    "You cannot change your own role or deactivate your own account."
                )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.id == self.request.user.id:
            raise ValidationError("You cannot delete your own account.")
        instance.delete()
