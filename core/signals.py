from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction  # Crucial for banking safety
from .models import Transaction
from accounts.models import SavingsAccount, CurrentAccount

@receiver(post_save, sender=Transaction)
def update_account_balance(sender, instance, created, **kwargs):
    if created:
        # We wrap this in a 'transaction.atomic' block.
        # If any part fails, Oracle will undo all changes in this block.
        with transaction.atomic():
            # 1. Identify the sender's account
            sender_savings = SavingsAccount.objects.filter(user=instance.user).first()
            sender_current = CurrentAccount.objects.filter(user=instance.user).first()
            sender_account = sender_savings or sender_current

            if not sender_account:
                return # No account found for this user

            # 2. Logic for DEPOSIT
            if instance.transaction_type == 'DEPOSIT':
                sender_account.balance += instance.amount
                sender_account.save()

            # 3. Logic for WITHDRAWAL
            elif instance.transaction_type == 'WITHDRAWAL':
                if sender_account.balance >= instance.amount:
                    sender_account.balance -= instance.amount
                    sender_account.save()
                else:
                    raise ValueError("Insufficient funds for withdrawal.")

            # 4. Logic for TRANSFER
            elif instance.transaction_type == 'TRANSFER':
                # Find the recipient by their account number
                rec_savings = SavingsAccount.objects.filter(account_number=instance.recipient_account_number).first()
                rec_current = CurrentAccount.objects.filter(account_number=instance.recipient_account_number).first()
                recipient_account = rec_savings or rec_current

                if recipient_account and sender_account.balance >= instance.amount:
                    # Subtract from sender, add to receiver
                    sender_account.balance -= instance.amount
                    recipient_account.balance += instance.amount

                    sender_account.save()
                    recipient_account.save()
                else:
                    raise ValueError("Transfer failed: Invalid recipient or insufficient funds.")
