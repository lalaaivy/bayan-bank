from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

from .security import decrypt, encrypt, sha256


class Client(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending Verification"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        INACTIVE = "inactive", "Inactive"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="client_profile",
    )

    id_number_encrypted = models.BinaryField()
    id_number_hash = models.CharField(
        max_length=64, unique=True, db_index=True
    )

    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Additional client information
    sex = models.CharField(max_length=20, blank=True)
    civil_status = models.CharField(max_length=30, blank=True)
    nationality = models.CharField(max_length=50, blank=True)

    employment_status = models.CharField(max_length=50, blank=True)
    source_of_income = models.CharField(max_length=100, blank=True)
    monthly_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    credit_score = models.PositiveIntegerField(default=0)

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_clients",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def client_code(self):
        """Client ID shown to users, e.g. CLT-000124."""
        return f"CLT-{self.pk:06d}" if self.pk else ""

    def set_id_number(self, value):
        self.id_number_encrypted = encrypt(value)
        self.id_number_hash = sha256(value)

    def get_id_number(self):
        return decrypt(self.id_number_encrypted)

    @classmethod
    def find_by_id_number(cls, value):
        return cls.objects.filter(
            id_number_hash=sha256(value)
        ).first()


def private_storage():
    """ID images are stored outside the public folders."""
    return FileSystemStorage(location=settings.BASE_DIR / "private_uploads")


class ClientDocument(models.Model):
    class IdType(models.TextChoices):
        PASSPORT = "passport", "Passport"
        DRIVERS = "drivers_license", "Driver's License"
        UMID = "umid", "UMID"
        PHILSYS = "philsys", "PhilSys ID"
        VOTERS = "voters", "Voter's ID"
        OTHER = "other", "Other valid ID"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="documents"
    )
    id_type = models.CharField(max_length=30, choices=IdType.choices)
    front_image = models.FileField(storage=private_storage, upload_to="ids/%Y/%m/")
    back_image = models.FileField(
        storage=private_storage, upload_to="ids/%Y/%m/", blank=True
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    remark = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client.client_code} - {self.get_id_type_display()}"