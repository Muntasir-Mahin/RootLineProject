from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from orders.models import Order

from .forms import DisputeForm, SellerResponseForm
from .models import Dispute


# --------------------------------------------------
# BUYER - RAISE DISPUTE
# --------------------------------------------------

@login_required
def raise_dispute_view(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        buyer=request.user
    )

    # Shipped order chara dispute allow korbo na
    if order.status != 'shipped':
        return redirect('my_orders')

    # Payment paid + escrow held hote hobe
    if (
        not hasattr(order, 'payment')
        or order.payment.payment_status != 'paid'
        or order.payment.escrow_status != 'held'
    ):
        return redirect('my_orders')

    # Same order-er against-e second dispute na
    if hasattr(order, 'dispute'):
        return redirect('my_orders')

    if request.method == 'POST':

        form = DisputeForm(request.POST)

        if form.is_valid():

            dispute = form.save(commit=False)

            dispute.order = order
            dispute.raised_by = request.user

            dispute.save()

            return redirect('my_orders')

    else:
        form = DisputeForm()

    return render(
        request,
        'disputes/raise_dispute.html',
        {
            'form': form,
            'order': order,
        }
    )


# --------------------------------------------------
# SELLER - RESPOND TO DISPUTE
# --------------------------------------------------

@login_required
def seller_dispute_response_view(request, dispute_id):

    if not request.user.seller_approved:
        return redirect('profile')

    dispute = get_object_or_404(
        Dispute.objects.select_related(
            'order',
            'order__buyer',
            'order__seller'
        ),
        id=dispute_id,
        order__seller=request.user
    )

    # Final decision hoye gele seller response edit korte parbe na
    if dispute.status in [
        'refund_approved',
        'seller_favored',
        'rejected',
    ]:
        return redirect('seller_orders')

    if request.method == 'POST':

        form = SellerResponseForm(
            request.POST,
            instance=dispute
        )

        if form.is_valid():

            dispute = form.save(commit=False)

            # Open dispute-e seller response dile status change
            if dispute.status == 'open':
                dispute.status = 'seller_responded'

            dispute.save()

            return redirect('seller_orders')

    else:

        form = SellerResponseForm(
            instance=dispute
        )

    return render(
        request,
        'disputes/seller_response.html',
        {
            'form': form,
            'dispute': dispute,
        }
    )