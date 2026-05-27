import os
from django.db import transaction
from django.db import connection
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from decimal import Decimal, InvalidOperation

# Modern GenAI SDK
from google import genai
from django.conf import settings

# Models & Serializers
from .models import (
    Transaction, User, CreditProfile, CreditActivity,
    SavingsGoal, UserPreferences, FundingRequest, Endorsement, BankCard, OracleMessage
)
from .serializers import TransactionSerializer, UserSerializer
from accounts.models import SavingsAccount, CurrentAccount

# Initialize the modern Gemini Client
client = genai.Client(api_key=settings.GEMINI_API_KEY)


# --- REGISTRATION VIEW ---
# --- REPLACED REGISTRATION VIEW (WITH VERITAS INTEGRATION & RAW ORACLE CALLS) ---
class RegisterView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        # 1. Extract form data sent by your Next.js frontend
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        phone = request.data.get('phone', '')
        univ_id = request.data.get('university_id', '').strip() # Matric No or Staff ID

        if not email or not password or not univ_id:
            return Response({"error": "Email, password, and University ID are required"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Automated Campus Segmentation Logic
        if "student.veritas.edu.ng" in email or univ_id.upper().startswith("VUG"):
            user_type = "STUDENT"
            account_type = "SAVINGS"
            daily_limit = Decimal('50000.00')   # Strict lower limit for student profiles
        else:
            user_type = "STAFF"
            account_type = "CURRENT"
            daily_limit = Decimal('500000.00') # Higher transaction allowance for faculty/staff

        try:
            with transaction.atomic():
                # 3. Create the Base Django User (keeps your API login system working)
                if User.objects.filter(email=email).exists():
                    return Response({"error": "User with this email already exists"}, status=status.HTTP_400_BAD_REQUEST)

                user_instance = User.objects.create(
                    username=email,
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )
                user_instance.set_password(password)
                user_instance.save()

                # 4. Open direct tunnel to Oracle Database to execute Part 5 & 6 requirements
                with connection.cursor() as cursor:
                    # Insert into raw Customers table
                    cursor.execute("""
                        INSERT INTO Customers (FirstName, LastName, Email, PhoneNumber, UserType, UniversityID)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING CustomerID INTO :cid
                    """, [first_name, last_name, email, phone, user_type, univ_id])

                    # Capture the auto-incremented CustomerID sequence from Oracle
                    customer_id = cursor.get_returned_value()

                    # Insert into raw Accounts table matching their role restrictions
                    cursor.execute("""
                        INSERT INTO Accounts (CustomerID, AccountType, Balance, DailyTransferLimit, IsActive)
                        VALUES (%s, %s, 0.00, %s, 1)
                    """, [customer_id, account_type, daily_limit])

                return Response({
                    "message": f"Registration successful! Verified as {user_type}.",
                    "account_provisioned": account_type
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": f"Database provisioning failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


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


# --- TRANSFER VIEW ---
class TransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sender = request.user
        recipient_email = request.data.get('recipient_email')

        try:
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


# --- SAVINGS GOAL VIEWS ---
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


class FundSavingsGoalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, goal_id):
        try:
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

        except SavingsAccount.DoesNotExist:
            return Response({"error": "Main savings account not found. Please deposit funds first."}, status=status.HTTP_404_NOT_FOUND)
        except SavingsGoal.DoesNotExist:
            return Response({"error": "Goal not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- ACCESSIBILITY PREFERENCES VIEW ---
class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        return Response({
            "dyslexia_font": prefs.dyslexia_font,
            "simplified_numbers": prefs.simplified_numbers,
            "anxiety_mode": prefs.anxiety_mode,
            "high_contrast": prefs.high_contrast,
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        data = request.data
        if 'dyslexia_font' in data: prefs.dyslexia_font = data['dyslexia_font']
        if 'simplified_numbers' in data: prefs.simplified_numbers = data['simplified_numbers']
        if 'anxiety_mode' in data: prefs.anxiety_mode = data['anxiety_mode']
        if 'high_contrast' in data: prefs.high_contrast = data['high_contrast']
        prefs.save()
        return Response({"message": "Preferences updated successfully"}, status=status.HTTP_200_OK)


# --- CARD MANAGEMENT VIEWS (RESTORED FIXED BACKEND) ---
class CardsDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cards = BankCard.objects.filter(user=request.user)
        if not cards.exists():
            BankCard.objects.create(user=request.user, card_type='PHYSICAL', name_on_card="Horizon Inclusion", last_four="4821", expiry_date="08/26", current_spend=Decimal('124000.00'), monthly_limit=Decimal('500000.00'))
            BankCard.objects.create(user=request.user, card_type='VIRTUAL', name_on_card="Eco-Safe Digital", last_four="9904", expiry_date="04/28", current_spend=Decimal('0.00'), monthly_limit=Decimal('200000.00'))
            cards = BankCard.objects.filter(user=request.user)

        card_data = []
        total_limit = Decimal('0')
        total_spend = Decimal('0')

        for card in cards:
            total_limit += card.monthly_limit
            total_spend += card.current_spend
            card_data.append({
                "id": card.id,
                "type": card.card_type,
                "name": card.name_on_card,
                "last_four": card.last_four,
                "expiry": card.expiry_date,
                "cvc": card.cvc_dummy,
                "controls": {
                    "is_frozen": card.is_frozen,
                    "online_payments": card.online_payments,
                    "international_spend": card.international_spend,
                    "contactless": card.contactless
                }
            })

        return Response({
            "cards": card_data,
            "spending_power": {
                "spent": float(total_spend),
                "remaining": float(total_limit - total_spend),
                "percentage_used": int((total_spend / total_limit) * 100) if total_limit > 0 else 0,
                "days_until_reset": 12,
                "insight": "Your spending is 12% lower than last month. Great job focusing on what matters."
            }
        }, status=status.HTTP_200_OK)


class UpdateCardControlView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, card_id):
        try:
            card = BankCard.objects.get(id=card_id, user=request.user)
            data = request.data
            if 'is_frozen' in data: card.is_frozen = data['is_frozen']
            if 'online_payments' in data: card.online_payments = data['online_payments']
            if 'international_spend' in data: card.international_spend = data['international_spend']
            if 'contactless' in data: card.contactless = data['contactless']
            card.save()
            return Response({"message": "Card controls updated"}, status=status.HTTP_200_OK)
        except BankCard.DoesNotExist:
            return Response({"error": "Card not found"}, status=status.HTTP_404_NOT_FOUND)


# --- COMMUNITY LENDING VIEWS ---
class CommunityLendingDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_requests = FundingRequest.objects.filter(is_fully_funded=False).order_by('-created_at')[:10]
        request_data = []
        for req in active_requests:
            percentage = min(int((req.raised_amount / req.target_amount) * 100), 100) if req.target_amount > 0 else 0
            request_data.append({
                "id": req.id,
                "borrower_name": req.borrower.first_name or req.borrower.email.split('@')[0],
                "title": req.title,
                "description": req.description,
                "target_amount": float(req.target_amount),
                "raised_amount": float(req.raised_amount),
                "percentage": percentage
            })

        endorsements = Endorsement.objects.filter(endorsee=request.user).order_by('-date_vouched')[:5]
        endorsement_data = [{"endorser_name": e.endorser.first_name or e.endorser.email.split('@')[0], "date": e.date_vouched} for e in endorsements]
        total_pool = sum(float(r.target_amount) for r in active_requests)

        return Response({
            "global_trust_score": 98.4,
            "active_pool_volume": total_pool,
            "your_impact": {
                "peers_supported": 12,
                "repaid_loans": 9
            },
            "trust_network_count": endorsements.count(),
            "endorsements": endorsement_data,
            "funding_requests": request_data
        }, status=status.HTTP_200_OK)


class SupportFundingRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                main_account = SavingsAccount.objects.select_for_update().get(user=request.user)
                funding_req = FundingRequest.objects.select_for_update().get(id=request_id)
                borrower_account, _ = SavingsAccount.objects.get_or_create(user=funding_req.borrower)

                if main_account.balance < amount:
                    return Response({"error": "Insufficient funds in main account"}, status=status.HTTP_400_BAD_REQUEST)

                main_account.balance -= amount
                borrower_account.balance += amount
                funding_req.raised_amount += amount
                if funding_req.raised_amount >= funding_req.target_amount:
                    funding_req.is_fully_funded = True

                main_account.save()
                borrower_account.save()
                funding_req.save()

                Transaction.objects.create(user=request.user, amount=-amount, description=f"Supported Community Loan: {funding_req.title}")
                Transaction.objects.create(user=funding_req.borrower, amount=amount, description=f"Received Support from Pool")

            return Response({"message": f"Successfully supported {funding_req.title} with ₦{amount}!"}, status=status.HTTP_200_OK)

        except SavingsAccount.DoesNotExist:
            return Response({"error": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        except FundingRequest.DoesNotExist:
            return Response({"error": "Funding request not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- HORIZON ORACLE VIEWS ---
class OracleDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        account = SavingsAccount.objects.filter(user=request.user).first()
        balance = float(account.balance) if account else 0.0

        return Response({
            "vibe_check": {
                "status": "Steady & Growing",
                "description": "Your financial pulse is calm and regular.",
                "score": 85
            },
            "insights": [
                "You've been investing in your community more this month! Your money is staying close to home.",
                "Every small round-up is a seed. You've planted 42 'seeds' this week alone through micro-savings."
            ],
            "future_path": {
                "current_amount": balance,
                "forecast_percentage": "+14%",
                "chart_data": [balance * 0.8, balance * 0.9, balance, balance * 1.05, balance * 1.14]
            }
        }, status=status.HTTP_200_OK)


class OracleChatView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        messages = OracleMessage.objects.filter(user=request.user).order_by('timestamp')[:20]
        history = [{"sender": msg.sender, "text": msg.message, "time": msg.timestamp.strftime("%I:%M %p")} for msg in messages]
        return Response({"history": history}, status=status.HTTP_200_OK)

    def post(self, request):
        user_text = request.data.get('message')
        if not user_text:
            return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)

        OracleMessage.objects.create(user=request.user, sender='USER', message=user_text)

        account = SavingsAccount.objects.filter(user=request.user).first()
        balance = account.balance if account else 0
        goals = SavingsGoal.objects.filter(user=request.user)
        goals_text = ", ".join([f"{g.name} (Target: ₦{g.target_amount})" for g in goals])

        system_prompt = f"""
        You are the 'Horizon Oracle', a highly empathetic, calming, and intelligent financial guide built into a Nigerian banking app.
        Your tone is reassuring, wise, and community-focused. You use standard English formatting.

        CONTEXT FOR THIS USER:
        Name: {request.user.first_name or 'Friend'}
        Current Savings Balance: ₦{balance}
        Active Goals: {goals_text if goals_text else 'None currently'}

        Respond directly to the user's prompt below. Keep it concise (2-3 short paragraphs max). Do not use asterisks or markdown bolding, just plain conversational text.
        """

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=system_prompt + "\n\nUser says: " + user_text,
            )
            oracle_reply = response.text.replace('*', '')

            OracleMessage.objects.create(user=request.user, sender='ORACLE', message=oracle_reply)

            return Response({
                "sender": "ORACLE",
                "text": oracle_reply
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print("🚨 ORACLE CRASH:", str(e))
            return Response({"error": f"Oracle is currently meditating. Details: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- ORACLE PROCEDURE TRANSACTION ENDPOINTS (PART 5 & 6) ---

class DepositView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        account_no = request.data.get('account_no')

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        # Optional: capture staff id if a teller processed it, else default to Null
        staff_id = request.data.get('staff_id', None)

        try:
            # Safely hand execution directly to your PL/SQL procedure
            with connection.cursor() as cursor:
                cursor.callproc('proc_deposit', [account_no, amount, staff_id])

            return Response({
                "message": f"Successfully deposited ₦{amount} into account {account_no}."
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Oracle Transaction Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class WithdrawalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        account_no = request.data.get('account_no')

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        staff_id = request.data.get('staff_id', None)

        try:
            with connection.cursor() as cursor:
                cursor.callproc('proc_withdrawal', [account_no, amount, staff_id])

            return Response({
                "message": f"Successfully withdrew ₦{amount} from account {account_no}."
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Oracle Transaction Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class ProcedureTransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        source_acc = request.data.get('source_account')
        dest_acc = request.data.get('destination_account')

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
        except InvalidOperation:
            return Response({"error": "Invalid amount format"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "Amount must be greater than zero"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Triggers your ACID-compliant database logic (limits, balance validation, audit log trigger)
            with connection.cursor() as cursor:
                cursor.callproc('proc_fund_transfer', [source_acc, dest_acc, amount])

            return Response({
                "message": f"Transfer of ₦{amount} completed successfully."
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Oracle Transfer Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
