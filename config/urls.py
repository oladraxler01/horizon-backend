from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Merged all your core imports into one clean block
from core.views import (
    DashboardView,
    OracleChatView,
    OracleDashboardView,
    RegisterView,
    CreditProfileView,
    TransferView,
    SavingsGoalListView,
    FundSavingsGoalView,
    UserPreferencesView,
    CommunityLendingDashboardView,
    SupportFundingRequestView,
    CardsDashboardView,
    UpdateCardControlView,
    # --- ADDED FOR ORACLE PL/SQL PROCEDURES ---
    DepositView,
    WithdrawalView,
    ProcedureTransferView
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

    # --- NEW ORACLE PL/SQL ENDPOINTS (PART 5 & 6) ---
    path('api/bank/proc-deposit/', DepositView.as_view(), name='proc_deposit'),
    path('api/bank/proc-withdraw/', WithdrawalView.as_view(), name='proc_withdraw'),
    path('api/bank/proc-transfer/', ProcedureTransferView.as_view(), name='proc_transfer'),

    # Micro-Savings Garden Endpoints
    path('api/savings/goals/', SavingsGoalListView.as_view(), name='savings-goals'),
    path('api/savings/goals/<int:goal_id>/fund/', FundSavingsGoalView.as_view(), name='fund-goal'),

    # Settings
    path('api/settings/preferences/', UserPreferencesView.as_view(), name='user-preferences'),

    # Card Management Endpoints
    path('api/cards/', CardsDashboardView.as_view(), name='cards-dashboard'),
    path('api/cards/<int:card_id>/controls/', UpdateCardControlView.as_view(), name='update-card-controls'),

    # Community Lending Endpoints
    path('api/lending/dashboard/', CommunityLendingDashboardView.as_view(), name='lending-dashboard'),
    path('api/lending/requests/<int:request_id>/support/', SupportFundingRequestView.as_view(), name='support-request'),

    # Horizon Oracle Endpoints
    path('api/oracle/dashboard/', OracleDashboardView.as_view(), name='oracle-dashboard'),
    path('api/oracle/chat/', OracleChatView.as_view(), name='oracle-chat'),
]
