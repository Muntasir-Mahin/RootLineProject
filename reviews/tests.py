from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReviewMigrationTests(TransactionTestCase):
    migrate_from = [('reviews', '0001_initial')]
    migrate_to = [('reviews', '0002_review_unique_review_per_buyer_product_order')]

    def test_duplicate_reviews_block_migration_without_deleting_data(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        try:
            apps = executor.loader.project_state(self.migrate_from).apps
            User = apps.get_model('accounts', 'User')
            Product = apps.get_model('products', 'Product')
            Order = apps.get_model('orders', 'Order')
            Review = apps.get_model('reviews', 'Review')
            buyer = User.objects.create(username='migration-buyer')
            seller = User.objects.create(username='migration-seller')
            product = Product.objects.create(seller=seller, name='Rice')
            order = Order.objects.create(buyer=buyer, seller=seller, email='buyer@example.com',
                                         recipient_name='Buyer', phone_number='01700000000',
                                         delivery_address='Dhaka', payment_method='bkash')
            values = dict(buyer=buyer, product=product, order=order, rating=5, comment='Original')
            Review.objects.create(**values)
            duplicate = Review.objects.create(**dict(values, comment='Duplicate'))
            with self.assertRaisesMessage(RuntimeError, 'Duplicate reviews exist'):
                MigrationExecutor(connection).migrate(self.migrate_to)
            self.assertEqual(Review.objects.count(), 2)
            # Reconcile only this test's duplicate before applying the constraint.
            duplicate.delete()
            MigrationExecutor(connection).migrate(self.migrate_to)
            self.assertEqual(Review.objects.count(), 1)
        finally:
            # Ensure later tests see the current schema even if an assertion fails.
            apps = MigrationExecutor(connection).loader.project_state(self.migrate_from).apps
            Review = apps.get_model('reviews', 'Review')
            # These are disposable rows in the isolated test database.
            Review.objects.all().delete()
            MigrationExecutor(connection).migrate(self.migrate_to)
