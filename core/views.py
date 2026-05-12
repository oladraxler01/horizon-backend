from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

# CRITICAL: We must import Decimal for money math so Python doesn't crash
from decimal import Decimal, InvalidOperation

# FIXED IMPORTS: Removed the trailing comma, added SavingsGoal
from .models import Transaction, User, CreditProfile, CreditActivity, SavingsGoal, UserPreferences
from .serializers import TransactionSerializer, UserSerializer
from accounts.models import SavingsAccount, CurrentAccount

# --- REGISTRATION VIEW ---
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        instance.set_password(instance.password)
        instance.save()


# --- DASHBOARD VIEW ---
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        savings = SavingsAccount.objects.filter(user=user).first()
        current = CurrentAccount.objects.filter(user=user).first()
        transactions = Transaction.objects.filter(user=user).order_by('-timestamp')[:5]

        data = {
            "user": UserSerializer(user).data,
            "savings_balance": savings.balance if savings else 0,
            "current_balance": current.balance if current else 0,
            "recent_transactions": TransactionSerializer(transactions, many=True).data
        }
        return Response(data)


# --- ACCOUNTS / CREDIT PROFILE VIEW ---
class CreditProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = CreditProfile.objects.get_or_create(user=request.user)

        base = getattr(profile, 'base_score', 600)
        rent = getattr(profile, 'rent_verified', False)
        phone = getattr(profile, 'phone_bill_verified', False)
        stream = getattr(profile, 'streaming_verified', False)
        endorse = getattr(profile, 'community_endorsements', 0)

        calc_score = base
        if rent: calc_score += 50
        if phone: calc_score += 30
        if stream: calc_score += 20
        calc_score += (endorse * 5)
        final_score = min(calc_score, 850)

        activities = CreditActivity.objects.filter(profile=profile).order_by('-id')[:10]

        return Response({
            "score": final_score,
            "toggles": {
                "rent": rent,
                "phone": phone,
                "streaming": stream,
            },
            "endorsements": endorse,
            "activities": [
                {"source": a.source, "date": a.date, "status": a.status, "impact": f"+{a.impact} pts"}
                for a in activities
            ]
        })


# --- TRANSFER VIEW (FIXED DECIMAL BUG) ---
class TransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sender = request.user
        recipient_email = request.data.get('recipient_email')

        try:
            # Safely convert to Decimal instead of float
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                sender_account = SavingsAccount.objects.select_for_update().get(user=sender)
                recipient_account = SavingsAccount.objects.select_for_update().get(user__email=recipient_email)

                if sender_account.balance < amount:
                    return Response({"error": "Insufficient funds"}, status=status.HTTP_400_BAD_REQUEST)

                sender_account.balance -= amount
                recipient_account.balance += amount

                sender_account.save()
                recipient_account.save()

                Transaction.objects.create(
                    user=sender,
                    amount=-amount,
                    description=f"Transfer to {recipient_email}"
                )
                Transaction.objects.create(
                    user=recipient_account.user,
                    amount=amount,
                    description=f"Transfer from {sender.email}"
                )

                return Response({"message": "Transfer successful"}, status=status.HTTP_200_OK)

        except SavingsAccount.DoesNotExist:
            return Response({"error": "Recipient account not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- 1. VIEW TO GET AND CREATE GOALS ---
class SavingsGoalListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        goals = SavingsGoal.objects.filter(user=request.user)

        goal_data = []
        for goal in goals:
            if goal.target_amount > 0:
                percentage = int((goal.current_amount / goal.target_amount) * 100)
            else:
                percentage = 0

            goal_data.append({
                "id": goal.id,
                "name": goal.name,
                "target_amount": float(goal.target_amount),
                "current_amount": float(goal.current_amount),
                "percentage": min(percentage, 100)
            })

        return Response({
            "goals": goal_data,
            "daily_growth": 12.40
        })

    def post(self, request):
        name = request.data.get('name')
        try:
            target_amount = Decimal(str(request.data.get('target_amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid target amount"}, status=status.HTTP_400_BAD_REQUEST)

        if not name or target_amount <= 0:
            return Response({"error": "Name and valid Target Amount required"}, status=status.HTTP_400_BAD_REQUEST)

        goal = SavingsGoal.objects.create(
            user=request.user,
            name=name,
            target_amount=target_amount
        )
        return Response({"message": "Goal planted successfully!", "id": goal.id}, status=status.HTTP_201_CREATED)


# --- 2. VIEW TO ADD MONEY TO A GOAL (FIXED DECIMAL BUG) ---
class FundSavingsGoalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, goal_id):
        try:
            # Safely convert frontend number to Python Decimal
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                main_account = SavingsAccount.objects.select_for_update().get(user=request.user)
                goal = SavingsGoal.objects.select_for_update().get(id=goal_id, user=request.user)

                if main_account.balance < amount:
                    return Response({"error": "Insufficient funds in main account"}, status=status.HTTP_400_BAD_REQUEST)

                main_account.balance -= amount
                goal.current_amount += amount

                main_account.save()
                goal.save()

                Transaction.objects.create(
                    user=request.user,
                    amount=-amount,
                    description=f"Funded Savings Goal: {goal.name}"
                )

            return Response({"message": f"Successfully added ₦{amount} to {goal.name}!"}, status=status.HTTP_200_OK)

        # Added this block so if user has no SavingsAccount, it tells them instead of throwing a 500
        except SavingsAccount.DoesNotExist:
            return Response({"error": "Main savings account not found. Please deposit funds first."}, status=status.HTTP_404_NOT_FOUND)
        except SavingsGoal.DoesNotExist:
            return Response({"error": "Goal not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print("🚨 CRASH REASON:", repr(e))
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- 3. VIEW FOR SETTINGS & ACCESSIBILITY ---
class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Fetch or create settings automatically so it never crashes on a new user
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)

        return Response({
            "dyslexia_font": prefs.dyslexia_font,
            "simplified_numbers": prefs.simplified_numbers,
            "anxiety_mode": prefs.anxiety_mode,
            "high_contrast": prefs.high_contrast,
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)

        # Look at the incoming JSON data and only update the fields that were sent
        data = request.data
        if 'dyslexia_font' in data:
            prefs.dyslexia_font = data['dyslexia_font']
        if 'simplified_numbers' in data:
            prefs.simplified_numbers = data['simplified_numbers']
        if 'anxiety_mode' in data:
            prefs.anxiety_mode = data['anxiety_mode']
        if 'high_contrast' in data:
            prefs.high_contrast = data['high_contrast']

        prefs.save()

        return Response({"message": "Preferences updated successfully"}, status=status.HTTP_200_OK)
