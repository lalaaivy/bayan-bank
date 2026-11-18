from django.conf import settings
from django.db import models

from .security import decrypt, encrypt, sha256


class Client(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="client_profile"
    )
    id_number_encrypted = models.BinaryField()
    id_number_hash = models.CharField(max_length=64, unique=True, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def set_id_number(self, value):
        self.id_number_encrypted = encrypt(value)
        self.id_number_hash = sha256(value)

    def get_id_number(self):
        return decrypt(self.id_number_encrypted)

    @classmethod
    def find_by_id_number(cls, value):
        return cls.objects.filter(id_number_hash=sha256(value)).first()