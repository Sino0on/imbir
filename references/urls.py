from django.urls import path
from .views import (
    CitiesView,
    SpecializationsView,
    ServiceCategoriesView,
    ClinicTypesView,
    LanguagesView,
    EquipmentView,
    ConditionsView,
    PaymentMethodsView,
    CountryCodesView,
    SiteSettingsView,
    UserAccountStatusView,
)

urlpatterns = [
    path('cities/', CitiesView.as_view(), name='ref-cities'),
    path('specializations/', SpecializationsView.as_view(), name='ref-specializations'),
    path('service-categories/', ServiceCategoriesView.as_view(), name='ref-service-categories'),
    path('clinic-types/', ClinicTypesView.as_view(), name='ref-clinic-types'),
    path('languages/', LanguagesView.as_view(), name='ref-languages'),
    path('equipment/', EquipmentView.as_view(), name='ref-equipment'),
    path('conditions/', ConditionsView.as_view(), name='ref-conditions'),
    path('payment-methods/', PaymentMethodsView.as_view(), name='ref-payment-methods'),
    path('country-codes/', CountryCodesView.as_view(), name='ref-country-codes'),
    # Алиас: фронт обращается к countries/
    path('countries/', CountryCodesView.as_view(), name='ref-countries'),
    path('site-settings/', SiteSettingsView.as_view(), name='ref-site-settings'),
    path('user-status/<int:user_id>/', UserAccountStatusView.as_view(), name='ref-user-status'),
]
