from drf_spectacular.utils import extend_schema, inline_serializer
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
        for doc_file in request.FILES.getlist('documents'):
            DoctorDocument.objects.create(doctor=doctor_profile, file=doc_file)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(request=ClinicRegisterSerializer, responses={201: _TOKEN_RESPONSE}, tags=['auth'])
class ClinicRegisterView(APIView):
    permission_classes = (AllowAny,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = ClinicRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        clinic_profile = user.clinic_profile
        for photo_file in request.FILES.getlist('photos'):
            ClinicPhoto.objects.create(clinic=clinic_profile, image=photo_file)
        for doc_file in request.FILES.getlist('documents'):
            ClinicDocument.objects.create(clinic=clinic_profile, file=doc_file)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserMeSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: UserMeSerializer}, tags=['auth'])
class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(UserMeSerializer(request.user).data)
