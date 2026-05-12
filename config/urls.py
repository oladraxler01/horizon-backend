from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Merged all your core imports into one clean block
from core.views import (
    DashboardView,
    RegisterView,
    CreditProfileView,
    TransferView,
    SavingsGoalListView,
    FundSavingsGoalView,
    UserPreferencesView
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth Endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Core Endpoints
    path('api/signup/', RegisterView.as_view(), name='signup'),
    path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/accounts/profile/', CreditProfileView.as_view(), name='accounts_profile'),

    # Financial Action Endpoints
    path('api/transfer/', TransferView.as_view(), name='transfer'),

    # Micro-Savings Garden Endpoints
    path('api/savings/goals/', SavingsGoalListView.as_view(), name='savings-goals'),
    path('api/savings/goals/<int:goal_id>/fund/', FundSavingsGoalView.as_view(), name='fund-goal'),
    path('api/settings/preferences/', UserPreferencesView.as_view(), name='user-preferences'),
]
