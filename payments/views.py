from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from dashboard.audit import DecisionError
from orders.models import Order
from .forms import PaymentForm
from .models import Payment
from .services import submit_transaction


@login_required
@require_http_methods(['GET', 'POST'])
def make_payment_view(request, order_id):
    order = get_object_or_404(Order, pk=order_id, buyer=request.user)
    payment = get_object_or_404(Payment, order=order)
    if order.status in ('cancelled', 'delivered') or payment.payment_status not in ('pending', 'failed'):
        return redirect('my_orders')
    form = PaymentForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            submit_transaction(order_id, actor=request.user, transaction_id=form.cleaned_data['transaction_id'])
        except DecisionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Transaction submitted for verification.')
        return redirect('my_orders')
    return render(request, 'payments/make_payment.html', {'form': form, 'order': order, 'payment': payment})
