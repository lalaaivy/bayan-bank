
from django.contrib import admin

from .models import Installment, Loan, LoanDocument, LoanProduct

admin.site.register(LoanProduct)
admin.site.register(Loan)
admin.site.register(Installment)
admin.site.register(LoanDocument)
