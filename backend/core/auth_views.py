from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import GoogleAccount
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    UserSerializer,
)


def _token_response(user, response_status=status.HTTP_200_OK):
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        },
        status=response_status,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(
        request,
        username=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
    )
    if user is None:
        return Response(
            {"detail": "Invalid email or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return _token_response(user)


@api_view(["POST"])
@permission_classes([AllowAny])
def signup_view(request):
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return _token_response(user, status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request_view(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user_model = get_user_model()
    user = user_model.objects.filter(
        email__iexact=serializer.validated_data["email"],
    ).first()
    if user and user.has_usable_password():
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = (
            f"{settings.FRONTEND_URL.rstrip('/')}/reset-password/confirm?"
            f"{urlencode({'uid': uid, 'token': token})}"
        )
        send_mail(
            "Reset your Travel Agent password",
            f"Use the link below to choose a new password:\n\n{reset_url}\n\n"
            "If you did not request this change, you can ignore this email.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )

    return Response(
        {"detail": "If an account exists for that email, password reset instructions have been sent."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm_view(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user_model = get_user_model()

    try:
        uid = force_str(urlsafe_base64_decode(serializer.validated_data["uid"]))
        user = user_model._default_manager.get(pk=uid)
    except (TypeError, ValueError, OverflowError, user_model.DoesNotExist):
        return Response(
            {"detail": "This password reset link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not default_token_generator.check_token(user, serializer.validated_data["token"]):
        return Response(
            {"detail": "This password reset link is invalid or has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    password = serializer.validated_data["password"]
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as error:
        return Response({"password": error.messages}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(password)
    user.save(update_fields=["password"])
    return Response(
        {"detail": "Your password has been reset. You can now sign in."},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def google_connect(request):
    if not settings.GOOGLE_CLIENT_ID:
        return Response(
            {"detail": "Google OAuth is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return Response({"auth_url": auth_url}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def google_callback(request):
    code = request.GET.get("code")
    if not code:
        return Response({"detail": "OAuth code is required."}, status=status.HTTP_400_BAD_REQUEST)

    token_payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data=token_payload,
        timeout=30,
    )
    token_response.raise_for_status()
    token_data = token_response.json()

    access_token = token_data.get("access_token")
    if not access_token:
        return Response({"detail": "Failed to get Google access token."}, status=status.HTTP_400_BAD_REQUEST)

    userinfo_response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    userinfo_response.raise_for_status()
    userinfo = userinfo_response.json()

    email = userinfo.get("email")
    if not email:
        return Response({"detail": "Google user email missing."}, status=status.HTTP_400_BAD_REQUEST)

    user_model = get_user_model()
    user = user_model.objects.filter(email=email).first()
    if user is None:
        username = email.split("@")[0]
        base_username = username
        counter = 1
        while user_model.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        user = user_model.objects.create_user(
            username=username,
            email=email,
            password=None,
            first_name=userinfo.get("given_name", ""),
            last_name=userinfo.get("family_name", ""),
        )

    google_account, _ = GoogleAccount.objects.get_or_create(
        user=user,
        provider="google",
        defaults={
            "google_user_id": userinfo.get("sub", ""),
            "email": email,
            "is_connected": True,
        },
    )
    google_account.google_user_id = userinfo.get("sub", "")
    google_account.email = email
    google_account.access_token = access_token
    google_account.refresh_token = token_data.get("refresh_token", google_account.refresh_token)
    google_account.token_expiry = None
    google_account.is_connected = True
    google_account.save(update_fields=[
        "google_user_id",
        "email",
        "access_token",
        "refresh_token",
        "token_expiry",
        "is_connected",
        "updated_at",
    ])

    refresh = RefreshToken.for_user(user)
    frontend_redirect = (
        f"{settings.FRONTEND_URL}/login"
        f"?access={refresh.access_token}&refresh={refresh}&email={email}"
    )
    return redirect(frontend_redirect)


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    refresh_token = None
    if isinstance(request.data, dict):
        refresh_token = request.data.get("refresh")

    try:
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
    except Exception:
        pass

    return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)
