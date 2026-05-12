from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User,Transaction

# Using UserAdmin ensures the password hashing and fields look professional
admin.site.register(User, UserAdmin)
admin.site.register(Transaction)
