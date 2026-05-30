from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import DestroyAPIView, ListCreateAPIView, UpdateAPIView
from rest_framework.response import Response

from users.models import ClinicBranch, ClinicInvite
from .permissions import IsClinic
from .serializers import (
    ClinicBranchUpdateSerializer,
    ClinicInviteCreateSerializer,
    ClinicInviteSerializer,
)


@extend_schema(tags=['Clinic'])
class BranchUpdateView(UpdateAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicBranchUpdateSerializer
    http_method_names = ['put']

    def get_queryset(self):
        return ClinicBranch.objects.filter(clinic__user=self.request.user)


@extend_schema_view(
    get=extend_schema(responses={200: ClinicInviteSerializer(many=True)}, tags=['Clinic']),
    post=extend_schema(request=ClinicInviteCreateSerializer, responses={201: ClinicInviteSerializer}, tags=['Clinic']),
)
class InviteListCreateView(ListCreateAPIView):
    permission_classes = (IsClinic,)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ClinicInviteCreateSerializer
        return ClinicInviteSerializer

    def get_queryset(self):
        return ClinicInvite.objects.filter(clinic__user=self.request.user).select_related('branch').order_by('-created_at')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['clinic'] = self.request.user.clinic_profile
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save()
        return Response(ClinicInviteSerializer(invite).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={204: None}, tags=['Clinic'])
class InviteDeleteView(DestroyAPIView):
    permission_classes = (IsClinic,)
    serializer_class = ClinicInviteSerializer

    def get_queryset(self):
        return ClinicInvite.objects.filter(clinic__user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response(status=status.HTTP_204_NO_CONTENT)
