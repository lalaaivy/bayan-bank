from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import Q

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
        max_length=64,
        unique=True,
        db_index=True,
    )

    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

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
    return FileSystemStorage(
        location=settings.BASE_DIR / "private_uploads"
    )


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
        Client,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    id_type = models.CharField(
        max_length=30,
        choices=IdType.choices,
    )
    front_image = models.FileField(
        storage=private_storage,
        upload_to="ids/%Y/%m/",
    )
    back_image = models.FileField(
        storage=private_storage,
        upload_to="ids/%Y/%m/",
        blank=True,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
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
        return (
            f"{self.client.client_code} - "
            f"{self.get_id_type_display()}"
        )


class SecurityFreeze(models.Model):
    """
    Records a client-wide security freeze.

    Minor freezes have an expiry time.
    Serious freezes remain active until manually released.
    """

    class Severity(models.TextChoices):
        MINOR = "minor", "Minor Suspicion"
        SERIOUS = "serious", "Serious Suspicion"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Manually Released"
        EXPIRED = "expired", "Automatically Expired"

    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="security_freezes",
    )

    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    reason = models.TextField()

    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    frozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_security_freezes",
    )

    unfrozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="released_security_freezes",
    )

    branch_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    staff_notes = models.TextField(blank=True)

    bank_accounts = models.ManyToManyField(
        "accounting.BankAccount",
        through="SecurityFreezeBankAccount",
        related_name="security_freezes",
        blank=True,
    )

    savings_accounts = models.ManyToManyField(
        "savings.SavingsAccount",
        through="SecurityFreezeSavingsAccount",
        related_name="security_freezes",
        blank=True,
    )

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(
                fields=["client", "status"],
                name="client_freeze_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.client.client_code} - "
            f"{self.get_severity_display()} - "
            f"{self.get_status_display()}"
        )


class SecurityFreezeBankAccount(models.Model):
    """
    Records which regular bank accounts were affected by a freeze.

    changed_status is True only when this freeze changed the
    account from ACTIVE to FROZEN.
    """

    security_freeze = models.ForeignKey(
        SecurityFreeze,
        on_delete=models.PROTECT,
        related_name="bank_account_records",
    )

    bank_account = models.ForeignKey(
        "accounting.BankAccount",
        on_delete=models.PROTECT,
        related_name="security_freeze_records",
    )

    changed_status = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["security_freeze", "bank_account"],
                name="unique_freeze_bank_account",
            ),
        ]

    def __str__(self):
        return (
            f"Freeze #{self.security_freeze_id} - "
            f"Bank Account #{self.bank_account_id}"
        )


class SecurityFreezeSavingsAccount(models.Model):
    """
    Records which savings accounts were affected by a freeze.
    """

    security_freeze = models.ForeignKey(
        SecurityFreeze,
        on_delete=models.PROTECT,
        related_name="savings_account_records",
    )

    savings_account = models.ForeignKey(
        "savings.SavingsAccount",
        on_delete=models.PROTECT,
        related_name="security_freeze_records",
    )

    changed_status = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["security_freeze", "savings_account"],
                name="unique_freeze_savings_account",
            ),
        ]

    def __str__(self):
        return (
            f"Freeze #{self.security_freeze_id} - "
            f"Savings Account #{self.savings_account_id}"
        )


class ReactivationRequest(models.Model):
    """
    Publicly submitted request to reactivate a deactivated client.

    Submitting a request does not reactivate the client.
    An authorized reviewer must verify the client's identity.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="reactivation_requests",
    )

    reason = models.TextField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_reactivation_requests",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    staff_notes = models.TextField(blank=True)

    branch_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    class Meta:
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(
                fields=["status", "-requested_at"],
                name="reactivation_status_date_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["client"],
                condition=Q(status="pending"),
                name="one_pending_reactivation_per_client",
            ),
        ]

    def __str__(self):
        return (
            f"{self.client.client_code} - "
            f"{self.get_status_display()}"
        )