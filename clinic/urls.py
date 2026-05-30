from django.urls import path
from .views import BranchUpdateView, InviteDeleteView, InviteListCreateView

urlpatterns = [
    path('branches/<int:pk>/', BranchUpdateView.as_view(), name='clinic-branch-update'),
    path('invites/', InviteListCreateView.as_view(), name='clinic-invite-list-create'),
    path('invites/<uuid:pk>/', InviteDeleteView.as_view(), name='clinic-invite-delete'),
]
