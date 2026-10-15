from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bidding.models import Auction
from disputes.models import Dispute
from disputes.services import decide_dispute, raise_dispute, respond_to_dispute
from orders.models import Order
from payments.models import Payment
from payments.services import confirm_delivery, fail_payment, refund_payment, submit_transaction, verify_payment
from products.models import Product
from .audit import DecisionError
from .models import AuditRecord
from .services import request_seller_access, review_product, review_seller


class Fixtures:
    @classmethod
    def make_fixtures(cls):
        call_command('create_dashboard_roles', stdout=StringIO())
        cls.owner = User.objects.create_superuser('owner', 'owner@example.com', 'Owner-pass-943!')
        cls.staff = User.objects.create_user('staff', is_staff=True)
        cls.finance = User.objects.create_user('finance', password='Finance-pass-943!', is_staff=True)
        cls.support = User.objects.create_user('support', is_staff=True)
        cls.catalogue = User.objects.create_user('catalogue', is_staff=True)
        for user, role in [(cls.finance, 'Finance'), (cls.support, 'Support'), (cls.catalogue, 'Catalogue')]:
            user.groups.add(Group.objects.get(name=role))
        cls.buyer = User.objects.create_user('buyer', email='buyer@example.com')
        cls.seller = User.objects.create_user('seller', seller_approved=True)
        cls.applicant = User.objects.create_user('applicant', seller_requested=True, seller_requested_at=timezone.now())
        cls.product = Product.objects.create(seller=cls.seller, name='Fresh rice', category='Rice', price='100.10', stock_quantity='10')
        cls.order = Order.objects.create(buyer=cls.buyer, seller=cls.seller, recipient_name='Buyer',
                                        email='buyer@example.com', phone_number='01700000000', delivery_address='Dhaka',
                                        payment_method='bkash', total_amount='100.10', status='shipped')
        cls.payment = Payment.objects.create(order=cls.order, amount='100.10', transaction_id='BKASH-123',
                                            payment_status='verification_pending')
        cls.dispute = Dispute.objects.create(order=cls.order, raised_by=cls.buyer, reason='damaged', description='Damaged rice bag')

    def hold_payment(self):
        Payment.objects.filter(pk=self.payment.pk).update(payment_status='paid', escrow_status='held')

    def post(self, name, *args, **data):
        return self.client.post(reverse('dashboard:' + name, args=args), data)

    def action_routes(self):
        return [
            ('payment_verify', [self.payment.pk], self.finance), ('payment_fail', [self.payment.pk], self.finance),
            ('dispute_decide', [self.dispute.pk], self.support),
            ('product_decide', [self.product.pk, 'verified'], self.catalogue),
            ('product_decide', [self.product.pk, 'rejected'], self.catalogue),
            ('seller_decide', [self.applicant.pk, 'approve'], self.catalogue),
            ('seller_decide', [self.applicant.pk, 'reject'], self.catalogue),
            ('seller_decide', [self.seller.pk, 'revoke'], self.catalogue),
        ]


class DashboardAccessTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_fixtures()

    def test_access_matrix(self):
        pages = {'overview': None, 'orders': None, 'activity': None,
                 'payments': 'finance', 'disputes': 'support', 'products': 'catalogue', 'sellers': 'catalogue'}
        for username in ['staff', 'finance', 'support', 'catalogue', 'owner', 'buyer']:
            self.client.force_login(getattr(self, username))
            for route, role in pages.items():
                with self.subTest(user=username, page=route):
                    expected = 200 if username == 'owner' or (username != 'buyer' and role in (None, username)) else 403
                    self.assertEqual(self.client.get(reverse('dashboard:' + route)).status_code, expected)
        self.client.logout()
        for route in pages:
            self.assertEqual(self.client.get(reverse('dashboard:' + route)).status_code, 403)

    def test_dispute_detail_is_support_only(self):
        for user, expected in [(self.staff, 403), (self.finance, 403), (self.catalogue, 403), (self.support, 200), (self.owner, 200)]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('dashboard:dispute_detail', args=[self.dispute.pk])).status_code, expected)

    def test_sidebar_contains_only_allowed_pages(self):
        for user in [self.staff, self.finance, self.support, self.catalogue, self.owner]:
            self.client.force_login(user)
            response = self.client.get(reverse('dashboard:overview'))
            for route, allowed in [('payments', user in (self.finance, self.owner)), ('disputes', user in (self.support, self.owner)),
                                    ('products', user in (self.catalogue, self.owner)), ('sellers', user in (self.catalogue, self.owner))]:
                checker = self.assertContains if allowed else self.assertNotContains
                checker(response, f'href="{reverse("dashboard:" + route)}"')
            self.assertNotContains(response, '/admin/')
            self.assertContains(response, '/static/dashboard/dashboard.css')
            self.assertNotContains(response, 'output.css')

    def test_group_without_staff_flag_grants_no_access(self):
        self.buyer.groups.add(Group.objects.get(name='Finance'))
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(reverse('dashboard:payments')).status_code, 403)
        self.assertEqual(self.post('payment_verify', self.payment.pk).status_code, 403)

    def test_multiple_groups_and_role_removal_take_effect(self):
        self.finance.groups.add(Group.objects.get(name='Support'))
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get(reverse('dashboard:disputes')).status_code, 200)
        self.finance.groups.remove(Group.objects.get(name='Finance'))
        self.assertEqual(self.client.get(reverse('dashboard:payments')).status_code, 403)

    def test_inactive_staff_denied(self):
        self.finance.is_active = False
        self.finance.save()
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get(reverse('dashboard:overview')).status_code, 403)

    def test_action_routes_require_the_right_role_and_post(self):
        for name, args, authorized in self.action_routes():
            with self.subTest(route=name, args=args):
                for user in [self.buyer, self.staff]:
                    self.client.force_login(user)
                    self.assertEqual(self.post(name, *args).status_code, 403)
                self.client.force_login(self.finance if authorized != self.finance else self.support)
                self.assertEqual(self.post(name, *args).status_code, 403)
                self.client.force_login(authorized)
                for method in ['get', 'put', 'delete', 'patch', 'head']:
                    self.assertEqual(getattr(self.client, method)(reverse('dashboard:' + name, args=args)).status_code, 405)
        self.assertFalse(AuditRecord.objects.exists())

    def test_action_routes_require_csrf_and_accept_valid_token(self):
        secured = Client(enforce_csrf_checks=True)
        for name, args, authorized in self.action_routes():
            secured.force_login(authorized)
            self.assertEqual(secured.post(reverse('dashboard:' + name, args=args)).status_code, 403)
        secured.force_login(self.finance)
        secured.get(reverse('dashboard:payments'))
        response = secured.post(reverse('dashboard:payment_verify', args=[self.payment.pk]),
                                {'csrfmiddlewaretoken': secured.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'paid')

    def test_read_only_pages_do_not_accept_post(self):
        self.client.force_login(self.owner)
        for name in ['overview', 'orders', 'activity', 'payments', 'disputes', 'products', 'sellers']:
            self.assertEqual(self.post(name).status_code, 405)

    def test_admin_is_owner_only_including_login(self):
        for user in [self.staff, self.finance, self.support, self.catalogue, self.buyer]:
            self.client.force_login(user)
            for name in ['admin:index', 'admin:login', 'admin:auth_group_changelist', 'admin:accounts_user_changelist']:
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:auth_group_changelist')).status_code, 200)

    def test_owner_assigns_roles_from_groups_screen(self):
        self.client.force_login(self.owner)
        group = Group.objects.get(name='Finance')
        url = reverse('admin:auth_group_change', args=[group.pk])
        self.assertContains(self.client.get(url), 'name="members"')
        response = self.client.post(url, {'name': 'Finance', 'members': [self.finance.pk, self.staff.pk], '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.staff.groups.filter(name='Finance').exists())
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('dashboard:payments')).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_login_form_refuses_staff_credentials(self):
        response = self.client.post(reverse('admin:login'), {'username': 'finance', 'password': 'Finance-pass-943!'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reserved for the owner')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_role_command_is_idempotent_and_grants_no_model_permissions(self):
        call_command('create_dashboard_roles', stdout=StringIO())
        self.assertEqual(Group.objects.filter(name__in=['Finance', 'Support', 'Catalogue']).count(), 3)
        for group in Group.objects.all():
            self.assertFalse(group.permissions.exists())


class DecisionTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_fixtures()

    def test_verify_holds_escrow_and_audits_actor_target_and_note(self):
        self.client.force_login(self.finance)
        response = self.post('payment_verify', self.payment.pk, note='Checked bKash ledger', next='https://evil.example')
        self.assertRedirects(response, reverse('dashboard:payments'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'paid')
        self.assertEqual(self.payment.escrow_status, 'held')
        self.assertIsNotNone(self.payment.paid_at)
        entry = AuditRecord.objects.get()
        self.assertEqual(entry.actor, self.finance)
        self.assertEqual(entry.action, 'payment.verify')
        self.assertEqual(entry.target, f'payments.payment:{self.payment.pk}')
        self.assertEqual(entry.note, 'Checked bKash ledger')

    def test_verify_fail_are_mutually_exclusive_and_errors_are_shown(self):
        self.client.force_login(self.finance)
        self.post('payment_verify', self.payment.pk)
        for route in ['payment_verify', 'payment_fail']:
            response = self.post(route, self.payment.pk)
            self.assertContains(self.client.get(response.url), 'Only payments awaiting verification')
        self.assertEqual(AuditRecord.objects.count(), 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.escrow_status, 'held')

    def test_finance_can_fail_a_pending_verification_after_seller_cancels(self):
        Order.objects.filter(pk=self.order.pk).update(status='cancelled')
        fail_payment(self.payment.pk, actor=self.finance, note='Cancelled order; no valid transaction')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'failed')
        self.assertEqual(AuditRecord.objects.get().action, 'payment.fail')

    def test_failed_payment_can_be_resubmitted_but_refunded_payment_cannot(self):
        fail_payment(self.payment.pk, actor=self.finance, note='No matching transaction')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'failed')
        self.assertEqual(self.payment.escrow_status, 'not_held')
        submit_transaction(self.order.pk, actor=self.buyer, transaction_id='NEW-TXN')
        verify_payment(self.payment.pk, actor=self.finance)
        decide_dispute(self.dispute.pk, actor=self.support, decision='refund_approved')
        with self.assertRaises(DecisionError):
            submit_transaction(self.order.pk, actor=self.buyer, transaction_id='RETRY')
        self.assertEqual(AuditRecord.objects.filter(action='payment.fail').get().note, 'No matching transaction')

    def test_missing_transaction_cancelled_order_and_wrong_amount_cannot_be_verified(self):
        cases = [({'transaction_id': ''}, {}), ({'amount': '99'}, {}), ({}, {'status': 'cancelled'}), ({}, {'status': 'delivered'})]
        for payment_changes, order_changes in cases:
            Payment.objects.filter(pk=self.payment.pk).update(transaction_id='TXN', amount='100.10')
            Payment.objects.filter(pk=self.payment.pk).update(**payment_changes)
            Order.objects.filter(pk=self.order.pk).update(status='shipped')
            Order.objects.filter(pk=self.order.pk).update(**order_changes)
            with self.assertRaises(DecisionError):
                verify_payment(self.payment.pk, actor=self.finance)
        self.assertFalse(AuditRecord.objects.exists())

    def test_refund_cancels_order_and_audits_both_decision_and_money_change(self):
        self.hold_payment()
        self.client.force_login(self.support)
        self.assertRedirects(self.post('dispute_decide', self.dispute.pk, decision='refund_approved', note='Claim substantiated'),
                             reverse('dashboard:dispute_detail', args=[self.dispute.pk]))
        self.payment.refresh_from_db(); self.order.refresh_from_db(); self.dispute.refresh_from_db()
        self.assertEqual((self.payment.payment_status, self.payment.escrow_status), ('refunded', 'refunded'))
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.payment.seller_amount, Decimal('0'))
        self.assertEqual(self.payment.commission_amount, Decimal('0'))
        self.assertEqual(self.dispute.resolved_by, self.support)
        self.assertIsNotNone(self.dispute.resolved_at)
        self.assertEqual(set(AuditRecord.objects.values_list('action', flat=True)), {'payment.refund', 'dispute.refund_approved'})
        self.assertTrue(all(entry.note == 'Claim substantiated' for entry in AuditRecord.objects.all()))

    def test_favour_seller_and_reject_release_with_one_commission_rate(self):
        for decision in ['seller_favored', 'rejected']:
            with self.subTest(decision=decision):
                self.hold_payment()
                decide_dispute(self.dispute.pk, actor=self.support, decision=decision, note='Delivery evidence checked')
                self.order.refresh_from_db(); self.payment.refresh_from_db(); self.dispute.refresh_from_db()
                self.assertEqual(self.order.status, 'delivered')
                self.assertEqual(self.payment.escrow_status, 'released')
                self.assertEqual(self.payment.payment_status, 'paid')
                self.assertEqual(self.payment.commission_amount, Decimal('5.01'))
                self.assertEqual(self.payment.seller_amount, Decimal('95.09'))
                self.assertEqual(self.payment.commission_amount + self.payment.seller_amount, self.payment.amount)
                self.assertIsNotNone(self.payment.released_at)
                self.assertEqual(self.dispute.status, decision)
                # Reset the fixture solely to exercise the other independent final outcome.
                Order.objects.filter(pk=self.order.pk).update(status='shipped')
                Dispute.objects.filter(pk=self.dispute.pk).update(status='open', resolved_by=None, resolved_at=None)

    def test_all_repeated_final_decisions_are_blocked(self):
        self.hold_payment()
        decide_dispute(self.dispute.pk, actor=self.support, decision='refund_approved')
        for decision in ['refund_approved', 'seller_favored', 'rejected', 'under_review']:
            with self.assertRaisesMessage(DecisionError, 'already been resolved'):
                decide_dispute(self.dispute.pk, actor=self.owner, decision=decision)
        self.assertEqual(AuditRecord.objects.count(), 2)
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.resolved_by, self.support)

    def test_under_review_preserves_money_and_can_be_resolved_later(self):
        self.hold_payment()
        decide_dispute(self.dispute.pk, actor=self.support, decision='under_review', note='Checking courier receipt')
        self.dispute.refresh_from_db(); self.payment.refresh_from_db()
        self.assertIsNone(self.dispute.resolved_at)
        self.assertEqual(self.payment.escrow_status, 'held')
        with self.assertRaisesMessage(DecisionError, 'already under review'):
            decide_dispute(self.dispute.pk, actor=self.support, decision='under_review')
        decide_dispute(self.dispute.pk, actor=self.support, decision='seller_favored')
        self.assertEqual(AuditRecord.objects.count(), 3)

    def test_invalid_decision_or_unheld_escrow_leaves_dispute_open(self):
        for decision in ['bad', 'refund_approved', 'seller_favored', 'rejected']:
            with self.assertRaises(DecisionError):
                decide_dispute(self.dispute.pk, actor=self.support, decision=decision)
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.status, 'open')
        self.assertFalse(AuditRecord.objects.exists())

    def test_audit_failure_rolls_back_entire_resolution(self):
        self.hold_payment()
        with patch('disputes.services.record_action', side_effect=RuntimeError('Audit unavailable')):
            with self.assertRaises(RuntimeError):
                decide_dispute(self.dispute.pk, actor=self.support, decision='seller_favored')
        self.order.refresh_from_db(); self.payment.refresh_from_db(); self.dispute.refresh_from_db()
        self.assertEqual(self.order.status, 'shipped')
        self.assertEqual(self.payment.escrow_status, 'held')
        self.assertEqual(self.dispute.status, 'open')
        self.assertFalse(AuditRecord.objects.exists())

    def test_delivery_cannot_release_money_during_any_open_dispute(self):
        self.hold_payment()
        self.client.force_login(self.buyer)
        for status in ['open', 'seller_responded', 'under_review']:
            Dispute.objects.filter(pk=self.dispute.pk).update(status=status)
            response = self.client.post(reverse('confirm_delivery', args=[self.order.pk]), follow=True)
            self.assertContains(response, 'while a dispute is open')
            self.order.refresh_from_db(); self.payment.refresh_from_db()
            self.assertEqual(self.order.status, 'shipped')
            self.assertEqual(self.payment.escrow_status, 'held')
        self.assertFalse(AuditRecord.objects.exists())
        self.assertEqual(self.client.get(reverse('confirm_delivery', args=[self.order.pk])).status_code, 405)

    def test_delivery_without_dispute_releases_once(self):
        self.hold_payment()
        self.dispute.delete()
        confirm_delivery(self.order.pk, actor=self.buyer)
        with self.assertRaises(DecisionError):
            confirm_delivery(self.order.pk, actor=self.buyer)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.seller_amount, Decimal('95.09'))
        self.assertEqual(AuditRecord.objects.get().actor, self.buyer)

    def test_payment_without_actor_rolls_back(self):
        with self.assertRaisesMessage(DecisionError, 'authenticated actor'):
            verify_payment(self.payment.pk, actor=None)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'verification_pending')

    def test_missing_records_404_and_invalid_forms_400(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.post('payment_verify', 999999).status_code, 404)
        self.assertEqual(self.post('dispute_decide', self.dispute.pk, decision='invalid').status_code, 400)
        self.assertEqual(self.post('dispute_decide', self.dispute.pk, decision='under_review', note='x' * 4001).status_code, 400)
        self.post('payment_verify', self.payment.pk, note='x' * 4001)
        self.assertFalse(AuditRecord.objects.exists())

    def test_seller_cannot_overwrite_resolved_dispute(self):
        self.hold_payment()
        decide_dispute(self.dispute.pk, actor=self.support, decision='rejected')
        with self.assertRaisesMessage(DecisionError, 'already been resolved'):
            respond_to_dispute(self.dispute.pk, actor=self.seller, response='Late update')

    def test_product_and_seller_decisions_are_audited_and_repeats_blocked(self):
        self.client.force_login(self.catalogue)
        self.assertRedirects(self.post('product_decide', self.product.pk, 'verified', note='Image checked'), reverse('dashboard:products'))
        self.assertRedirects(self.post('seller_decide', self.applicant.pk, 'approve', note='Identity checked'), reverse('dashboard:sellers'))
        self.product.refresh_from_db(); self.applicant.refresh_from_db()
        self.assertEqual(self.product.verification_status, 'verified')
        self.assertTrue(self.applicant.seller_approved)
        self.assertFalse(self.applicant.seller_requested)
        with self.assertRaises(DecisionError):
            review_product(self.product.pk, actor=self.catalogue, decision='rejected')
        with self.assertRaises(DecisionError):
            review_seller(self.applicant.pk, actor=self.catalogue, decision='approve')
        review_seller(self.applicant.pk, actor=self.catalogue, decision='revoke', note='Access revoked')
        self.assertEqual(AuditRecord.objects.count(), 3)
        self.assertEqual(set(AuditRecord.objects.values_list('actor_id', flat=True)), {self.catalogue.pk})

    def test_product_rejection_and_seller_rejection(self):
        review_product(self.product.pk, actor=self.catalogue, decision='rejected', note='Unclear listing')
        review_seller(self.applicant.pk, actor=self.catalogue, decision='reject', note='Incomplete details')
        self.product.refresh_from_db(); self.applicant.refresh_from_db()
        self.assertEqual(self.product.verification_status, 'rejected')
        self.assertFalse(self.applicant.seller_requested or self.applicant.seller_approved)
        self.assertEqual(set(AuditRecord.objects.values_list('action', flat=True)), {'product.rejected', 'seller.reject'})
        request_seller_access(self.applicant.pk)
        self.applicant.refresh_from_db()
        self.assertIsNotNone(self.applicant.seller_requested_at)

    def test_audit_preserves_actor_name_after_actor_is_deleted(self):
        verify_payment(self.payment.pk, actor=self.finance)
        self.finance.delete()
        entry = AuditRecord.objects.get()
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_name, 'finance')


class AdminServiceTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_fixtures()

    def setUp(self):
        self.client.force_login(self.owner)

    def admin_action(self, model, action, pk, note='Owner checked record'):
        url = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')
        return self.client.post(url, {'action': action, '_selected_action': [pk], 'note': note})

    def test_admin_verification_and_failure_use_shared_rules_and_audit(self):
        self.assertEqual(self.admin_action(Payment, 'verify_payment', self.payment.pk).status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.escrow_status, 'held')
        self.assertEqual(AuditRecord.objects.get().actor, self.owner)
        response = self.admin_action(Payment, 'mark_payment_failed', self.payment.pk)
        self.assertContains(self.client.get(response.url), 'Only payments awaiting verification')
        self.assertEqual(AuditRecord.objects.count(), 1)

    def test_admin_failed_payment_audited(self):
        self.admin_action(Payment, 'mark_payment_failed', self.payment.pk)
        self.assertEqual(AuditRecord.objects.get().action, 'payment.fail')

    def test_admin_refund_uses_shared_settlement_and_cannot_be_resolved_twice(self):
        self.hold_payment()
        self.admin_action(Dispute, 'refund_buyer', self.dispute.pk)
        self.order.refresh_from_db(); self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.payment.payment_status, 'refunded')
        self.assertEqual(AuditRecord.objects.count(), 2)
        response = self.admin_action(Dispute, 'favour_seller', self.dispute.pk)
        self.assertContains(self.client.get(response.url), 'already been resolved')
        self.assertEqual(AuditRecord.objects.count(), 2)
        self.assertEqual(set(AuditRecord.objects.values_list('note', flat=True)), {'Owner checked record'})

    def test_admin_release_uses_commission_and_marks_order_delivered(self):
        self.hold_payment()
        self.admin_action(Dispute, 'reject_dispute', self.dispute.pk)
        self.order.refresh_from_db(); self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        self.assertEqual(self.payment.commission_amount, Decimal('5.01'))
        self.assertEqual(AuditRecord.objects.filter(action='payment.release').get().actor, self.owner)

    def test_admin_product_and_seller_approval_rejection_and_revocation_audited(self):
        self.admin_action(Product, 'reject_products', self.product.pk)
        self.admin_action(User, 'reject_sellers', self.applicant.pk)
        request_seller_access(self.applicant.pk)
        self.admin_action(User, 'approve_sellers', self.applicant.pk)
        self.admin_action(User, 'revoke_sellers', self.applicant.pk)
        self.assertEqual(set(AuditRecord.objects.values_list('action', flat=True)),
                         {'product.rejected', 'seller.reject', 'seller.approve', 'seller.revoke'})

    def test_admin_fields_cannot_bypass_services_and_audit_is_read_only(self):
        for model, fields in [(Payment, ['payment_status', 'escrow_status', 'amount', 'commission_amount']),
                              (Dispute, ['status', 'admin_note', 'resolved_at']),
                              (Product, ['verification_status']), (User, ['seller_approved', 'seller_requested'])]:
            model_admin = admin.site._registry[model]
            readonly = model_admin.get_readonly_fields(None)
            self.assertTrue(set(fields).issubset(readonly))
        audit_admin = admin.site._registry[AuditRecord]
        self.assertFalse(audit_admin.has_add_permission(None))
        self.assertFalse(audit_admin.has_change_permission(None))
        self.assertFalse(audit_admin.has_delete_permission(None))

    def test_crafted_admin_form_cannot_change_payment_status(self):
        response = self.client.post(reverse('admin:payments_payment_change', args=[self.payment.pk]), {
            'payment_status': 'paid', 'escrow_status': 'released', '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, 'verification_pending')
        self.assertEqual(self.payment.escrow_status, 'not_held')
        self.assertFalse(AuditRecord.objects.exists())


class DashboardDisplayTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_fixtures()

    def setUp(self):
        self.client.force_login(self.owner)

    def test_payment_tabs_filter_statuses_and_show_method_transaction_and_people(self):
        response = self.client.get(reverse('dashboard:payments'))
        for text in ['BKASH-123', 'bKash', 'buyer', 'seller', '100.10', 'confirm(']:
            self.assertContains(response, text)
        for value in ['paid', 'failed', 'refunded', 'pending']:
            response = self.client.get(reverse('dashboard:payments'), {'tab': value})
            self.assertNotContains(response, 'BKASH-123')
        self.assertEqual(self.client.get(reverse('dashboard:payments'), {'tab': 'invalid'}).context['selected'], 'verification_pending')

    def test_dispute_detail_shows_claim_response_summary_note_form_and_escaped_content(self):
        Dispute.objects.filter(pk=self.dispute.pk).update(seller_response='<script>alert(1)</script>')
        response = self.client.get(reverse('dashboard:dispute_detail', args=[self.dispute.pk]))
        self.assertContains(response, 'Damaged rice bag')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, 'name="note"')
        self.assertContains(response, '5% commission')

    def test_orders_search_number_people_and_status(self):
        url = reverse('dashboard:orders')
        for query in [str(self.order.pk), f'#{self.order.pk}', 'buyer', 'seller', 'buyer@example.com']:
            response = self.client.get(url, {'q': query, 'status': 'shipped'})
            self.assertEqual(list(response.context['page_obj']), [self.order])
        for query in [{'q': 'missing'}, {'q': '9' * 150}, {'status': 'pending'}]:
            self.assertEqual(self.client.get(url, query).context['page_obj'].paginator.count, 0)
        self.assertNotContains(self.client.get(url), 'method="post"')

    @override_settings(DASHBOARD_STALE_HOURS={'payments': 1, 'disputes': 1, 'products': 1, 'sellers': 1})
    def test_overview_counts_and_overdue_filters(self):
        old = timezone.now() - timedelta(hours=2)
        Payment.objects.filter(pk=self.payment.pk).update(updated_at=old)
        Dispute.objects.filter(pk=self.dispute.pk).update(created_at=old)
        Product.objects.filter(pk=self.product.pk).update(created_at=old)
        User.objects.filter(pk=self.applicant.pk).update(seller_requested_at=old)
        Auction.objects.create(product=self.product, starting_price=10, start_time=old,
                               end_time=timezone.now() + timedelta(hours=3), status='active')
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.context['queue_sizes'], {'payments': 1, 'disputes': 1, 'products': 1, 'sellers': 1})
        self.assertEqual([row['count'] for row in response.context['overdue']], [1, 1, 1, 1])
        self.assertEqual(response.context['running_auctions'], 1)
        self.assertEqual(response.context['ending_auctions'], 1)
        for name in ['payments', 'disputes', 'products', 'sellers']:
            self.assertEqual(self.client.get(reverse('dashboard:' + name), {'overdue': '1'}).context['page_obj'].paginator.count, 1)

    def test_overview_escrow_and_commission_totals(self):
        self.hold_payment()
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.context['money']['held'], Decimal('100.10'))
        decide_dispute(self.dispute.pk, actor=self.support, decision='seller_favored')
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.context['money'], {'held': Decimal('0'), 'released': Decimal('95.09'),
                                                    'commission': Decimal('5.01'), 'refunded': Decimal('0')})
        self.assertEqual(response.context['page_obj'].paginator.count, 2)

    def test_all_lists_are_paginated_and_keep_filters(self):
        extra_orders = [Order(buyer=self.buyer, seller=self.seller, total_amount='100.10', status='shipped', payment_method='bkash') for _ in range(26)]
        Order.objects.bulk_create(extra_orders)
        Payment.objects.bulk_create([Payment(order=order, amount='100.10', payment_status='verification_pending') for order in extra_orders])
        Dispute.objects.bulk_create([Dispute(order=order, raised_by=self.buyer, reason='other', description='Claim') for order in extra_orders])
        Product.objects.bulk_create([Product(seller=self.seller, name=f'Product {i}') for i in range(26)])
        User.objects.bulk_create([User(username=f'applicant-{i}', seller_requested=True, seller_requested_at=timezone.now()) for i in range(26)])
        AuditRecord.objects.bulk_create([AuditRecord(actor=self.owner, actor_name='owner', action='test', target='test:1', summary='Test action') for _ in range(26)])
        for route in ['payments', 'disputes', 'products', 'sellers', 'orders', 'activity']:
            url = reverse('dashboard:' + route)
            first = self.client.get(url)
            self.assertEqual(len(first.context['page_obj']), 25)
            second = self.client.get(url, {'page': '2'})
            self.assertEqual(len(second.context['page_obj']), 2 if route != 'activity' else 1)
            self.assertEqual(second.context['page_obj'].number, 2)
            self.assertEqual(self.client.get(url, {'page': 'garbage'}).context['page_obj'].number, 1)
        filtered = self.client.get(reverse('dashboard:orders'), {'q': 'buyer', 'status': 'shipped'})
        self.assertContains(filtered, 'q=buyer&amp;status=shipped&amp;page=2')
        self.assertEqual(self.client.get(reverse('dashboard:overview')).context['page_obj'].paginator.per_page, 10)


class ConcurrentDecisionTests(Fixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.make_fixtures()
        if connection.vendor == 'sqlite' and connection.creation.is_in_memory_db(connection.settings_dict['NAME']):
            self.skipTest('Use ROOTLINE_TEST_DB=work/dashboard-tests.sqlite3 for SQLite concurrency tests.')

    def race(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    operation()
                    return 'saved'
                except DecisionError:
                    return 'blocked'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            return list(pool.map(run, operations))

    def test_simultaneous_verification_and_failure_only_one_wins(self):
        results = self.race([lambda: verify_payment(self.payment.pk, actor=self.finance),
                             lambda: fail_payment(self.payment.pk, actor=self.owner)])
        self.assertCountEqual(results, ['saved', 'blocked'])
        self.assertEqual(AuditRecord.objects.count(), 1)

    def test_simultaneous_refund_and_release_only_one_wins(self):
        self.hold_payment()
        results = self.race([lambda: decide_dispute(self.dispute.pk, actor=self.support, decision='refund_approved'),
                             lambda: decide_dispute(self.dispute.pk, actor=self.owner, decision='seller_favored')])
        self.assertCountEqual(results, ['saved', 'blocked'])
        self.assertEqual(AuditRecord.objects.count(), 2)
        self.payment.refresh_from_db(); self.order.refresh_from_db()
        self.assertIn((self.payment.escrow_status, self.order.status), [('refunded', 'cancelled'), ('released', 'delivered')])

    def test_dispute_creation_racing_with_delivery_preserves_escrow_invariant(self):
        self.hold_payment()
        self.dispute.delete()
        results = self.race([lambda: raise_dispute(self.order.pk, actor=self.buyer, reason='damaged', description='Damaged'),
                             lambda: confirm_delivery(self.order.pk, actor=self.buyer)])
        self.assertCountEqual(results, ['saved', 'blocked'])
        self.order.refresh_from_db(); self.payment.refresh_from_db()
        if Dispute.objects.filter(order=self.order).exists():
            self.assertEqual((self.order.status, self.payment.escrow_status), ('shipped', 'held'))
        else:
            self.assertEqual((self.order.status, self.payment.escrow_status), ('delivered', 'released'))
