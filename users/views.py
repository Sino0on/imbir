from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

from .models import DoctorDocument, ClinicPhoto, ClinicDocument
from .serializers import (
    LoginSerializer, UserMeSerializer,
    ClientRegisterSerializer, DoctorRegisterSerializer, ClinicRegisterSerializer,
)
from users.utils import save_hybrid_documents

_TOKEN_RESPONSE = inline_serializer('TokenResponse', fields={
    'access': serializers.CharField(),
    'refresh': serializers.CharField(),
    'user': UserMeSerializer(),
})


@extend_schema(request=LoginSerializer, responses={200: _TOKEN_RESPONSE}, tags=['auth'])
class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        })


@extend_schema(
    request=inline_serializer('LogoutRequest', fields={'refresh': serializers.CharField()}),
    responses={204: None},
    tags=['auth'],
)
class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'refresh токен обязателен'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Неверный или просроченный токен'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=ClientRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class ClientRegisterView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = ClientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(request=DoctorRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class DoctorRegisterView(APIView):
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request):
        serializer = DoctorRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        doctor_profile = user.doctor_profile
        save_hybrid_documents(doctor_profile, 'documents', DoctorDocument, request)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(request=ClinicRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class ClinicRegisterView(APIView):
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request):
        serializer = ClinicRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        clinic_profile = user.clinic_profile
        save_hybrid_documents(clinic_profile, 'photos', ClinicPhoto, request)
        save_hybrid_documents(clinic_profile, 'documents', ClinicDocument, request)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(responses={200: UserMeSerializer}, tags=['auth']),
    put=extend_schema(request=UserMeSerializer, responses={200: UserMeSerializer}, tags=['auth']),
)
class MeView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get(self, request):
        return Response(UserMeSerializer(request.user, context={'request': request}).data)

    def put(self, request):
        serializer = UserMeSerializer(request.user, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


from django.core import signing
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


@extend_schema(
    request=inline_serializer('PasswordResetRequest', fields={'email': serializers.EmailField()}),
    responses={200: inline_serializer('PasswordResetRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response({'error': 'Email обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            token = signing.dumps({'email': user.email}, salt='password-reset')

            subject = "Восстановление пароля — Imbir"
            message = (
                f"Здравствуйте!\n\n"
                f"Вы получили это письмо, потому что запросили сброс пароля.\n"
                f"Используйте следующий токен для подтверждения:\n\n"
                f"{token}\n\n"
                f"Если вы не запрашивали сброс пароля, проигнорируйте это письмо.\n"
            )
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL or 'noreply@imbir.kg',
                [user.email],
                fail_silently=True,
            )
        except User.DoesNotExist:
            pass

        return Response({'detail': 'Если пользователь существует, письмо с инструкциями отправлено.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=inline_serializer('PasswordResetConfirm', fields={
        'token': serializers.CharField(),
        'password': serializers.CharField(),
    }),
    responses={200: inline_serializer('PasswordResetConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        token = request.data.get('token', '').strip()
        password = request.data.get('password', '').strip()

        if not token or not password:
            return Response({'error': 'Токен и пароль обязательны'}, status=status.HTTP_400_BAD_REQUEST)

        if len(password) < 8:
            return Response({'password': 'Пароль должен быть не менее 8 символов.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = signing.loads(token, salt='password-reset', max_age=86400)  # 24 часа
            email = data.get('email')
        except signing.SignatureExpired:
            return Response({'error': 'Срок действия токена истёк'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'error': 'Неверный токен сброса пароля'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Пользователь не найден'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save()

        return Response({'detail': 'Пароль успешно сброшен'}, status=status.HTTP_200_OK)

