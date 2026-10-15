import io
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.contrib import admin
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import User
from . import ollama
from .models import Conversation, Message
from .services import ChatError, ask, clear_history, history_for, store_turn


@override_settings(OLLAMA_MODEL='qwen3:1.7b')
class LocalClientTests(SimpleTestCase):
    def opener_response(self, value):
        response = MagicMock()
        response.read.return_value = json.dumps(value).encode()
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        return opener

    @override_settings(AI_CHAT_ENABLED=True, OLLAMA_BASE_URL='http://127.0.0.1:11434', OLLAMA_MODEL='qwen3:1.7b')
    @patch('chatbot.ollama.build_opener')
    def test_request_uses_local_model_bounded_context_and_no_streaming(self, build_opener):
        opener = self.opener_response({'message': {'content': 'সহজভাবে কম্পোস্ট তৈরি করা যায়।'}})
        build_opener.return_value = opener
        history = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'past ' + str(i)} for i in range(10)]
        answer = ollama.reply('কম্পোস্ট কী?', history)
        self.assertEqual(answer, 'সহজভাবে কম্পোস্ট তৈরি করা যায়।')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/chat')
        payload = json.loads(request.data)
        self.assertFalse(payload['stream'])
        self.assertFalse(payload['think'])
        self.assertEqual(payload['model'], 'qwen3:1.7b')
        self.assertEqual(payload['messages'][0]['role'], 'system')
        self.assertEqual(payload['messages'][1]['content'], 'past 4')
        self.assertEqual(payload['messages'][-1]['content'], 'কম্পোস্ট কী?')
        self.assertEqual(len(payload['messages']), 8)
        self.assertIn('write in Bangla', payload['messages'][0]['content'])
        self.assertEqual(payload['options']['repeat_penalty'], 1.15)
        self.assertEqual(payload['options']['repeat_last_n'], 256)
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 120)

    @override_settings(AI_CHAT_ENABLED=True, OLLAMA_MODEL='qwen3:1.7b')
    def test_remote_urls_credentials_paths_and_https_are_not_allowed(self):
        for base in ['https://ollama.com', 'http://example.com', 'http://localhost.evil.test',
                     'http://user:pass@127.0.0.1', 'http://127.0.0.1/api',
                     'http://localhost:bad', 'http://localhost?redirect=external']:
            with self.subTest(base=base), override_settings(OLLAMA_BASE_URL=base):
                with self.assertRaises(ollama.LocalAIError), patch('chatbot.ollama.build_opener') as opener:
                    ollama.reply('Hello', [])
                opener.assert_not_called()

    @override_settings(AI_CHAT_ENABLED=False)
    @patch('chatbot.ollama.build_opener')
    def test_disabled_chat_does_not_make_network_requests(self, opener):
        with self.assertRaises(ollama.LocalAIError) as error:
            ollama.reply('Hello', [])
        self.assertEqual(error.exception.code, 'disabled')
        self.assertEqual(ollama.status()['code'], 'disabled')
        opener.assert_not_called()

    @override_settings(AI_CHAT_ENABLED=True, OLLAMA_BASE_URL='http://localhost:11434')
    def test_cloud_and_unknown_model_names_are_rejected(self):
        for model in ['qwen3:cloud', 'some-model:480b-cloud', 'gpt-paid-api']:
            with override_settings(OLLAMA_MODEL=model), self.assertRaises(ollama.LocalAIError):
                ollama.configuration()

    @patch('chatbot.ollama.build_opener')
    def test_offline_timeout_and_missing_model_have_clear_errors(self, build_opener):
        opener = MagicMock()
        build_opener.return_value = opener
        for error, expected in [(URLError('connection refused'), 'offline'), (TimeoutError(), 'offline'),
                                (HTTPError('http://localhost', 404, 'Not found', {}, None), 'model_missing'),
                                (HTTPError('http://localhost', 500, 'Error', {}, None), 'unavailable')]:
            opener.open.side_effect = error
            with self.assertRaises(ollama.LocalAIError) as result:
                ollama.reply('Question', [])
            self.assertEqual(result.exception.code, expected)

    @patch('chatbot.ollama.build_opener')
    def test_invalid_empty_and_oversized_model_replies_are_rejected(self, build_opener):
        for payload in [[], {'message': None}, {'message': {'content': ''}}, {'message': {'content': 42}}]:
            build_opener.return_value = self.opener_response(payload)
            with self.assertRaises(ollama.LocalAIError):
                ollama.reply('Question', [])
        opener = self.opener_response({})
        opener.open.return_value.read.return_value = b'x' * (ollama.RESPONSE_LIMIT + 1)
        build_opener.return_value = opener
        with self.assertRaises(ollama.LocalAIError):
            ollama.reply('Question', [])

    @patch('chatbot.ollama.request_json')
    def test_connection_check_distinguishes_ready_and_missing_model(self, request_json):
        request_json.return_value = {'models': [{'name': 'qwen3:1.7b'}]}
        self.assertTrue(ollama.status()['ready'])
        request_json.return_value = {'models': []}
        self.assertEqual(ollama.status()['code'], 'model_missing')
        request_json.return_value = {'models': 'invalid'}
        self.assertEqual(ollama.status()['code'], 'bad_response')


@override_settings(OLLAMA_MODEL='qwen3:1.7b')
class ReplyQualityGuardTests(SimpleTestCase):
    @patch('chatbot.ollama.request_json', return_value={'message': {'content': 'Check soil drainage and pH before planting.'}})
    def test_latest_english_question_overrides_previous_bangla_context(self, request_json):
        ollama.reply('What should I check before preparing soil?', [
            {'role': 'user', 'content': 'কম্পোস্ট কী?'},
            {'role': 'assistant', 'content': 'কম্পোস্ট মাটির জৈব উপাদান বাড়াতে সাহায্য করে।'},
        ])
        payload = request_json.call_args.kwargs['payload']
        self.assertIn('write in English', payload['messages'][0]['content'])
        self.assertEqual(len(payload['messages']), 4)

    def test_repeated_bangla_sentences_from_report_are_detected(self):
        answer = ('টোমাটো লেব লাল হওয়া বা সাধারণ কম্পোস্ট তৈরি করার পর জমি কাশার করার সময় কী পরীক্ষা হয়?\n' * 2)
        self.assertTrue(ollama.is_repetitive(answer))

    def test_repeated_english_phrases_without_line_breaks_are_detected(self):
        self.assertTrue(ollama.is_repetitive('Check the soil before planting and check the drainage. ' * 5))

    def test_normal_answers_and_short_repeated_terms_are_allowed(self):
        for answer in [
            'Soil pH matters. Soil drainage matters too.',
            'Check drainage first. Then check the soil pH and organic matter. '
            'Different crops need different conditions, so tell me which vegetables you want to grow '
            'and whether water stays on the soil after rain.',
            'মাটি ঝুরঝুরে আছে কি না দেখুন। পানি জমে থাকে কি না পরীক্ষা করুন। '
            'কোন সবজি চাষ করবেন এবং আপনার জমি কোন জেলায় আছে জানালে আরও নির্দিষ্টভাবে বলা যাবে।',
        ]:
            with self.subTest(answer=answer):
                self.assertFalse(ollama.is_repetitive(answer))

    @patch('chatbot.ollama.request_json')
    def test_bad_previous_answer_is_excluded_without_mutating_saved_context(self, request_json):
        request_json.return_value = {'message': {'content': 'Several things can cause yellow leaves, including water stress.'}}
        history = [{'role': 'user', 'content': 'Old question'},
                   {'role': 'assistant', 'content': 'Check the soil before planting and check the drainage. ' * 5}]
        ollama.reply('Why are tomato leaves yellow?', history)
        self.assertEqual(len(request_json.call_args.kwargs['payload']['messages']), 2)
        self.assertEqual(len(history), 2)

    @patch('chatbot.ollama.request_json')
    def test_generation_loop_is_rejected_with_no_automatic_retry(self, request_json):
        request_json.return_value = {'message': {'content': 'Check the soil before planting and check the drainage. ' * 5}}
        with self.assertRaises(ollama.LocalAIError) as error:
            ollama.reply('What soil checks should I do?', [])
        self.assertEqual(error.exception.code, 'repetitive_response')
        request_json.assert_called_once()

    @patch('chatbot.ollama.request_json')
    def test_question_echo_is_rejected(self, request_json):
        question = 'What should I check before preparing soil for vegetables?'
        request_json.return_value = {'message': {'content': question}}
        with self.assertRaises(ollama.LocalAIError) as error:
            ollama.reply(question, [])
        self.assertEqual(error.exception.code, 'repetitive_response')

    @override_settings(OLLAMA_MODEL='qwen3:4b')
    def test_larger_local_model_is_supported(self):
        self.assertEqual(ollama.configuration()[1], 'qwen3:4b')


class ChatFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('chat-farmer', seller_approved=True)
        cls.other = User.objects.create_user('other-chat-farmer')

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    def post(self, message='How do I compost?', **extra):
        return self.client.post(reverse('chatbot:send'), {'message': message, **extra}, HTTP_ACCEPT='application/json')


class ChatHistoryTests(ChatFixtures):
    @patch('chatbot.ollama.reply', return_value='Start with plant waste and keep it moist.')
    def test_successful_turn_is_private_and_survives_page_reload(self, reply):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['role'] for row in response.json()['messages']], ['user', 'assistant'])
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(Conversation.objects.get().user, self.user)
        self.assertContains(self.client.get(reverse('chatbot:chat')), 'Start with plant waste')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('chatbot:chat')), 'Start with plant waste')
        reply.assert_called_once_with('How do I compost?', [])

    @patch('chatbot.ollama.reply', return_value='Second answer')
    def test_only_current_users_messages_go_to_model(self, reply):
        store_turn(self.user, 0, 'My first question', 'My first answer')
        store_turn(self.other, 0, 'PRIVATE OTHER QUESTION', 'PRIVATE OTHER ANSWER')
        response = self.post('My next question')
        self.assertEqual(response.status_code, 200)
        sent = reply.call_args.args[1]
        self.assertEqual([row['content'] for row in sent], ['My first question', 'My first answer'])
        self.assertNotIn('PRIVATE OTHER', str(sent))
        self.assertEqual(len(response.json()['messages']), 4)

    @patch('chatbot.ollama.reply', side_effect=ollama.LocalAIError('Open Ollama first.', code='offline'))
    def test_provider_failure_does_not_create_fake_answers_or_partial_history(self, reply):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], 'Open Ollama first.')
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Conversation.objects.exists())

    @patch('chatbot.ollama.request_json')
    def test_repetitive_output_is_not_saved_or_sent_as_a_successful_answer(self, request_json):
        request_json.return_value = {'message': {'content': 'Check the soil before planting and check the drainage. ' * 5}}
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertIn('repeated text', response.json()['error'])
        self.assertFalse(Message.objects.exists())

    def test_clear_only_deletes_current_users_messages(self):
        store_turn(self.user, 0, 'Mine', 'My answer')
        store_turn(self.other, 0, 'Other', 'Other answer')
        response = self.client.post(reverse('chatbot:clear'), HTTP_ACCEPT='application/json')
        self.assertEqual(response.json(), {'messages': []})
        self.assertEqual(history_for(self.user), [])
        self.assertEqual(len(history_for(self.other)), 2)

    def test_clear_cannot_be_undone_by_in_flight_answer(self):
        def delayed_answer(question, history):
            clear_history(self.user)
            return 'Late response'
        with patch('chatbot.ollama.reply', side_effect=delayed_answer):
            response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Message.objects.exists())

    def test_stale_version_cannot_overwrite_newer_turn(self):
        store_turn(self.user, 0, 'First', 'First answer')
        with self.assertRaises(ChatError):
            store_turn(self.user, 0, 'Stale second', 'Stale answer')
        self.assertEqual(len(history_for(self.user)), 2)

    def test_retained_history_is_bounded_to_thirty_messages(self):
        for revision in range(18):
            store_turn(self.user, revision, f'Question {revision}', f'Answer {revision}')
        history = history_for(self.user)
        self.assertEqual(len(history), 30)
        self.assertEqual(history[0]['content'], 'Question 3')
        self.assertEqual(history[-1]['content'], 'Answer 17')

    def test_duplicate_in_flight_requests_are_rejected(self):
        cache.set(f'rootline-chat:busy:{self.user.pk}', 'existing-request', timeout=30)
        with patch('chatbot.ollama.reply') as reply:
            response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '5')
        reply.assert_not_called()
        self.assertEqual(cache.get(f'rootline-chat:busy:{self.user.pk}'), 'existing-request')

    def test_busy_marker_is_removed_when_generation_fails(self):
        with patch('chatbot.ollama.reply', side_effect=ollama.LocalAIError('Offline')):
            self.post()
        self.assertIsNone(cache.get(f'rootline-chat:busy:{self.user.pk}'))


class ChatViewTests(ChatFixtures):
    def test_page_is_login_required_and_get_does_not_create_history(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('chatbot:chat')).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(reverse('chatbot:chat'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertContains(response, 'Ask RootLine')
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Message.objects.exists())

    def test_mutations_are_post_only_and_require_login(self):
        for route in ['send', 'clear']:
            url = reverse('chatbot:' + route)
            for method in ['get', 'put', 'delete', 'patch']:
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)
            self.client.logout()
            response = self.client.post(url, {'message': 'Question'}, HTTP_ACCEPT='application/json')
            self.assertEqual(response.status_code, 401)
            self.client.force_login(self.user)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('chatbot:status')).status_code, 401)

    def test_send_and_clear_require_valid_csrf(self):
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.user)
        for route in ['send', 'clear']:
            self.assertEqual(secured.post(reverse('chatbot:'+route), {'message':'Hello'}).status_code, 403)
        secured.get(reverse('chatbot:chat'))
        token = secured.cookies['csrftoken'].value
        with patch('chatbot.ollama.reply', return_value='Hello farmer'):
            response = secured.post(reverse('chatbot:send'), {'message':'Hello','csrfmiddlewaretoken':token}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(secured.post(reverse('chatbot:clear'), {'csrfmiddlewaretoken':token}, HTTP_ACCEPT='application/json').status_code, 200)

    def test_empty_and_oversized_questions_are_rejected_without_model_call(self):
        with patch('chatbot.ollama.reply') as reply:
            for text in ['', '   ', 'x' * 2001]:
                self.assertEqual(self.post(text).status_code, 400)
        reply.assert_not_called()
        self.assertFalse(Message.objects.exists())

    @patch('chatbot.ollama.reply', return_value='A simple answer')
    def test_non_javascript_forms_work_and_next_is_ignored(self, reply):
        response = self.client.post(reverse('chatbot:send'), {'message':'Question','next':'https://evil.example'})
        self.assertRedirects(response, reverse('chatbot:chat'))
        response = self.client.post(reverse('chatbot:clear'), {'next':'https://evil.example'})
        self.assertRedirects(response, reverse('chatbot:chat'))
        self.assertFalse(Message.objects.exists())

    def test_user_and_model_html_are_escaped(self):
        store_turn(self.user, 0, '<script>alert(1)</script>', '<img src=x onerror=alert(1)>')
        response = self.client.get(reverse('chatbot:chat'))
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertContains(response, '&lt;img src=x onerror=alert(1)&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotContains(response, '<img src=x onerror=alert(1)>')

    @override_settings(AI_CHAT_ENABLED=False)
    def test_disabled_chat_has_no_provider_calls(self):
        with patch('chatbot.ollama.build_opener') as opener:
            self.assertEqual(self.post().status_code, 503)
            self.assertEqual(self.client.get(reverse('chatbot:status')).json()['code'], 'disabled')
        opener.assert_not_called()
        self.assertContains(self.client.get(reverse('chatbot:chat')), 'AI chat is switched off')

    def test_navigation_and_profile_have_chat_links(self):
        self.assertContains(self.client.get(reverse('profile')), 'href="/ask-rootline/"', count=2)
        self.assertContains(self.client.get(reverse('agro_updates:index')), 'href="/ask-rootline/"')

    def test_private_messages_are_not_in_staff_admin(self):
        self.assertNotIn(Conversation, admin.site._registry)
        self.assertNotIn(Message, admin.site._registry)

    @patch('chatbot.ollama.status', return_value={'ready':True,'code':'ready','model':'qwen3:1.7b','message':'Ready'})
    def test_connection_check_is_get_only(self, status):
        self.assertTrue(self.client.get(reverse('chatbot:status')).json()['ready'])
        self.assertEqual(self.client.post(reverse('chatbot:status')).status_code, 405)


@override_settings(OLLAMA_MODEL='qwen3:1.7b')
class LocalHTTPIntegrationTests(SimpleTestCase):
    """Exercise HTTP/JSON behavior with a local protocol fixture, not a real AI model."""
    @contextmanager
    def server(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'models':[{'name':'qwen3:1.7b'}]}).encode())
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'message':{'content':'Protocol test response'}}, ensure_ascii=False).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with override_settings(OLLAMA_BASE_URL=f'http://127.0.0.1:{server.server_port}'):
                yield captured
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_real_loopback_http_chat_and_health_requests(self):
        with self.server() as captured:
            self.assertTrue(ollama.status()['ready'])
            self.assertEqual(ollama.reply('বাংলা প্রশ্ন', []), 'Protocol test response')
            self.assertEqual(captured[0]['messages'][-1]['content'], 'বাংলা প্রশ্ন')

    def test_redirect_to_a_non_local_server_is_not_followed(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.send_response(307)
                self.send_header('Location', 'https://example.com/collect')
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with override_settings(OLLAMA_BASE_URL=f'http://127.0.0.1:{server.server_port}'):
                with self.assertRaises(ollama.LocalAIError):
                    ollama.reply('Local question', [])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    @patch('chatbot.management.commands.check_ollama.status', return_value={'ready':True,'model':'qwen3:1.7b'})
    def test_check_command_reports_ready(self, status):
        out = io.StringIO()
        call_command('check_ollama', stdout=out)
        self.assertIn('Ready: qwen3:1.7b', out.getvalue())

    @patch('chatbot.management.commands.check_ollama.status', return_value={'ready':False,'message':'Open Ollama first'})
    def test_check_command_fails_clearly_when_offline(self, status):
        with self.assertRaisesMessage(CommandError, 'Open Ollama first'):
            call_command('check_ollama', stdout=io.StringIO())


class ConcurrentChatHistoryTests(TransactionTestCase):
    def test_competing_turns_only_one_can_write_the_same_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connection, connections
        if connection.vendor == 'sqlite' and connection.creation.is_in_memory_db(connection.settings_dict['NAME']):
            self.skipTest('Use ROOTLINE_TEST_DB=work/rootline-chat-tests.sqlite3 to exercise file locking.')
        user = User.objects.create_user('concurrent-chat-user')
        barrier = threading.Barrier(2)
        def write_turn(label):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    store_turn(user, 0, label, 'Answer ' + label)
                    return 'saved'
                except ChatError:
                    return 'conflict'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(write_turn, ['one', 'two']))
        self.assertCountEqual(result, ['saved', 'conflict'])
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(Conversation.objects.get(user=user).revision, 1)
