from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dashboard.audit import DecisionError
from dashboard.models import AuditRecord
from .forms import VideoForm
from .models import Video
from .services import save_video, set_publication
from .youtube import youtube_video_id


class YouTubeLinkTests(SimpleTestCase):
    def test_supported_links_extract_only_the_video_id(self):
        links = [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtube.com/watch?v=dQw4w9WgXcQ&t=30',
            'https://m.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ?si=share-code',
            'https://www.youtube.com/shorts/dQw4w9WgXcQ',
            'https://youtube.com/live/dQw4w9WgXcQ',
            'https://youtube.com/embed/dQw4w9WgXcQ',
        ]
        for link in links:
            with self.subTest(link=link):
                self.assertEqual(youtube_video_id(link), 'dQw4w9WgXcQ')

    def test_untrusted_hosts_scripts_playlists_and_malformed_ids_are_rejected(self):
        links = [
            'javascript:alert(1)', 'https://example.com/watch?v=dQw4w9WgXcQ',
            'https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ',
            'https://youtube.com@evil.example/watch?v=dQw4w9WgXcQ',
            'https://user:password@youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtube.com:8000/watch?v=dQw4w9WgXcQ',
            'https://youtube.com:bad/watch?v=dQw4w9WgXcQ',
            'https://youtube.com/playlist?list=test', 'https://youtu.be/too-short',
            'https://youtube.com/watch?v=dQw4w9WgXcQ&v=anotherId01',
            'https://youtu.be/dQw4w9WgXcQ/extra',
            'https://youtube.com/watch?v=bad%22%3Escript', '',
        ]
        for link in links:
            with self.subTest(link=link), self.assertRaises(ValidationError):
                youtube_video_id(link)


class VideoFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('agro-owner', 'owner@example.com', 'Agro-pass-943!')
        cls.catalogue = User.objects.create_user('agro-catalogue', is_staff=True)
        cls.catalogue.groups.add(Group.objects.create(name='Catalogue'))
        cls.finance = User.objects.create_user('agro-finance', is_staff=True)
        cls.finance.groups.add(Group.objects.create(name='Finance'))
        cls.staff = User.objects.create_user('agro-staff', is_staff=True)
        cls.farmer = User.objects.create_user('agro-farmer', seller_approved=True)
        cls.data = {
            'title': 'ধান চাষের ব্যবহারিক পরামর্শ', 'youtube_url': 'https://youtu.be/dQw4w9WgXcQ',
            'summary': 'কৃষকের জন্য একটি ভিডিও গাইড।', 'channel_name': 'Example farming channel',
            'category': 'crops', 'language': 'bn', 'source_published_on': None,
            'is_published': False, 'featured': False,
        }

    def video(self, **changes):
        return save_video(actor=self.owner, data=dict(self.data, **changes))

    def post_data(self, **changes):
        values = dict(self.data, **changes)
        values['source_published_on'] = values['source_published_on'] or ''
        return {key: value for key, value in values.items() if value is not False}


class VideoServiceTests(VideoFixtures):
    def test_draft_creation_normalizes_url_and_audits_actor(self):
        video = self.video()
        self.assertEqual(video.youtube_url, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(video.video_id, 'dQw4w9WgXcQ')
        self.assertIsNone(video.published_at)
        self.assertEqual(video.created_by, self.owner)
        audit = AuditRecord.objects.get()
        self.assertEqual(audit.actor, self.owner)
        self.assertEqual(audit.action, 'agro_video.create')
        self.assertEqual(audit.target, f'agro_updates.video:{video.pk}')

    def test_publish_unpublish_and_repeat_rules(self):
        video = self.video()
        set_publication(video.pk, actor=self.catalogue, published=True)
        video.refresh_from_db()
        self.assertIsNotNone(video.published_at)
        original_date = video.published_at
        with self.assertRaisesMessage(DecisionError, 'already published'):
            set_publication(video.pk, actor=self.owner, published=True)
        set_publication(video.pk, actor=self.catalogue, published=False)
        with self.assertRaisesMessage(DecisionError, 'already a draft'):
            set_publication(video.pk, actor=self.owner, published=False)
        set_publication(video.pk, actor=self.owner, published=True)
        video.refresh_from_db()
        self.assertEqual(video.published_at, original_date)
        self.assertEqual(AuditRecord.objects.count(), 4)

    def test_editor_can_update_and_preserves_original_author(self):
        video = self.video()
        updated = save_video(actor=self.catalogue, video_id=video.pk,
                             data=dict(self.data, title='Updated farming guide', is_published=True))
        self.assertEqual(updated.title, 'Updated farming guide')
        self.assertEqual(updated.created_by, self.owner)
        self.assertEqual(updated.updated_by, self.catalogue)
        self.assertIsNotNone(updated.published_at)
        self.assertEqual(AuditRecord.objects.filter(action='agro_video.edit').count(), 1)

    def test_same_video_in_different_url_formats_cannot_be_added_twice(self):
        self.video()
        with self.assertRaises(ValidationError):
            self.video(youtube_url='https://youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(Video.objects.count(), 1)
        self.assertEqual(AuditRecord.objects.count(), 1)
        form = VideoForm(data=self.post_data(youtube_url='https://youtube.com/shorts/dQw4w9WgXcQ'))
        self.assertFalse(form.is_valid())
        self.assertIn('youtube_url', form.errors)

    def test_service_denies_non_editors(self):
        video = self.video()
        for actor in [self.finance, self.staff, self.farmer]:
            with self.assertRaises(DecisionError):
                save_video(actor=actor, data=self.data)
            with self.assertRaises(DecisionError):
                set_publication(video.pk, actor=actor, published=True)
        self.assertEqual(AuditRecord.objects.count(), 1)

    def test_failed_audit_rolls_back_publication(self):
        video = self.video()
        with patch('agro_updates.services.record_action', side_effect=RuntimeError('Audit unavailable')):
            with self.assertRaises(RuntimeError):
                set_publication(video.pk, actor=self.owner, published=True)
        video.refresh_from_db()
        self.assertFalse(video.is_published)
        self.assertIsNone(video.published_at)


class PublicVideoTests(VideoFixtures):
    def test_public_page_has_empty_state_and_navigation_link(self):
        response = self.client.get(reverse('agro_updates:index'))
        self.assertContains(response, 'Fresh knowledge is on its way')
        self.assertContains(response, 'href="/agro-updates/"')
        self.assertNotContains(response, 'Manage videos')

    def test_only_published_videos_and_publication_dates_are_visible(self):
        draft = self.video()
        self.assertNotContains(self.client.get(reverse('agro_updates:index')), draft.title)
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
        set_publication(draft.pk, actor=self.owner, published=True)
        response = self.client.get(reverse('agro_updates:index'))
        self.assertContains(response, draft.title)
        self.assertContains(response, 'https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg')
        Video.objects.filter(pk=draft.pk).update(published_at=timezone.now()+timedelta(days=1))
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)

    def test_detail_uses_known_embed_host_and_youtube_fallback(self):
        video = self.video(is_published=True)
        response = self.client.get(video.get_absolute_url())
        self.assertContains(response, 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertContains(response, 'Watch on YouTube')
        self.assertContains(response, 'Example farming channel')
        self.assertNotContains(response, 'autoplay=1')
        set_publication(video.pk, actor=self.owner, published=False)
        self.assertEqual(self.client.get(video.get_absolute_url()).status_code, 404)

    def test_public_search_topic_and_language_filters(self):
        video = self.video(is_published=True)
        url = reverse('agro_updates:index')
        for query in [{'q': 'ধান'}, {'q': 'Example'}, {'category': 'crops'}, {'language': 'bn'}]:
            self.assertContains(self.client.get(url, query), video.title)
        for query in [{'q': 'missing'}, {'category': 'news'}, {'language': 'en'}]:
            self.assertNotContains(self.client.get(url, query), video.title)
        self.assertEqual(self.client.get(url, {'category': 'invalid'}).status_code, 200)

    def test_pagination_keeps_search_and_language(self):
        self.video(is_published=True)
        now = timezone.now()
        Video.objects.bulk_create([Video(title=f'Guide {i}', summary='farming', category='crops',
                                         language='bn', video_id=f'Agro{i:07d}',
                                         youtube_url=f'https://www.youtube.com/watch?v=Agro{i:07d}',
                                         is_published=True, published_at=now) for i in range(10)])
        url = reverse('agro_updates:index')
        response = self.client.get(url, {'q':'farming', 'language':'bn'})
        self.assertEqual(len(response.context['page_obj']), 9)
        self.assertContains(response, 'q=farming&amp;language=bn&amp;page=2')
        self.assertEqual(len(self.client.get(url, {'q':'farming', 'language':'bn', 'page':2}).context['page_obj']), 2)
        self.assertEqual(self.client.get(url, {'page':'garbage'}).context['page_obj'].number, 1)

    def test_content_is_escaped_and_public_endpoints_are_read_only(self):
        video = self.video(title='<script>alert(1)</script>', is_published=True)
        response = self.client.get(video.get_absolute_url())
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(self.client.post(reverse('agro_updates:index')).status_code, 405)
        self.assertEqual(self.client.post(video.get_absolute_url()).status_code, 405)


class EditorVideoTests(VideoFixtures):
    def test_management_access_and_navigation_by_role(self):
        for user, expected in [(self.owner,200), (self.catalogue,200), (self.finance,403), (self.staff,403), (self.farmer,403)]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('dashboard:agro_videos')).status_code, expected)
            self.assertEqual(self.client.get(reverse('dashboard:agro_video_create')).status_code, expected)
            response = self.client.get(reverse('agro_updates:index'))
            checker = self.assertContains if expected == 200 else self.assertNotContains
            checker(response, 'Manage videos')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard:agro_videos')).status_code, 403)

    def test_editor_creates_published_video_and_edits_with_forms(self):
        self.client.force_login(self.catalogue)
        response = self.client.post(reverse('dashboard:agro_video_create'), self.post_data(is_published='on', next='https://evil.example'))
        self.assertRedirects(response, reverse('dashboard:agro_videos'))
        video = Video.objects.get()
        self.assertTrue(video.is_published)
        response = self.client.post(reverse('dashboard:agro_video_edit', args=[video.pk]), self.post_data(title='Edited title'))
        self.assertRedirects(response, reverse('dashboard:agro_videos'))
        video.refresh_from_db()
        self.assertEqual(video.title, 'Edited title')
        self.assertFalse(video.is_published)
        self.assertEqual(AuditRecord.objects.count(), 2)

    def test_bad_url_and_duplicate_return_form_errors_without_save(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('dashboard:agro_video_create'), self.post_data(youtube_url='https://evil.example/video'))
        self.assertContains(response, 'Enter a valid YouTube video link')
        self.assertFalse(Video.objects.exists())
        self.video()
        response = self.client.post(reverse('dashboard:agro_video_create'), self.post_data())
        self.assertContains(response, 'already been added')
        self.assertEqual(Video.objects.count(), 1)

    def test_publication_actions_require_post_and_csrf(self):
        video = self.video()
        self.client.force_login(self.owner)
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.owner)
        for decision in ['publish', 'unpublish']:
            url = reverse('dashboard:agro_video_publication', args=[video.pk, decision])
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(secured.post(url).status_code, 403)
        url = reverse('dashboard:agro_video_create')
        self.assertEqual(secured.post(url, self.post_data()).status_code, 403)
        secured.get(url)
        token = secured.cookies['csrftoken'].value
        response = secured.post(reverse('dashboard:agro_video_publication', args=[video.pk,'publish']), {'csrfmiddlewaretoken':token})
        self.assertEqual(response.status_code, 302)
        video.refresh_from_db()
        self.assertTrue(video.is_published)

    def test_other_roles_cannot_mutate_even_with_direct_requests(self):
        video = self.video()
        for user in [self.finance, self.staff, self.farmer]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('dashboard:agro_video_create'), self.post_data()).status_code, 403)
            self.assertEqual(self.client.post(reverse('dashboard:agro_video_edit', args=[video.pk]), self.post_data()).status_code, 403)
            self.assertEqual(self.client.post(reverse('dashboard:agro_video_publication', args=[video.pk,'publish'])).status_code, 403)
        video.refresh_from_db()
        self.assertFalse(video.is_published)

    def test_admin_routes_owner_to_audited_front_end_forms(self):
        video = self.video()
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.get(reverse('admin:agro_updates_video_add')), reverse('dashboard:agro_video_create'))
        self.assertRedirects(self.client.get(reverse('admin:agro_updates_video_change', args=[video.pk])), reverse('dashboard:agro_video_edit', args=[video.pk]))

    def test_dashboard_list_is_paginated_and_filters_publication(self):
        now = timezone.now()
        Video.objects.bulk_create([Video(title=f'Video {i}', video_id=f'Agro{i:07d}',
                                         youtube_url=f'https://www.youtube.com/watch?v=Agro{i:07d}',
                                         is_published=True, published_at=now) for i in range(26)])
        self.client.force_login(self.catalogue)
        response = self.client.get(reverse('dashboard:agro_videos'))
        self.assertEqual(len(response.context['page_obj']), 25)
        response = self.client.get(reverse('dashboard:agro_videos'), {'page':2})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(self.client.get(reverse('dashboard:agro_videos'), {'tab':'draft'}), 'No videos in this tab')
