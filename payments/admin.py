from django.contrib import admin

from dashboard.admin import ReadOnlyRecordsAdmin, ServiceActionMixin
from .models import Payment
from .services import fail_payment, verify_payment


@admin.register(Payment)
class PaymentAdmin(ServiceActionMixin, ReadOnlyRecordsAdmin):
    list_display = ('id', 'order', 'amount', 'transaction_id', 'payment_status', 'escrow_status', 'created_at')
    list_filter = ('payment_status', 'escrow_status')
    search_fields = ('transaction_id', 'order__buyer__username', 'order__seller__username')
    actions = ('verify_payment', 'mark_payment_failed')

    @admin.action(description='Verify selected payments (confirm after checking transaction IDs)')
    def verify_payment(self, request, queryset):
        self.run_service(request, queryset, verify_payment)

    @admin.action(description='Fail selected payments')
    def mark_payment_failed(self, request, queryset):
        self.run_service(request, queryset, fail_payment)
