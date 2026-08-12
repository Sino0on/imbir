from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

import random
from .models import (
    DoctorDocument, ClinicPhoto, ClinicDocument, PasswordResetCode, PhoneVerificationCode,
    EmailVerificationCode, LoginCode,
)
from .serializers import (
    LoginSerializer, UserMeSerializer,
    ClientRegisterSerializer, DoctorRegisterSerializer, ClinicRegisterSerializer,
    PasswordResetVerifySerializer, PasswordResetConfirmSerializer,
    PhoneRegisterRequestSerializer, PhoneRegisterConfirmSerializer,
    EmailRegisterRequestSerializer, EmailRegisterConfirmSerializer,
    LoginOTPRequestSerializer, LoginOTPVerifySerializer,
    VerifyEmailConfirmSerializer, VerifyPhoneConfirmSerializer,
)
from users.utils import save_hybrid_documents, send_sms_nikita

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
    request=inline_serializer('PasswordResetRequest', fields={
        'email': serializers.EmailField(required=False),
        'phone': serializers.CharField(required=False),
    }),
    responses={200: inline_serializer('PasswordResetRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email', '').strip()
        phone = request.data.get('phone', '').strip()

        if not email and not phone:
            return Response({'error': 'Email или телефон обязательны'}, status=status.HTTP_400_BAD_REQUEST)

        code = f"{random.randint(100000, 999999)}"

        if email:
            try:
                user = User.objects.get(email=email)
                PasswordResetCode.objects.create(email=email, code=code)

                subject = "Восстановление пароля — Imbir"
                message = (
                    f"Здравствуйте!\n\n"
                    f"Вы получили это письмо, потому что запросили сброс пароля.\n"
                    f"Код подтверждения для сброса пароля:\n\n"
                    f"{code}\n\n"
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
            return Response({'detail': 'Если пользователь существует, письмо с кодом подтверждения отправлено.'}, status=status.HTTP_200_OK)
        else:
            try:
                user = User.objects.get(phone=phone)
                PasswordResetCode.objects.create(phone=phone, code=code)

                message = f"Код подтверждения для сброса пароля в Imbir: {code}"
                send_sms_nikita(phone, message)
            except User.DoesNotExist:
                pass
            return Response({'detail': 'Если пользователь существует, СМС с кодом подтверждения отправлено.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PasswordResetVerifySerializer,
    responses={200: inline_serializer('PasswordResetVerifySuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetVerifyView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'detail': 'Код подтверждён успешно.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PasswordResetConfirmSerializer,
    responses={200: inline_serializer('PasswordResetConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get('email')
        phone = serializer.validated_data.get('phone')
        password = serializer.validated_data['password']
        reset_code = serializer.validated_data['reset_code']

        try:
            if email:
                user = User.objects.get(email=email)
            else:
                user = User.objects.get(phone=phone)
            user.set_password(password)
            user.save()

            reset_code.is_used = True
            reset_code.save()
        except User.DoesNotExist:
            return Response({'error': 'Пользователь не найден'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Пароль успешно сброшен'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PhoneRegisterRequestSerializer,
    responses={200: inline_serializer('PhoneRegisterRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class PhoneRegisterRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PhoneRegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']

        # Generate 4-digit code
        code = f"{random.randint(1000, 9999)}"
        PhoneVerificationCode.objects.create(phone=phone, code=code)

        # Send SMS via Nikita
        message = f"Код подтверждения для регистрации в Imbir: {code}"
        send_sms_nikita(phone, message)

        return Response({'detail': 'Код подтверждения отправлен на указанный номер телефона.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=PhoneRegisterConfirmSerializer,
    responses={201: _TOKEN_RESPONSE},
    tags=['auth'],
)
class PhoneRegisterConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PhoneRegisterConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        password = serializer.validated_data['password']
        first_name = serializer.validated_data['first_name']
        last_name = serializer.validated_data['last_name']
        verification = serializer.validated_data['verification']

        # Generate a unique placeholder email based on phone digits only
        phone_digits = ''.join(c for c in phone if c.isdigit())
        placeholder_email = f"{phone_digits}@phone.imbir.kg"

        # Create user
        user = User.objects.create_user(
            email=placeholder_email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=User.Role.PATIENT
        )

        # Mark code as used
        verification.is_used = True
        verification.save()

        # Login immediately and return tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    request=EmailRegisterRequestSerializer,
    responses={200: inline_serializer('EmailRegisterRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class EmailRegisterRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = EmailRegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Generate 4-digit code
        code = f"{random.randint(1000, 9999)}"
        EmailVerificationCode.objects.create(email=email, code=code)

        subject = "Код подтверждения — Imbir"
        message = f"Код подтверждения для регистрации в Imbir: {code}"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL or 'noreply@imbir.kg', [email], fail_silently=True)

        return Response({'detail': 'Код подтверждения отправлен на указанный email.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=EmailRegisterConfirmSerializer,
    responses={201: _TOKEN_RESPONSE},
    tags=['auth'],
)
class EmailRegisterConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = EmailRegisterConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        first_name = serializer.validated_data['first_name']
        last_name = serializer.validated_data['last_name']
        verification = serializer.validated_data['verification']

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.PATIENT,
        )

        verification.is_used = True
        verification.save()

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    request=LoginOTPRequestSerializer,
    responses={200: inline_serializer('LoginOTPRequestSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
)
class LoginOTPRequestView(APIView):
    """Запросить код входа без пароля — доступно любой существующей роли."""
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        phone = serializer.validated_data['phone']

        code = f"{random.randint(100000, 999999)}"

        if email:
            user = User.objects.filter(email=email).first()
            if user:
                LoginCode.objects.create(email=email, code=code)
                subject = "Код входа — Imbir"
                message = f"Код подтверждения для входа в Imbir: {code}"
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL or 'noreply@imbir.kg', [email], fail_silently=True)
            return Response(
                {'detail': 'Если пользователь существует, письмо с кодом входа отправлено.'},
                status=status.HTTP_200_OK,
            )

        user = User.objects.filter(phone=phone).first()
        if user:
            LoginCode.objects.create(phone=phone, code=code)
            message = f"Код подтверждения для входа в Imbir: {code}"
            send_sms_nikita(phone, message)
        return Response(
            {'detail': 'Если пользователь существует, СМС с кодом входа отправлено.'},
            status=status.HTTP_200_OK,
        )


@extend_schema(request=LoginOTPVerifySerializer, responses={200: _TOKEN_RESPONSE}, tags=['auth'])
class LoginOTPVerifyView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = LoginOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user, context={'request': request}).data,
        })


@extend_schema(
    request=VerifyEmailConfirmSerializer,
    responses={200: inline_serializer('VerifyEmailConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
    summary='Подтвердить email кодом перед регистрацией врача/клиники (аккаунт не создаётся)',
)
class VerifyEmailConfirmView(APIView):
    """Подтверждение email без создания аккаунта — шаг перед многошаговой
    регистрацией врача/клиники. Код запрашивается через EmailRegisterRequestView
    (тот же /api/auth/verify/email/request/ = /api/auth/register/email/request/)."""
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = VerifyEmailConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = serializer.validated_data['verification']
        verification.is_used = True
        verification.save(update_fields=['is_used'])

        return Response({'detail': 'Email подтверждён.'}, status=status.HTTP_200_OK)


@extend_schema(
    request=VerifyPhoneConfirmSerializer,
    responses={200: inline_serializer('VerifyPhoneConfirmSuccess', fields={'detail': serializers.CharField()})},
    tags=['auth'],
    summary='Подтвердить телефон кодом перед регистрацией врача/клиники (аккаунт не создаётся)',
)
class VerifyPhoneConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = VerifyPhoneConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = serializer.validated_data['verification']
        verification.is_used = True
        verification.save(update_fields=['is_used'])

        return Response({'detail': 'Телефон подтверждён.'}, status=status.HTTP_200_OK)



