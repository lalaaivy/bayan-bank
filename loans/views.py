from django.shortcuts import render
from accounts.decorators import role_required

@role_required("client")
def my_loans(request):
    return render(request, "portal/loans.html")