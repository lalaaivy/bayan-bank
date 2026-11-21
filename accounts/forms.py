
import os
import re
from datetime import date

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from audit.services import log
from clients.models import Client, ClientDocument

from .models import Role, User


PHONE_RE = re.compile(r"^(09\d{9}|\+639\d{9})$")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_IMAGE_SIZE_MB = 5

EMPLOYEE_ROLES = (
    Role.ADMIN,
    Role.STAFF,
    Role.LOAN_OFFICER,
)


class RegisterForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"})
    )
    sex = forms.ChoiceField(
        choices=[("Male", "Male"), ("Female", "Female")]
    )
    civil_status = forms.ChoiceField(choices=[
        ("Single", "Single"),
        ("Married", "Married"),
        ("Widowed", "Widowed"),
        ("Separated", "Separated"),
    ])
    nationality = forms.CharField(max_length=50, initial="Filipino")
    phone = forms.CharField(max_length=30, label="Mobile number")
    address = forms.CharField(max_length=255)

    employment_status = forms.ChoiceField(choices=[
        ("Employed", "Employed"),
        ("Self-employed", "Self-employed"),
        ("Unemployed", "Unemployed"),
        ("Student", "Student"),
    ])
    source_of_income = forms.CharField(max_length=100)
    monthly_income = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )
    id_number = forms.CharField(
        max_length=60,
        label="Valid ID number",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        today = date.today()
        age = today.year - dob.year - (
            (today.month, today.day) < (dob.month, dob.day)
        )
        if age < 18:
            raise forms.ValidationError(
                "You must be 18 or older to register."
            )
        return dob

    def clean_phone(self):
        phone = (
            self.cleaned_data["phone"]
            .replace(" ", "")
            .replace("-", "")
        )
        if not PHONE_RE.match(phone):
            raise forms.ValidationError(
                "Use a PH mobile number like 09171234567."
            )
        return phone

    def clean_id_number(self):
        value = self.cleaned_data["id_number"].strip()
        if Client.find_by_id_number(value):
            raise forms.ValidationError(
                "This ID number is already registered."
            )
        return value

    def clean(self):
        data = super().clean()
        password = data.get("password")

        if password:
            if password != data.get("confirm_password"):
                self.add_error(
                    "confirm_password",
                    "Passwords do not match.",
                )
            else:
                try:
                    validate_password(password)
                except forms.ValidationError as error:
                    self.add_error("password", error)

        return data

    @transaction.atomic
    def save(self):
        data = self.cleaned_data

        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=Role.objects.get(name=Role.CLIENT),
        )

        client = Client(
            user=user,
            phone=data["phone"],
            address=data["address"],
            date_of_birth=data["date_of_birth"],
            sex=data["sex"],
            civil_status=data["civil_status"],
            nationality=data["nationality"],
            employment_status=data["employment_status"],
            source_of_income=data["source_of_income"],
            monthly_income=data["monthly_income"],
        )
        client.set_id_number(data["id_number"])
        client.save()

        log(user, "register", client)
        return client


class EmployeeUserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Password",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirm password",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.filter(
            name__in=EMPLOYEE_ROLES
        ).order_by("name")

        for field in self.fields.values():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean(self):
        data = super().clean()
        password = data.get("password")

        if password:
            if password != data.get("confirm_password"):
                self.add_error(
                    "confirm_password",
                    "Passwords do not match.",
                )
            else:
                try:
                    validate_password(password)
                except forms.ValidationError as error:
                    self.add_error("password", error)

        return data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])

        if commit:
            user.save()

        return user


class EmployeeUserEditForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label="New password",
        help_text="Leave blank to keep the current password.",
    )
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label="Confirm new password",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.filter(
            name__in=EMPLOYEE_ROLES
        ).order_by("name")

        for field in self.fields.values():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        existing = User.objects.filter(
            username__iexact=username
        ).exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError("This username is already taken.")

        return username

    def clean(self):
        data = super().clean()
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if password or confirm_password:
            if password != confirm_password:
                self.add_error(
                    "confirm_password",
                    "Passwords do not match.",
                )
            elif password:
                try:
                    validate_password(password, self.instance)
                except forms.ValidationError as error:
                    self.add_error("password", error)

        return data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")

        if password:
            user.set_password(password)

        if commit:
            user.save()

        return user


class ClientDocumentForm(forms.ModelForm):
    """Form for the client's ID upload (front image required, back optional)."""

    class Meta:
        model = ClientDocument
        fields = ["id_type", "front_image", "back_image"]
        widgets = {
            "front_image": forms.FileInput(
                attrs={"accept": ".jpg,.jpeg,.png"}
            ),
            "back_image": forms.FileInput(
                attrs={"accept": ".jpg,.jpeg,.png"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css)

    def _check_image(self, uploaded):
        extension = os.path.splitext(uploaded.name)[1].lower()

        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise forms.ValidationError(
                "Only JPG or PNG images are allowed."
            )

        if uploaded.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"File is too large. Maximum size is {MAX_IMAGE_SIZE_MB} MB."
            )

        return uploaded

    def clean_front_image(self):
        uploaded = self.cleaned_data["front_image"]
        return self._check_image(uploaded)

    def clean_back_image(self):
        uploaded = self.cleaned_data.get("back_image")
        if uploaded:
            return self._check_image(uploaded)
        return uploaded
