from django.contrib.auth import get_user_model

User = get_user_model()
Role = User._meta.get_field("role").related_model

accounts = [
    ("client_test", "client"),
    ("staff_test", "staff"),
    ("officer_test", "loan_officer"),
    ("admin_test", "admin"),
]

for username, rolename in accounts:
    role, _ = Role.objects.get_or_create(name=rolename)
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    user.role = role
    user.set_password("test1234")
    if rolename == "admin":
        user.is_staff = True
        user.is_superuser = True
    user.save()
    print("ready:", username, "->", rolename)
