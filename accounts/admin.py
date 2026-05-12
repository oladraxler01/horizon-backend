from django.contrib import admin
from .models import SavingsAccount, CurrentAccount

admin.site.register(SavingsAccount)
admin.site.register(CurrentAccount)
