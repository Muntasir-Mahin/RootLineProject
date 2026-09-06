from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from orders.forms import CheckoutForm
from orders.models import Order, OrderItem
from payments.models import Payment
from products.models import Product

from .forms import AuctionForm, BidForm
from .models import Auction, Bid
from .services import finalize_auction
@login_required
def create_auction_view(request, product_id):

    if not request.user.seller_approved:
        return redirect('profile')

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    # Fixed-price only product-er auction create kora jabe na
    if product.selling_type not in ['bidding', 'both']:
        return redirect('my_products')

    # Ei product-er auction already thakle abar create kora jabe na
    if Auction.objects.filter(product=product).exists():
        return redirect('my_products')

    if request.method == 'POST':

        form = AuctionForm(request.POST)

        if form.is_valid():

            auction = form.save(commit=False)

            auction.product = product

            # Start time onujayi initial status
            if auction.start_time <= timezone.now():
                auction.status = 'active'
            else:
                auction.status = 'upcoming'

            auction.save()

            return redirect('my_products')

    else:
        form = AuctionForm()

    return render(
        request,
        'bidding/create_auction.html',
        {
            'form': form,
            'product': product,
        }
    )

def auction_list_view(request):

    now = timezone.now()

    auctions = Auction.objects.filter(
        product__verification_status='verified',
        product__is_available=True,
        product__selling_type__in=['bidding', 'both'],
        start_time__lte=now,
        end_time__gt=now,
    ).select_related(
        'product',
        'product__seller'
    ).order_by('end_time')

    # Active time hole status update
    auctions.filter(status='upcoming').update(status='active')

    return render(
        request,
        'bidding/auction_list.html',
        {
            'auctions': auctions
        }
    )


def auction_detail_view(request, auction_id):

    auction = get_object_or_404(
        Auction.objects.select_related(
            'product',
            'product__seller',
            'winner',
            'order',
        ),
        id=auction_id
    )

    now = timezone.now()

    # Auction start hole active
    if (
        auction.status == 'upcoming'
        and auction.start_time <= now < auction.end_time
    ):
        auction.status = 'active'
        auction.save(update_fields=['status'])

    # Auction end hole winner select
    auction = finalize_auction(auction)

    highest_bid = auction.bids.select_related(
        'bidder'
    ).order_by(
        '-amount',
        'created_at'
    ).first()

    if highest_bid:
        minimum_bid = (
            highest_bid.amount
            + auction.minimum_increment
        )
    else:
        minimum_bid = auction.starting_price

    return render(
        request,
        'bidding/auction_detail.html',
        {
            'auction': auction,
            'highest_bid': highest_bid,
            'minimum_bid': minimum_bid,
        }
    )

@login_required
def place_bid_view(request, auction_id):

    if request.method != 'POST':
        return redirect(
            'auction_detail',
            auction_id=auction_id
        )

    with transaction.atomic():

        auction = get_object_or_404(
            Auction.objects.select_for_update().select_related(
                'product',
                'product__seller'
            ),
            id=auction_id
        )

        now = timezone.now()

        # Auction running kina
        if not (
            auction.start_time <= now < auction.end_time
        ):
            return redirect(
                'auction_detail',
                auction_id=auction.id
            )

        if auction.status not in ['active', 'upcoming']:
            return redirect(
                'auction_detail',
                auction_id=auction.id
            )

        # Seller nijer product-e bid korte parbe na
        if auction.product.seller == request.user:
            return redirect(
                'auction_detail',
                auction_id=auction.id
            )

        form = BidForm(
            request.POST,
            auction=auction
        )

        if form.is_valid():

            bid = form.save(commit=False)
            bid.auction = auction
            bid.bidder = request.user
            bid.save()

            if auction.status == 'upcoming':
                auction.status = 'active'
                auction.save(update_fields=['status'])

    return redirect(
        'auction_detail',
        auction_id=auction_id
    )

@login_required
def edit_auction_view(request, auction_id):

    if not request.user.seller_approved:
        return redirect('profile')

    auction = get_object_or_404(
        Auction,
        id=auction_id,
        product__seller=request.user
    )

    # Auction start hoye gele edit kora jabe na
    if timezone.now() >= auction.start_time:
        return redirect('my_products')

    # Bid already thakleo edit kora jabe na
    if auction.bids.exists():
        return redirect('my_products')

    if request.method == 'POST':

        form = AuctionForm(
            request.POST,
            instance=auction
        )

        if form.is_valid():

            auction = form.save(commit=False)

            if auction.start_time <= timezone.now():
                auction.status = 'active'
            else:
                auction.status = 'upcoming'

            auction.save()

            return redirect('my_products')

    else:
        form = AuctionForm(instance=auction)

    return render(
        request,
        'bidding/edit_auction.html',
        {
            'form': form,
            'auction': auction,
        }
    )

@login_required
def auction_winner_checkout_view(request, auction_id):

    auction = get_object_or_404(
        Auction.objects.select_related(
            'product',
            'product__seller',
            'winner',
            'order',
        ),
        id=auction_id
    )

    auction = finalize_auction(auction)

    # Auction sesh na hole checkout na
    if auction.status != 'ended':
        return redirect(
            'auction_detail',
            auction_id=auction.id
        )

    # Sudhu winner checkout korte parbe
    if auction.winner != request.user:
        return redirect(
            'auction_detail',
            auction_id=auction.id
        )

    # No winning bid
    if auction.winning_bid is None:
        return redirect(
            'auction_detail',
            auction_id=auction.id
        )

    # Already order create hoye gele
    if auction.order:
        return redirect('my_orders')

    product = auction.product

    initial_data = {
        'recipient_name':
            request.user.get_full_name()
            or request.user.username,

        'email': request.user.email,

        'phone_number':
            request.user.phone_number,

        'delivery_address':
            request.user.address,
    }

    if request.method == 'POST':

        form = CheckoutForm(request.POST)

        if form.is_valid():

            with transaction.atomic():

                auction = Auction.objects.select_for_update().get(
                    id=auction.id
                )

                # Duplicate order protection
                if auction.order_id:
                    return redirect('my_orders')

                product = Product.objects.select_for_update().get(
                    id=auction.product_id
                )

                quantity = Decimal('1.00')

                # Stock check
                if (
                    not product.is_available
                    or product.stock_quantity < quantity
                ):
                    return redirect(
                        'auction_detail',
                        auction_id=auction.id
                    )

                order = Order.objects.create(
                    buyer=request.user,
                    seller=product.seller,

                    recipient_name=
                        form.cleaned_data['recipient_name'],

                    email=
                        form.cleaned_data['email'],

                    phone_number=
                        form.cleaned_data['phone_number'],

                    delivery_address=
                        form.cleaned_data['delivery_address'],

                    payment_method=
                        form.cleaned_data['payment_method'],

                    total_amount=auction.winning_bid,
                    status='pending'
                )

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    price=auction.winning_bid,
                    quantity=quantity,
                    unit=product.unit
                )

                Payment.objects.create(
                    order=order,
                    amount=auction.winning_bid,
                    payment_status='pending',
                    escrow_status='not_held'
                )

                # Reduce stock
                product.stock_quantity -= quantity

                if product.stock_quantity <= 0:
                    product.stock_quantity = 0
                    product.is_available = False

                product.save(
                    update_fields=[
                        'stock_quantity',
                        'is_available'
                    ]
                )

                # Auction-er sathe order link
                auction.order = order
                auction.save(
                    update_fields=['order']
                )

            return redirect('my_orders')

    else:
        form = CheckoutForm(
            initial=initial_data
        )

    return render(
        request,
        'bidding/winner_checkout.html',
        {
            'auction': auction,
            'product': product,
            'form': form,
        }
    )