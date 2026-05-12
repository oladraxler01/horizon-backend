from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings



class User(AbstractUser):
    # Encapsulation: Customizing the identity fields
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_verified = models.BooleanField(default=False) # For professional KYC

    # Using email as the primary login identifier
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('TRANSFER', 'Transfer'),
    )

    # Linking the transaction to the user and the account
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    description = models.TextField(blank=True, null=True)
    recipient_account_number = models.CharField(max_length=12, blank=True, null=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"

class CreditProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credit_profile')
    horizon_score = models.IntegerField(default=600)
    rent_verified = models.BooleanField(default=True)
    phone_bill_verified = models.BooleanField(default=True)
    streaming_verified = models.BooleanField(default=False)
    community_endorsements = models.IntegerField(default=12)

class CreditActivity(models.Model):
    profile = models.ForeignKey(CreditProfile, on_delete=models.CASCADE, related_name='activities')
    source = models.CharField(max_length=100)
    date = models.DateField()
    status = models.CharField(max_length=20, default='VERIFIED')
    impact = models.IntegerField()


class CreditProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    base_score = models.IntegerField(default=600)
    rent_verified = models.BooleanField(default=False)
    phone_bill_verified = models.BooleanField(default=False)
    streaming_verified = models.BooleanField(default=False)
    community_endorsements = models.IntegerField(default=0)

    # @property
    # def horizon_score(self):
    #     # Professional logic: Verifications add points to a base score
    #     score = self.base_score
    #     if self.rent_verified: score += 50
    #     if self.phone_bill_verified: score += 30
    #     if self.streaming_verified: score += 20
    #     score += (self.community_endorsements * 5)
    #     return min(score, 850) # Cap at 850 like real credit scores


# 1. Parent Model MUST come first
class CreditProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # ... fields ...

# 2. Child Model comes second
class CreditActivity(models.Model):
        # To this:
        profile = models.ForeignKey(CreditProfile, on_delete=models.CASCADE, related_name='activities')



# Add this at the bottom of core/models.py
class SavingsGoal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='savings_goals')
    name = models.CharField(max_length=100) # e.g., "Emergency Fund"
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.name}"




class UserPreferences(models.Model):
    # OneToOneField ensures each user only has exactly ONE settings profile
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='preferences')

    # The 4 toggles from your design
    dyslexia_font = models.BooleanField(default=False)
    simplified_numbers = models.BooleanField(default=False)
    anxiety_mode = models.BooleanField(default=False)
    high_contrast = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email} - Preferences"


