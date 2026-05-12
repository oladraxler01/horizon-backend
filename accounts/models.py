from django.db import models
from django.conf import settings

class Account(models.Model):
    # Inheritance: Shared fields for all account types
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account_number = models.CharField(max_length=12, unique=True)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True # This tells Django not to create a table for 'Account'

    def deposit(self, amount): # Encapsulation: Logic stays within the object
        if amount > 0:
            self.balance += amount
            self.save()
            return True
        return False

class SavingsAccount(Account):
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=3.50)

class CurrentAccount(Account):
    overdraft_limit = models.DecimalField(max_digits=15, decimal_places=2, default=1000.00)
