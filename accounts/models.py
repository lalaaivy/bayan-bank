from django.contrib.auth.models import AbstractUser
from django.db import models

class Role(models.Model):
    name = models.CharField(max_length=30, unique=True)

class User(AbstractUser):
    role = models.ForeignKey(Role, on_delete=models.PROTECT)