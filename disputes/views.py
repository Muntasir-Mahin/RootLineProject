from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from dashboard.audit import DecisionError
from orders.models import Order
from .forms import DisputeForm, SellerResponseForm
from .models import Dispute
from .services import FINAL_DISPUTE_STATUSES, raise_dispute, respond_to_dispute


@login_required
@require_http_methods(['GET', 'POST'])
def raise_dispute_view(request, order_id):
    order = get_object_or_404(Order, pk=order_id, buyer=request.user)
    if order.status != 'shipped' or hasattr(order, 'dispute'):
        return redirect('my_orders')
    if not hasattr(order, 'payment') or order.payment.payment_status != 'paid' or order.payment.escrow_status != 'held':
        return redirect('my_orders')
    form = DisputeForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            raise_dispute(order_id, actor=request.user, **form.cleaned_data)
        except DecisionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Your dispute has been sent to Support.')
        return redirect('my_orders')
    return render(request, 'disputes/raise_dispute.html', {'form': form, 'order': order})


@login_required
@require_http_methods(['GET', 'POST'])
def seller_dispute_response_view(request, dispute_id):
    if not request.user.seller_approved:
        return redirect('profile')
    dispute = get_object_or_404(Dispute.objects.select_related('order', 'order__buyer', 'order__seller'),
                                pk=dispute_id, order__seller=request.user)
    if dispute.status in FINAL_DISPUTE_STATUSES:
        return redirect('seller_orders')
    form = SellerResponseForm(request.POST if request.method == 'POST' else None, instance=dispute)
    if request.method == 'POST' and form.is_valid():
        try:
            respond_to_dispute(dispute_id, actor=request.user, response=form.cleaned_data['seller_response'])
        except DecisionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Response saved.')
        return redirect('seller_orders')
    return render(request, 'disputes/seller_response.html', {'form': form, 'dispute': dispute})
