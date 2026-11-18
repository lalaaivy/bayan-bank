from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.Model):
    ADMIN = "admin"
    LOAN_OFFICER = "loan_officer"
    STAFF = "staff"
    CLIENT = "client"
    NAMES = [ADMIN, LOAN_OFFICER, STAFF, CLIENT]

    name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name


class BankUserManager(UserManager):
    """Superusers created from the command line get the admin role automatically,
    because User.role is required and createsuperuser does not ask for it."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        if "role" not in extra_fields and "role_id" not in extra_fields:
            extra_fields["role"], _ = Role.objects.get_or_create(name=Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    objects = BankUserManager()