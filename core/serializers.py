from rest_framework import serializers
from .models import User, Transaction
from accounts.models import SavingsAccount, CurrentAccount

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone_number', 'password']
        extra_kwargs = {
            'password': {'write_only': True} # Prevents password from being leaked in JSON
        }

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class AccountSummarySerializer(serializers.Serializer):
    # This is a custom serializer to show a "Dashboard" view
    account_number = serializers.CharField()
    balance = serializers.DecimalField(max_digits=15, decimal_places=2)
    account_type = serializers.CharField()
