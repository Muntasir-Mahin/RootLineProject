from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bidding.models import Auction, Bid
from disputes.models import Dispute
from payments.models import Payment
from products.models import Product
from reviews.models import Review
from wishlist.models import Wishlist
from .models import Cart, CartItem, Order


class MarketplaceWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user('seller', password='Fresh-market-943!', seller_approved=True)
        cls.buyer = User.objects.create_user('buyer', password='Fresh-market-943!')
        cls.other = User.objects.create_user('other', seller_approved=True)
        cls.product = Product.objects.create(
            seller=cls.seller, name='Organic rice', description='Fresh rice',
            category='Grains', price='20.00', stock_quantity='10.00',
            verification_status='verified', selling_type='both',
        )
        cls.checkout_data = dict(recipient_name='Buyer', email='buyer@example.com',
                                 phone_number='01700000000', delivery_address='Dhaka', payment_method='bkash')

    def setUp(self):
        self.client.force_login(self.buyer)

    def post(self, route_name, *args, **data):
        return self.client.post(reverse(route_name, args=args), data)

    def add_item(self, user=None, quantity='2.00'):
        cart, _ = Cart.objects.get_or_create(user=user or self.buyer)
        return CartItem.objects.create(cart=cart, product=self.product, quantity=quantity)

    def checkout(self):
        self.add_item()
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('order_success'))
        return Order.objects.get()

    def auction(self, **kwargs):
        values = dict(product=self.product, starting_price='20', minimum_increment='1',
                      start_time=timezone.now() - timedelta(hours=1),
                      end_time=timezone.now() + timedelta(hours=1), status='active')
        values.update(kwargs)
        return Auction.objects.create(**values)

    def test_seller_cannot_add_own_product_even_with_direct_post(self):
        self.client.force_login(self.seller)
        response = self.post('add_to_cart', self.product.pk, quantity='1')
        self.assertRedirects(response, reverse('marketplace_product_detail', args=[self.product.pk]))
        self.assertFalse(CartItem.objects.exists())
        self.assertContains(self.client.get(reverse('marketplace_product_detail', args=[self.product.pk])),
                            'You cannot buy your own product.')
        self.assertNotContains(self.client.get(reverse('marketplace_product_detail', args=[self.product.pk])),
                               reverse('add_to_cart', args=[self.product.pk]))

    def test_checkout_rejects_existing_self_owned_cart_on_get_and_post(self):
        self.client.force_login(self.seller)
        self.add_item(self.seller)
        for response in [self.client.get(reverse('checkout')), self.post('checkout', **self.checkout_data)]:
            self.assertRedirects(response, reverse('cart'))
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))

    def test_seller_can_buy_from_another_seller(self):
        self.client.force_login(self.other)
        self.add_item(self.other)
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('order_success'))
        self.assertEqual(Order.objects.get().buyer, self.other)

    def test_add_update_remove_cart_and_totals(self):
        self.post('add_to_cart', self.product.pk, quantity='1.25')
        self.post('add_to_cart', self.product.pk, quantity='0.75')
        item = CartItem.objects.get()
        self.assertEqual(item.quantity, Decimal('2'))
        self.assertEqual(self.client.get(reverse('cart')).context['total_price'], Decimal('40'))
        self.post('update_cart_item', item.pk, quantity='3.50')
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal('3.50'))
        self.post('remove_cart_item', item.pk)
        self.assertFalse(CartItem.objects.exists())

    def test_invalid_cart_quantities_do_not_crash_or_mutate(self):
        for quantity in ['NaN', 'Infinity', '-Infinity', '0', '-1', 'abc', '1.001', '10000000000']:
            with self.subTest(quantity=quantity):
                self.assertEqual(self.post('add_to_cart', self.product.pk, quantity=quantity).status_code, 302)
                self.assertFalse(CartItem.objects.exists())
        item = self.add_item()
        for quantity in ['NaN', 'Infinity', '-1', 'abc', '1.001']:
            self.assertEqual(self.post('update_cart_item', item.pk, quantity=quantity).status_code, 302)
            item.refresh_from_db()
            self.assertEqual(item.quantity, Decimal('2'))

    def test_stock_limits_on_add_update_and_checkout(self):
        self.post('add_to_cart', self.product.pk, quantity='11')
        self.assertFalse(CartItem.objects.exists())
        item = self.add_item()
        self.post('add_to_cart', self.product.pk, quantity='9')
        self.post('update_cart_item', item.pk, quantity='11')
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal('2'))
        self.product.stock_quantity = 1
        self.product.save()
        self.assertRedirects(self.post('checkout', **self.checkout_data), reverse('cart'))
        self.assertFalse(Order.objects.exists())

    def test_cart_items_cannot_be_modified_by_another_user(self):
        item = self.add_item(self.seller)
        for action in ['update_cart_item', 'remove_cart_item']:
            self.assertEqual(self.post(action, item.pk, quantity='1').status_code, 404)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())

    def test_unavailable_or_unverified_products_cannot_be_purchased(self):
        for changes in [dict(is_available=False), dict(verification_status='pending'), dict(selling_type='bidding')]:
            Product.objects.filter(pk=self.product.pk).update(**changes)
            self.assertEqual(self.post('add_to_cart', self.product.pk, quantity='1').status_code, 404)
        self.assertFalse(CartItem.objects.exists())

    def test_checkout_creates_order_payment_and_reduces_stock(self):
        order = self.checkout()
        self.assertEqual(order.total_amount, Decimal('40'))
        self.assertEqual(order.items.get().quantity, Decimal('2'))
        self.assertEqual(order.payment.payment_status, 'pending')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('8'))
        self.assertFalse(CartItem.objects.exists())
        self.post('checkout', **self.checkout_data)
        self.assertEqual(Order.objects.count(), 1)

    def test_checkout_groups_orders_by_seller(self):
        item = self.add_item()
        product = Product.objects.create(seller=self.other, name='Beans', price='5', stock_quantity='3',
                                         verification_status='verified')
        CartItem.objects.create(cart=item.cart, product=product, quantity='1')
        self.post('checkout', **self.checkout_data)
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(set(Order.objects.values_list('total_amount', flat=True)), {Decimal('40'), Decimal('5')})

    def test_favourite_add_is_idempotent_and_removal_is_user_scoped(self):
        for _ in range(2):
            self.assertRedirects(self.post('add_wishlist', self.product.pk),
                                 reverse('marketplace_product_detail', args=[self.product.pk]))
        self.assertEqual(Wishlist.objects.filter(user=self.buyer).count(), 1)
        self.assertContains(self.client.get(reverse('marketplace_product_detail', args=[self.product.pk])),
                            'Remove from Wishlist')
        self.assertContains(self.client.get(reverse('my_wishlist')), self.product.name)
        Wishlist.objects.create(user=self.other, product=self.product)
        self.post('remove_wishlist', self.product.pk)
        self.assertFalse(Wishlist.objects.filter(user=self.buyer).exists())
        self.assertTrue(Wishlist.objects.filter(user=self.other).exists())

    def test_favourite_mutations_require_post_and_csrf(self):
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.buyer)
        for action in ['add_wishlist', 'remove_wishlist']:
            url = reverse(action, args=[self.product.pk])
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(secured.post(url).status_code, 403)
        response = secured.get(reverse('marketplace_product_detail', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        token = secured.cookies['csrftoken'].value
        self.assertEqual(secured.post(reverse('add_wishlist', args=[self.product.pk]),
                                      {'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertTrue(Wishlist.objects.filter(user=self.buyer).exists())

    def test_login_required_for_cart_and_favourites(self):
        self.client.logout()
        for action in ['add_to_cart', 'add_wishlist', 'remove_wishlist']:
            response = self.post(action, self.product.pk)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('login')))
        self.assertFalse(CartItem.objects.exists())
        self.assertFalse(Wishlist.objects.exists())

    def test_payment_verification_shipping_delivery_and_review(self):
        order = self.checkout()
        self.assertEqual(self.post('make_payment', order.pk, transaction_id='TXN-123').status_code, 302)
        payment = order.payment
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, 'verification_pending')
        self.client.force_login(self.seller)
        self.post('update_order_status', order.pk, action='confirm')
        self.post('update_order_status', order.pk, action='ship')
        order.refresh_from_db()
        self.assertEqual(order.status, 'confirmed')
        owner = User.objects.create_superuser('workflow-owner', 'owner@example.com', 'Owner-password-943!')
        self.client.force_login(owner)
        self.assertEqual(self.client.post(reverse('admin:payments_payment_changelist'), {
            'action': 'verify_payment', '_selected_action': [payment.pk],
        }).status_code, 302)
        self.client.force_login(self.seller)
        self.post('update_order_status', order.pk, action='ship')
        order.refresh_from_db()
        self.assertEqual(order.status, 'shipped')
        self.client.force_login(self.buyer)
        self.post('confirm_delivery', order.pk)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, 'delivered')
        self.assertEqual(payment.escrow_status, 'released')
        self.assertEqual(payment.commission_amount, Decimal('2'))
        self.assertEqual(payment.seller_amount, Decimal('38'))
        self.post('add_review', self.product.pk, order.pk, rating='5', comment='Great rice')
        self.post('add_review', self.product.pk, order.pk, rating='5', comment='Duplicate')
        self.assertEqual(Review.objects.count(), 1)
        response = self.client.get(reverse('marketplace_product_detail', args=[self.product.pk]))
        self.assertEqual(response.context['seller_rating'], 5)

    def test_review_requires_product_in_delivered_order(self):
        order = self.checkout()
        self.post('add_review', self.product.pk, order.pk, rating='5', comment='Too early')
        self.assertFalse(Review.objects.exists())
        Order.objects.filter(pk=order.pk).update(status='delivered')
        unrelated = Product.objects.create(seller=self.other, name='Not purchased')
        self.post('add_review', unrelated.pk, order.pk, rating='5', comment='Not purchased')
        self.assertFalse(Review.objects.exists())

    def test_cancellation_restores_stock_once_and_refunds_held_payment(self):
        order = self.checkout()
        Payment.objects.filter(order=order).update(payment_status='paid', escrow_status='held')
        self.client.force_login(self.seller)
        for _ in range(2):
            self.post('update_order_status', order.pk, action='cancel')
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal('10'))
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.payment.payment_status, 'refunded')

    def test_dispute_and_seller_response(self):
        order = self.checkout()
        Order.objects.filter(pk=order.pk).update(status='shipped')
        Payment.objects.filter(order=order).update(payment_status='paid', escrow_status='held')
        self.post('raise_dispute', order.pk, reason='damaged', description='Package damaged')
        dispute = Dispute.objects.get()
        self.client.force_login(self.seller)
        self.post('seller_dispute_response', dispute.pk, seller_response='Replacement offered')
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'seller_responded')
        self.assertEqual(dispute.seller_response, 'Replacement offered')

    def test_bid_rejects_seller_and_low_bid_accepts_buyer(self):
        auction = self.auction()
        self.client.force_login(self.seller)
        self.post('place_bid', auction.pk, amount='30')
        self.assertFalse(Bid.objects.exists())
        self.client.force_login(self.buyer)
        self.post('place_bid', auction.pk, amount='19')
        self.assertFalse(Bid.objects.exists())
        self.post('place_bid', auction.pk, amount='25')
        self.assertEqual(Bid.objects.get().bidder, self.buyer)

    def test_marketplace_finalizes_auction_and_winner_checks_out_once(self):
        auction = self.auction(end_time=timezone.now() - timedelta(minutes=1))
        Bid.objects.create(auction=auction, bidder=self.buyer, amount='25')
        self.client.get(reverse('marketplace_product_detail', args=[self.product.pk]))
        auction.refresh_from_db()
        self.assertEqual(auction.winner, self.buyer)
        self.assertEqual(auction.status, 'ended')
        for _ in range(2):
            self.post('auction_winner_checkout', auction.pk, **self.checkout_data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().total_amount, Decimal('25'))

    def test_auction_checkout_rejects_legacy_seller_winner(self):
        auction = self.auction(status='ended', end_time=timezone.now() - timedelta(minutes=1),
                               winner=self.seller, winning_bid='25')
        self.client.force_login(self.seller)
        self.post('auction_winner_checkout', auction.pk, **self.checkout_data)
        self.assertFalse(Order.objects.exists())

    def test_product_creation_edit_and_delete_do_not_allow_verification_or_owner_changes(self):
        self.client.force_login(self.seller)
        data = dict(name='Organic beans', description='Fresh', category='Beans', price='10',
                    stock_quantity='5', unit='kg', selling_type='fixed', is_available='on',
                    seller=self.other.pk, verification_status='verified')
        self.assertRedirects(self.post('add_product', **data), reverse('seller_dashboard'))
        product = Product.objects.get(name='Organic beans')
        self.assertEqual(product.seller, self.seller)
        self.assertEqual(product.verification_status, 'pending')
        self.assertRedirects(self.post('edit_product', product.pk, **dict(data, name='Edited beans')), reverse('my_products'))
        product.refresh_from_db()
        self.assertEqual(product.name, 'Edited beans')
        self.assertEqual(product.seller, self.seller)
        self.assertEqual(product.verification_status, 'pending')
        self.post('delete_product', product.pk)
        product.refresh_from_db()
        self.assertFalse(product.is_available)

    def test_marketplace_search_and_category_filter(self):
        for query in [{'search': 'rice'}, {'category': 'Grains'}, {'selling_type': 'both'}, {'min_price': '10', 'max_price': '30'}]:
            self.assertContains(self.client.get(reverse('marketplace'), query), 'Organic rice')
        self.assertNotContains(self.client.get(reverse('marketplace'), {'search': 'nonexistent'}), 'Organic rice')

    def test_core_pages_render_for_buyer_and_seller(self):
        for user, pages in [(self.buyer, ['profile', 'cart', 'my_orders', 'my_wishlist']),
                            (self.seller, ['seller_dashboard', 'my_products', 'add_product', 'seller_orders', 'seller_reviews'])]:
            self.client.force_login(user)
            for page in pages:
                with self.subTest(user=user.username, page=page):
                    self.assertEqual(self.client.get(reverse(page)).status_code, 200)

    def test_registration_login_profile_and_seller_request(self):
        self.client.logout()
        password = 'Fresh-market-943!'
        self.assertRedirects(self.post('register', username='newbuyer', email='new@example.com',
                                      password1=password, password2=password), reverse('login'))
        self.assertRedirects(self.post('login', username='newbuyer', password=password), reverse('profile'))
        self.post('edit_profile', first_name='New', last_name='Buyer', email='new@example.com',
                  phone_number='01700000000', address='Dhaka')
        self.post('become_seller')
        user = User.objects.get(username='newbuyer')
        self.assertEqual(user.first_name, 'New')
        self.assertTrue(user.seller_requested)
        self.assertFalse(user.seller_approved)

    def test_invalid_price_filters_do_not_crash(self):
        for value in ['NaN', 'Infinity', 'abc', '-1']:
            with self.subTest(value=value):
                self.assertEqual(self.client.get(reverse('marketplace'), {'min_price': value}).status_code, 200)

    def test_other_users_cannot_pay_or_manage_an_order(self):
        order = self.checkout()
        self.client.force_login(self.other)
        for route, data in [('make_payment', {'transaction_id': 'FORGED'}),
                            ('update_order_status', {'action': 'cancel'}),
                            ('confirm_delivery', {})]:
            self.assertEqual(self.post(route, order.pk, **data).status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.payment.payment_status, 'pending')
