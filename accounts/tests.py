from django.contrib.auth import SESSION_KEY
from django.test import Client, TestCase
from django.urls import reverse

from .models import User


class LogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('logout-buyer', password='Logout-test-943!')
        cls.other = User.objects.create_user('logout-other', password='Logout-test-943!')

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def confirm_data(self):
        token = self.client.get(reverse('logout_token')).json()['csrfToken']
        return {'csrfmiddlewaretoken': token, 'confirm': 'yes', 'user_id': self.user.pk}

    def test_logout_links_open_confirmation_without_signing_out(self):
        response = self.client.get(reverse('logout'))
        self.assertContains(response, 'Yes, log out')
        self.assertContains(response, 'Cancel')
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertIn('no-store', response.headers['Cache-Control'])
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'href="/logout/"', count=2)
        self.assertNotContains(response, 'action="/logout/"')

    def test_confirmed_logout_uses_post_and_valid_csrf(self):
        self.assertRedirects(self.client.post(reverse('logout'), self.confirm_data()), reverse('login'))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_missing_or_invalid_csrf_does_not_sign_out(self):
        self.client.get(reverse('logout'))
        for token in ['', 'incorrect-token', 'A' * 64]:
            response = self.client.post(reverse('logout'),
                                        {'csrfmiddlewaretoken': token, 'confirm': 'yes', 'user_id': self.user.pk})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_post_without_confirmation_keeps_user_signed_in(self):
        data = self.confirm_data()
        del data['confirm']
        self.assertRedirects(self.client.post(reverse('logout'), data), reverse('logout'))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_different_account_requires_new_confirmation(self):
        data = self.confirm_data()
        self.client.force_login(self.other)
        self.assertRedirects(self.client.post(reverse('logout'), data), reverse('logout'))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.other.pk))

    def test_rotated_csrf_token_can_be_refreshed_without_signing_out(self):
        self.client.get(reverse('logout'))
        old_token = self.client.cookies['csrftoken'].value
        # Logging in again simulates another tab rotating the shared CSRF cookie.
        login_response = self.client.post(reverse('login'), {
            'csrfmiddlewaretoken': old_token, 'username': self.user.username,
            'password': 'Logout-test-943!',
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertNotEqual(self.client.cookies['csrftoken'].value, old_token)
        stale = self.client.post(reverse('logout'), {
            'csrfmiddlewaretoken': old_token, 'confirm': 'yes', 'user_id': self.user.pk,
        })
        self.assertEqual(stale.status_code, 403)
        data = self.confirm_data()
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertRedirects(self.client.post(reverse('logout'), data), reverse('login'))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_token_refresh_is_not_cached_and_only_accepts_get(self):
        response = self.client.get(reverse('logout_token'))
        self.assertEqual(response.json()['userId'], self.user.pk)
        self.assertEqual(len(response.json()['csrfToken']), 64)
        self.assertIn('no-store', response.headers['Cache-Control'])
        # Valid CSRF is supplied so the method check itself is exercised.
        self.assertEqual(self.client.post(reverse('logout_token'),
                                          {'csrfmiddlewaretoken': response.json()['csrfToken']}).status_code, 405)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_already_signed_out_is_handled_without_a_token(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('logout_token')).json(), {'signedOut': True})
        self.assertEqual(self.client.get(reverse('logout')).status_code, 302)
