
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from notifications.models import Notification


class NotificationTests(TestCase):
    def setUp(self):
        self.client_role, _ = Role.objects.get_or_create(
            name=Role.CLIENT
        )
        self.staff_role, _ = Role.objects.get_or_create(
            name=Role.STAFF
        )

        self.user = User.objects.create_user(
            username="notification_client",
            email="client@example.com",
            password="TestPassword123!",
            role=self.client_role,
        )

        self.other_user = User.objects.create_user(
            username="notification_staff",
            email="staff@example.com",
            password="TestPassword123!",
            role=self.staff_role,
        )

        self.notification = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.LOAN_APPROVED,
            message="Your loan application has been approved.",
        )

        self.other_notification = Notification.objects.create(
            user=self.other_user,
            kind=Notification.Kind.LOAN_DISBURSED,
            message="Your loan has been disbursed.",
        )

    def test_notification_creation(self):
        self.assertEqual(self.notification.user, self.user)
        self.assertEqual(
            self.notification.kind,
            Notification.Kind.LOAN_APPROVED,
        )
        self.assertFalse(self.notification.is_read)

    def test_notification_string_representation(self):
        self.assertIn(
            self.notification.get_kind_display(),
            str(self.notification),
        )

    def test_notifications_are_ordered_newest_first(self):
        newer_notification = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.LOAN_PAYMENT_RECORDED,
            message="A loan payment was recorded.",
        )

        notifications = list(
            Notification.objects.filter(user=self.user)
        )

        self.assertEqual(notifications[0], newer_notification)

    def test_client_can_view_own_notifications(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("notification_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.notification.message)
        self.assertNotContains(
            response,
            self.other_notification.message,
        )

    def test_staff_can_view_own_notifications(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse("notification_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.other_notification.message,
        )

    def test_user_can_mark_own_notification_as_read(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "mark_notification_read",
                args=[self.notification.pk],
            )
        )

        self.notification.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("notification_list"),
        )
        self.assertTrue(self.notification.is_read)

    def test_user_cannot_mark_another_users_notification_as_read(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "mark_notification_read",
                args=[self.other_notification.pk],
            )
        )

        self.other_notification.refresh_from_db()

        self.assertFalse(self.other_notification.is_read)
        self.assertIn(response.status_code, [302, 403, 404])

    def test_user_can_mark_all_own_notifications_as_read(self):
        second_notification = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.INSTALLMENT_OVERDUE,
            message="Your loan installment is overdue.",
        )

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("mark_all_notifications_read")
        )

        self.notification.refresh_from_db()
        second_notification.refresh_from_db()
        self.other_notification.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("notification_list"),
        )
        self.assertTrue(self.notification.is_read)
        self.assertTrue(second_notification.is_read)
        self.assertFalse(self.other_notification.is_read)

    def test_notification_actions_require_post(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "mark_notification_read",
                args=[self.notification.pk],
            )
        )

        self.assertEqual(response.status_code, 405)

    def test_unread_notification_count(self):
        self.assertEqual(
            Notification.objects.filter(
                user=self.user,
                is_read=False,
            ).count(),
            1,
        )

        self.notification.is_read = True
        self.notification.save(update_fields=["is_read"])

        self.assertEqual(
            Notification.objects.filter(
                user=self.user,
                is_read=False,
            ).count(),
            0,
        )
