from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bidding.models import Auction, Bid
from bidding.services import finalize_auction
from payments.models import Payment
from products.models import Product
from reviews.models import Review
from wishlist.models import Wishlist
from .models import Cart, CartItem, Order
from .services import CheckoutUnavailable, checkout_cart, deduct_stock


class IntegrityFixtures:
    def setUp(self):
        super().setUp()
        self.seller = User.objects.create_user('integrity-seller', seller_approved=True)
        self.buyer = User.objects.create_user('integrity-buyer')
        self.other = User.objects.create_user('integrity-other')
        self.product = Product.objects.create(
            seller=self.seller, name='Rice', description='Organic rice', category='Food',
            price='20', stock_quantity='10', selling_type='both', verification_status='verified',
        )
        self.checkout_data = dict(recipient_name='Buyer', email='buyer@example.com',
                                 phone_number='01700000000', delivery_address='Dhaka', payment_method='bkash')
        self.client.force_login(self.buyer)

    def cart(self, buyer=None, quantity='1'):
        cart, _ = Cart.objects.get_or_create(user=buyer or self.buyer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=quantity)
        return cart

    def auction(self, **changes):
        data = dict(product=self.product, starting_price='20', minimum_increment='1',
                    start_time=timezone.now() - timedelta(hours=1),
                    end_time=timezone.now() + timedelta(hours=1), status='active')
        data.update(changes)
        return Auction.objects.create(**data)

    def post(self, route, *args, **data):
        return self.client.post(reverse(route, args=args), data)


class IntegrityTests(IntegrityFixtures, TestCase):
    def test_legacy_ended_auction_winner_is_recovered_and_idempotent(self):
        auction = self.auction(status='ended', end_time=timezone.now() - timedelta(minutes=1))
        Bid.objects.create(auction=auction, bidder=self.buyer, amount='25')
        self.client.get(reverse('marketplace_product_detail', args=[self.product.pk]))
        auction.refresh_from_db()
        self.assertEqual(auction.winner_id, self.buyer.pk)
        self.assertEqual(auction.winning_bid, Decimal('25'))
        finalize_auction(auction)
        auction.refresh_from_db()
        self.assertEqual(auction.winner_id, self.buyer.pk)

    def test_finalization_skips_seller_bids_and_preserves_cancelled_auctions(self):
        auction = self.auction(end_time=timezone.now() - timedelta(minutes=1))
        Bid.objects.create(auction=auction, bidder=self.seller, amount='100')
        Bid.objects.create(auction=auction, bidder=self.buyer, amount='25')
        self.assertEqual(finalize_auction(auction).winner_id, self.buyer.pk)
        Auction.objects.filter(pk=auction.pk).update(status='cancelled', winner=None, winning_bid=None)
        self.assertIsNone(finalize_auction(auction).winner_id)

    def test_live_auction_blocks_cart_add_and_preexisting_checkout(self):
        self.auction()
        response = self.post('add_to_cart', self.product.pk, quantity='1')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CartItem.objects.exists())
        self.cart()
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('cart'))
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))
        response = self.client.get(reverse('marketplace_product_detail', args=[self.product.pk]))
        self.assertContains(response, 'Fixed-price purchases are paused')
        self.assertNotContains(response, reverse('add_to_cart', args=[self.product.pk]))

    def test_upcoming_auction_reserves_stock_before_start(self):
        self.auction(status='upcoming', start_time=timezone.now() + timedelta(minutes=30))
        self.cart()
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('cart'))
        self.assertFalse(Order.objects.exists())

    def test_winner_stock_is_protected_after_end_until_checkout(self):
        auction = self.auction(end_time=timezone.now() - timedelta(minutes=1))
        Bid.objects.create(auction=auction, bidder=self.buyer, amount='25')
        self.cart(self.other, quantity='10')
        self.client.force_login(self.other)
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('cart'))
        self.client.force_login(self.buyer)
        self.assertRedirects(self.post('auction_winner_checkout', auction.pk, **self.checkout_data), reverse('my_orders'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('9'))
        # Remaining fixed-price stock becomes purchasable after winning checkout.
        CartItem.objects.filter(cart__user=self.other).update(quantity='9')
        self.client.force_login(self.other)
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('order_success'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('0'))
        self.assertFalse(self.product.is_available)

    def test_expired_no_bid_or_cancelled_auction_does_not_block_cart(self):
        auction = self.auction(end_time=timezone.now() - timedelta(minutes=1))
        cart = self.cart()
        self.assertEqual(len(checkout_cart(cart.pk, self.buyer, self.checkout_data)), 1)
        Auction.objects.filter(pk=auction.pk).update(status='cancelled')
        Bid.objects.create(auction=auction, bidder=self.other, amount='25')
        cart = self.cart()
        self.assertEqual(len(checkout_cart(cart.pk, self.buyer, self.checkout_data)), 1)

    def test_failed_mixed_cart_rolls_back_all_products_and_orders(self):
        cart = self.cart()
        unavailable = Product.objects.create(seller=self.seller, name='Unavailable', price='5', stock_quantity='0',
                                             verification_status='verified')
        CartItem.objects.create(cart=cart, product=unavailable, quantity='1')
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('cart'))
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(CartItem.objects.count(), 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))

    def test_conditional_stock_deduction_rejects_stale_stock(self):
        stale = Product.objects.get(pk=self.product.pk)
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='0')
        with self.assertRaises(CheckoutUnavailable):
            deduct_stock(stale, Decimal('1'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('0'))

    def test_fractional_stock_is_exact_when_fully_consumed(self):
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='0.30')
        for buyer, quantity in [(self.buyer, '0.10'), (self.other, '0.20')]:
            cart = self.cart(buyer, quantity)
            checkout_cart(cart.pk, buyer, self.checkout_data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('0'))
        self.assertFalse(self.product.is_available)

    def test_reviews_are_unique_in_the_database(self):
        cart = self.cart()
        order = checkout_cart(cart.pk, self.buyer, self.checkout_data)[0]
        values = dict(buyer=self.buyer, product=self.product, order=order, rating=5, comment='Fresh')
        Review.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(**values)
        self.assertEqual(Review.objects.count(), 1)

    def test_unverified_unavailable_and_fixed_products_reject_bids_and_public_detail(self):
        auction = self.auction()
        for changes in [dict(verification_status='pending'), dict(verification_status='rejected'),
                        dict(is_available=False), dict(stock_quantity='0'), dict(selling_type='fixed')]:
            Product.objects.filter(pk=self.product.pk).update(
                verification_status='verified', is_available=True, stock_quantity='10', selling_type='both',
            )
            Product.objects.filter(pk=self.product.pk).update(**changes)
            with self.subTest(changes=changes):
                self.assertEqual(self.post('place_bid', auction.pk, amount='30').status_code, 404)
                self.client.logout()
                self.assertEqual(self.client.get(reverse('auction_detail', args=[auction.pk])).status_code, 404)
                self.client.force_login(self.buyer)
                self.assertFalse(Bid.objects.exists())

    def test_winner_cannot_checkout_unverified_or_soft_deleted_product(self):
        auction = self.auction(status='ended', winner=self.buyer, winning_bid='25',
                               end_time=timezone.now() - timedelta(minutes=1))
        for changes in [dict(verification_status='pending'), dict(is_available=False)]:
            Product.objects.filter(pk=self.product.pk).update(**changes)
            self.post('auction_winner_checkout', auction.pk, **self.checkout_data)
            self.assertFalse(Order.objects.exists())

    def test_wishlist_rejects_unverified_unavailable_or_empty_products(self):
        for changes in [dict(verification_status='pending'), dict(is_available=False), dict(stock_quantity='0')]:
            Product.objects.filter(pk=self.product.pk).update(**changes)
            self.assertEqual(self.post('add_wishlist', self.product.pk).status_code, 404)
        self.assertFalse(Wishlist.objects.exists())

    def test_both_price_filters_reject_bad_input_without_500(self):
        for field in ['min_price', 'max_price']:
            for value in ['abc', 'NaN', 'Infinity', '-1', '99999999999999999', '1.001']:
                with self.subTest(field=field, value=value):
                    response = self.client.get(reverse('marketplace'), {field: value})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'Enter a valid non-negative price')

    def test_auction_creation_requires_sufficient_available_stock(self):
        self.client.force_login(self.seller)
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='0.50')
        response = self.post('create_auction', self.product.pk, starting_price='20', minimum_increment='1',
                             start_time=timezone.now().isoformat(),
                             end_time=(timezone.now() + timedelta(hours=1)).isoformat())
        self.assertRedirects(response, reverse('my_products'))
        self.assertFalse(Auction.objects.exists())

    def test_seller_can_create_and_edit_upcoming_auction(self):
        self.client.force_login(self.seller)
        data = dict(starting_price='20', minimum_increment='1',
                    start_time=(timezone.now() + timedelta(hours=1)).isoformat(),
                    end_time=(timezone.now() + timedelta(hours=2)).isoformat())
        self.assertRedirects(self.post('create_auction', self.product.pk, **data), reverse('my_products'))
        auction = Auction.objects.get()
        self.assertEqual(auction.status, 'upcoming')
        self.assertRedirects(self.post('edit_auction', auction.pk, **dict(data, starting_price='30')),
                             reverse('my_products'))
        auction.refresh_from_db()
        self.assertEqual(auction.starting_price, Decimal('30'))
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='0')
        self.assertRedirects(self.post('edit_auction', auction.pk, **data), reverse('my_products'))
        auction.refresh_from_db()
        self.assertEqual(auction.starting_price, Decimal('30'))


class ConcurrentPurchaseTests(IntegrityFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        if connection.vendor == 'sqlite' and connection.creation.is_in_memory_db(connection.settings_dict['NAME']):
            self.skipTest('Run with ROOTLINE_TEST_DB=/tmp/rootline-tests.sqlite3 to exercise SQLite file locking.')

    def race(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations))

    def test_two_buyers_compete_for_last_unit(self):
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='1')
        carts = [self.cart(self.buyer), self.cart(self.other)]
        def buy(cart, buyer):
            try:
                checkout_cart(cart.pk, buyer, self.checkout_data)
                return 'purchased'
            except CheckoutUnavailable:
                return 'unavailable'
        results = self.race([lambda: buy(carts[0], self.buyer), lambda: buy(carts[1], self.other)])
        self.assertCountEqual(results, ['purchased', 'unavailable'])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('0'))

    def test_duplicate_cart_submission_creates_one_order(self):
        cart = self.cart()
        def buy():
            try:
                checkout_cart(cart.pk, self.buyer, self.checkout_data)
                return 'purchased'
            except CheckoutUnavailable:
                return 'unavailable'
        self.assertCountEqual(self.race([buy, buy]), ['purchased', 'unavailable'])
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('9'))

    def test_cart_cannot_compete_with_auction_winner_for_last_unit(self):
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='1')
        auction = self.auction(status='ended', winner=self.buyer, winning_bid='25',
                               end_time=timezone.now() - timedelta(minutes=1))
        cart = self.cart(self.other)
        winner_client = Client()
        winner_client.force_login(self.buyer)
        def cart_buy():
            try:
                checkout_cart(cart.pk, self.other, self.checkout_data)
                return 'purchased'
            except CheckoutUnavailable:
                return 'unavailable'
        def winner_buy():
            response = winner_client.post(reverse('auction_winner_checkout', args=[auction.pk]), self.checkout_data)
            self.assertEqual(response.status_code, 302)
            return 'winner purchased'
        self.assertCountEqual(self.race([cart_buy, winner_buy]), ['unavailable', 'winner purchased'])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().buyer_id, self.buyer.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('0'))

    def test_duplicate_auction_checkout_creates_one_order(self):
        auction = self.auction(status='ended', winner=self.buyer, winning_bid='25',
                               end_time=timezone.now() - timedelta(minutes=1))
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.buyer)
        url = reverse('auction_winner_checkout', args=[auction.pk])
        results = self.race([lambda: clients[0].post(url, self.checkout_data).status_code,
                             lambda: clients[1].post(url, self.checkout_data).status_code])
        self.assertEqual(results, [302, 302])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('9'))

    def test_duplicate_review_submissions_create_one_review(self):
        cart = self.cart()
        order = checkout_cart(cart.pk, self.buyer, self.checkout_data)[0]
        Order.objects.filter(pk=order.pk).update(status='delivered')
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.buyer)
        url = reverse('add_review', args=[self.product.pk, order.pk])
        data = dict(rating='5', comment='Fresh rice')
        results = self.race([lambda: clients[0].post(url, data).status_code,
                             lambda: clients[1].post(url, data).status_code])
        self.assertEqual(results, [302, 302])
        self.assertEqual(Review.objects.count(), 1)

    def test_simultaneous_equal_bids_recheck_minimum(self):
        auction = self.auction()
        clients = [Client(), Client()]
        clients[0].force_login(self.buyer)
        clients[1].force_login(self.other)
        url = reverse('place_bid', args=[auction.pk])
        results = self.race([lambda: clients[0].post(url, {'amount': '20'}).status_code,
                             lambda: clients[1].post(url, {'amount': '20'}).status_code])
        self.assertEqual(results, [302, 302])
        self.assertEqual(Bid.objects.count(), 1)

    def test_auction_creation_and_cart_purchase_cannot_claim_same_last_unit(self):
        Product.objects.filter(pk=self.product.pk).update(stock_quantity='1')
        cart = self.cart()
        seller_client = Client()
        seller_client.force_login(self.seller)
        data = dict(starting_price='20', minimum_increment='1',
                    start_time=timezone.now().isoformat(),
                    end_time=(timezone.now() + timedelta(hours=1)).isoformat())
        def cart_buy():
            try:
                checkout_cart(cart.pk, self.buyer, self.checkout_data)
            except CheckoutUnavailable:
                pass
        self.race([cart_buy, lambda: seller_client.post(reverse('create_auction', args=[self.product.pk]), data)])
        self.assertEqual(Order.objects.count() + Auction.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('1') if Auction.objects.exists() else Decimal('0'))

    def test_duplicate_cancellations_restore_stock_once(self):
        order = checkout_cart(self.cart().pk, self.buyer, self.checkout_data)[0]
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.seller)
        url = reverse('update_order_status', args=[order.pk])
        results = self.race([lambda: clients[0].post(url, {'action': 'cancel'}).status_code,
                             lambda: clients[1].post(url, {'action': 'cancel'}).status_code])
        self.assertEqual(results, [302, 302])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))
