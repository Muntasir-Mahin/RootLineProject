from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from orders.models import Order
from .forms import PaymentForm
from .models import Payment


@login_required
def make_payment_view(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        buyer=request.user
    )

    payment = get_object_or_404(
        Payment,
        order=order
    )

    # Already verified payment hole abar payment submit kora jabe na
    if payment.payment_status == 'paid':
        return redirect('my_orders')

    # Verification already pending hole abar submit kora jabe na
    if payment.payment_status == 'verification_pending':
        return redirect('my_orders')

    # Cancelled order-e payment kora jabe na
    if order.status == 'cancelled':
        return redirect('my_orders')

    if request.method == 'POST':
        form = PaymentForm(request.POST)

        if form.is_valid():

            payment.transaction_id = form.cleaned_data['transaction_id']

            # IMPORTANT:
            # Buyer submit korlei Paid na
            payment.payment_status = 'verification_pending'
            payment.escrow_status = 'not_held'
            payment.paid_at = None

            payment.save(
                update_fields=[
                    'transaction_id',
                    'payment_status',
                    'escrow_status',
                    'paid_at',
                ]
            )

            return redirect('my_orders')

    else:
        form = PaymentForm()

    return render(
        request,
        'payments/make_payment.html',
        {
            'form': form,
            'order': order,
            'payment': payment,
        }
    )