from django.contrib import admin

from dashboard.admin import ReadOnlyRecordsAdmin, ServiceActionMixin
from .models import Dispute
from .services import decide_dispute


@admin.register(Dispute)
class DisputeAdmin(ServiceActionMixin, ReadOnlyRecordsAdmin):
    list_display = ('id', 'order', 'raised_by', 'reason', 'status', 'created_at', 'resolved_by', 'resolved_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('order__id', 'raised_by__username', 'description')
    actions = ('under_review', 'refund_buyer', 'favour_seller', 'reject_dispute')

    @admin.action(description='Mark under review')
    def under_review(self, request, queryset):
        self.run_service(request, queryset, decide_dispute, decision='under_review')

    @admin.action(description='Refund buyer and cancel order')
    def refund_buyer(self, request, queryset):
        self.run_service(request, queryset, decide_dispute, decision='refund_approved')

    @admin.action(description='Favour seller and release escrow')
    def favour_seller(self, request, queryset):
        self.run_service(request, queryset, decide_dispute, decision='seller_favored')

    @admin.action(description='Reject dispute and release escrow')
    def reject_dispute(self, request, queryset):
        self.run_service(request, queryset, decide_dispute, decision='rejected')
