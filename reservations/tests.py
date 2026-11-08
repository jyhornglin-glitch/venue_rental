import json
import base64
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Venue, Reservation, UserProfile


class FullSystemIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. 建立最高管理者 (Superadmin)
        self.superadmin = User.objects.create_superuser(
            username='superadmin',
            email='super@example.com',
            password='superpassword'
        )

        # 2. 建立管理者 (Admin)
        self.admin = User.objects.create_user(
            username='venue_admin',
            email='admin@example.com',
            password='adminpassword',
            is_staff=True
        )
        self.admin.profile.role = UserProfile.Role.ADMIN
        self.admin.profile.save()

        # 3. 建立一般申請者 (User)
        self.applicant = User.objects.create_user(
            username='applicant',
            email='user@example.com',
            password='userpassword'
        )

        # 4. 建立初始場地
        self.venue1 = Venue.objects.create(
            name='大型演講廳',
            capacity=200,
            location='A棟1F',
            is_active=True
        )
        self.venue2 = Venue.objects.create(
            name='維修中實驗室',
            capacity=30,
            location='C棟3F',
            is_active=False
        )

    def test_user_roles_initialization(self):
        self.assertEqual(self.superadmin.profile.role, UserProfile.Role.SUPERADMIN)
        self.assertTrue(self.superadmin.profile.is_superadmin)

        self.assertEqual(self.admin.profile.role, UserProfile.Role.ADMIN)
        self.assertTrue(self.admin.profile.is_admin_or_superadmin)

        self.assertEqual(self.applicant.profile.role, UserProfile.Role.USER)
        self.assertFalse(self.applicant.profile.is_admin_or_superadmin)

    def test_venue_acid_create(self):
        payload = {
            "name": "新世紀多功能廳",
            "capacity": 80,
            "location": "綜合大樓 4F",
            "description": "配備 4K 投影與視訊設備",
            "is_active": True
        }

        # 一般使用者嘗試建立場地 -> 403
        self.client.force_login(self.applicant)
        res = self.client.post('/api/venues/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # 管理者建立場地 (ACID 交易操作) -> 201
        self.client.force_login(self.admin)
        res = self.client.post('/api/venues/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 201)
        created_id = res.json()['id']
        new_venue = Venue.objects.get(id=created_id)
        self.assertEqual(new_venue.name, "新世紀多功能廳")

        # 測試 Consistency: 無效資料 (容納人數為 0) -> 400
        invalid_payload = payload.copy()
        invalid_payload["capacity"] = 0
        res_fail = self.client.post('/api/venues/', data=json.dumps(invalid_payload), content_type='application/json')
        self.assertEqual(res_fail.status_code, 400)

    def test_venue_acid_update(self):
        self.client.force_login(self.admin)

        # 更新場地容納人數與停用
        res = self.client.patch(
            f'/api/venues/{self.venue1.id}/',
            data=json.dumps({"capacity": 250, "is_active": False}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.venue1.refresh_from_db()
        self.assertEqual(self.venue1.capacity, 250)
        self.assertFalse(self.venue1.is_active)

    def test_venue_acid_delete_and_protection(self):
        # 1. 建立一筆預約綁定 venue1
        now = timezone.now()
        Reservation.objects.create(
            user=self.applicant,
            venue=self.venue1,
            start_time=now + timedelta(days=1, hours=2),
            end_time=now + timedelta(days=1, hours=4),
            reason='研討會'
        )

        self.client.force_login(self.admin)

        # 2. 嘗試刪除已有預約紀錄的場地 -> 400 (ProtectedError 攔截，資料完整性保護)
        res = self.client.delete(f'/api/venues/{self.venue1.id}/')
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Venue.objects.filter(id=self.venue1.id).exists())

        # 3. 刪除無預約的場地 venue2 -> 200
        res_del = self.client.delete(f'/api/venues/{self.venue2.id}/')
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(Venue.objects.filter(id=self.venue2.id).exists())

    def test_superadmin_role_management(self):
        # 1. 一般使用者無法查看或變更角色 -> 403
        self.client.force_login(self.applicant)
        res = self.client.get('/api/users/')
        self.assertEqual(res.status_code, 403)

        # 2. 管理者可查看名冊
        self.client.force_login(self.admin)
        res = self.client.get('/api/users/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 3)

        # 3. 管理者不能變更其他人的角色 -> 403
        res = self.client.patch(
            f'/api/users/{self.applicant.id}/role/',
            data=json.dumps({"role": UserProfile.Role.ADMIN}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 403)

        # 4. 最高管理者可升遷一般申請者為管理者 -> 200
        self.client.force_login(self.superadmin)
        res = self.client.patch(
            f'/api/users/{self.applicant.id}/role/',
            data=json.dumps({"role": UserProfile.Role.ADMIN}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.applicant.profile.refresh_from_db()
        self.assertEqual(self.applicant.profile.role, UserProfile.Role.ADMIN)
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_staff)

    def test_superadmin_create_user(self):
        # 1. 管理者無權新增人員 -> 403
        self.client.force_login(self.admin)
        res_fail = self.client.post(
            '/api/users/',
            data=json.dumps({
                "username": "new_manager",
                "password": "password123",
                "role": UserProfile.Role.ADMIN
            }),
            content_type='application/json'
        )
        self.assertEqual(res_fail.status_code, 403)

        # 2. 最高管理者新增管理者 (ADMIN) -> 201
        self.client.force_login(self.superadmin)
        res_admin = self.client.post(
            '/api/users/',
            data=json.dumps({
                "username": "new_manager",
                "password": "password123",
                "email": "manager@test.com",
                "phone": "0912345678",
                "role": UserProfile.Role.ADMIN
            }),
            content_type='application/json'
        )
        self.assertEqual(res_admin.status_code, 201)
        created_user = User.objects.get(username="new_manager")
        self.assertEqual(created_user.profile.role, UserProfile.Role.ADMIN)
        self.assertTrue(created_user.is_staff)

        # 3. 最高管理者新增一般申請者 (USER) -> 201
        res_user = self.client.post(
            '/api/users/',
            data=json.dumps({
                "username": "new_applicant",
                "password": "password123",
                "role": UserProfile.Role.USER
            }),
            content_type='application/json'
        )
        self.assertEqual(res_user.status_code, 201)
        applicant_user = User.objects.get(username="new_applicant")
        self.assertEqual(applicant_user.profile.role, UserProfile.Role.USER)
        self.assertFalse(applicant_user.is_staff)

        # 4. 重複帳號建立 -> 400
        res_dup = self.client.post(
            '/api/users/',
            data=json.dumps({
                "username": "new_manager",
                "password": "password123",
                "role": UserProfile.Role.USER
            }),
            content_type='application/json'
        )
        self.assertEqual(res_dup.status_code, 400)

    def test_venue_time_limited_closure(self):
        now = timezone.now()
        closure_start = now + timedelta(days=2, hours=10)
        closure_end = now + timedelta(days=2, hours=14)

        # 1. 管理者為 venue1 設定限定停用時段 (明天 10:00 ~ 14:00 設備保養)
        self.client.force_login(self.admin)
        res_close = self.client.post(
            f'/api/venues/{self.venue1.id}/closures/',
            data=json.dumps({
                "start_time": closure_start.isoformat(),
                "end_time": closure_end.isoformat(),
                "reason": "全面深層消毒清潔"
            }),
            content_type='application/json'
        )
        self.assertEqual(res_close.status_code, 201)
        closure_id = res_close.json()['id']

        # 2. 一般使用者嘗試在停用時段內預約 (11:00 ~ 13:00) -> 400 驗證失敗攔截
        self.client.force_login(self.applicant)
        res_book_fail = self.client.post(
            '/api/reservations/',
            data=json.dumps({
                "venue_id": self.venue1.id,
                "start_time": (now + timedelta(days=2, hours=11)).isoformat(),
                "end_time": (now + timedelta(days=2, hours=13)).isoformat(),
                "reason": "試圖在維修時段預約"
            }),
            content_type='application/json'
        )
        self.assertEqual(res_book_fail.status_code, 400)
        self.assertIn("已設定限定停用", str(res_book_fail.json()))

        # 3. 預約停用時段外的時間 (15:00 ~ 17:00) -> 201 成功
        res_book_ok = self.client.post(
            '/api/reservations/',
            data=json.dumps({
                "venue_id": self.venue1.id,
                "start_time": (now + timedelta(days=2, hours=15)).isoformat(),
                "end_time": (now + timedelta(days=2, hours=17)).isoformat(),
                "reason": "時段外正常預約"
            }),
            content_type='application/json'
        )
        self.assertEqual(res_book_ok.status_code, 201)

        # 4. 管理者解除停用時段 -> 200
        self.client.force_login(self.admin)
        res_del_closure = self.client.delete(f'/api/venues/{self.venue1.id}/closures/{closure_id}/')
        self.assertEqual(res_del_closure.status_code, 200)

        # 5. 解除後，該時段 (11:00 ~ 13:00) 即可重新被預約
        self.client.force_login(self.applicant)
        res_book_reopen = self.client.post(
            '/api/reservations/',
            data=json.dumps({
                "venue_id": self.venue1.id,
                "start_time": (now + timedelta(days=2, hours=11)).isoformat(),
                "end_time": (now + timedelta(days=2, hours=13)).isoformat(),
                "reason": "解除停用後正常預約"
            }),
            content_type='application/json'
        )
        self.assertEqual(res_book_reopen.status_code, 201)

    def test_unauthenticated_visitor_can_view_venue_and_rental_info(self):
        """測試未登入訪客可正常查詢場地資訊與場地租用資訊"""
        self.client.logout()

        # 1. 訪客查詢場地清單 (僅開放中場地) -> 200
        res_venues = self.client.get('/api/venues/')
        self.assertEqual(res_venues.status_code, 200)
        venues_data = res_venues.json()
        self.assertEqual(len(venues_data), 1)  # 僅 venue1 (is_active=True)，venue2 不會列出
        self.assertEqual(venues_data[0]['name'], '大型演講廳')
        self.assertIn('closures', venues_data[0])

        # 2. 訪客查詢單一場地詳情 -> 200
        res_detail = self.client.get(f'/api/venues/{self.venue1.id}/')
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.json()['name'], '大型演講廳')

        # 3. 訪客查詢場地停用維護時段 -> 200
        res_closures = self.client.get(f'/api/venues/{self.venue1.id}/closures/')
        self.assertEqual(res_closures.status_code, 200)

        # 4. 訪客不能新增場地或新增停用時段 -> 401
        res_post_venue = self.client.post(
            '/api/venues/',
            data=json.dumps({"name": "訪客企圖新增", "capacity": 10, "location": "1F"}),
            content_type='application/json'
        )
        self.assertEqual(res_post_venue.status_code, 401)

        res_post_closure = self.client.post(
            f'/api/venues/{self.venue1.id}/closures/',
            data=json.dumps({"start_time": "2026-10-05T10:00:00", "end_time": "2026-10-05T12:00:00"}),
            content_type='application/json'
        )
        self.assertEqual(res_post_closure.status_code, 401)

        # 5. 建立一筆已核准預約與一筆待審核預約
        now = timezone.now()
        approved_res = Reservation.objects.create(
            user=self.applicant,
            venue=self.venue1,
            start_time=now + timedelta(days=3, hours=9),
            end_time=now + timedelta(days=3, hours=12),
            reason='公開社區共修活動',
            status=Reservation.Status.APPROVED
        )
        pending_res = Reservation.objects.create(
            user=self.applicant,
            venue=self.venue1,
            start_time=now + timedelta(days=4, hours=14),
            end_time=now + timedelta(days=4, hours=17),
            reason='待審核內部會議',
            status=Reservation.Status.PENDING
        )

        # 6. 訪客查詢場地租用資訊 -> 200，且僅回傳 APPROVED 已核准之租用排程，並對申請人做去識別化保護
        res_rentals = self.client.get('/api/reservations/')
        self.assertEqual(res_rentals.status_code, 200)
        rentals_data = res_rentals.json()
        self.assertEqual(len(rentals_data), 1)
        self.assertEqual(rentals_data[0]['id'], approved_res.id)
        self.assertEqual(rentals_data[0]['venue_name'], '大型演講廳')
        self.assertEqual(rentals_data[0]['reason'], '公開社區共修活動')
        self.assertEqual(rentals_data[0]['status'], 'APPROVED')
        self.assertTrue(rentals_data[0]['is_public_view'])
        self.assertNotIn('applicant', rentals_data[0]['username'])  # 帳號遮罩如 a***
        self.assertTrue(rentals_data[0]['username'].startswith('a***'))

        # 7. 訪客按場地篩選租用資訊
        res_filtered = self.client.get(f'/api/reservations/?venue_id={self.venue1.id}')
        self.assertEqual(res_filtered.status_code, 200)
        self.assertEqual(len(res_filtered.json()), 1)

        res_filtered_empty = self.client.get(f'/api/reservations/?venue_id={self.venue2.id}')
        self.assertEqual(res_filtered_empty.status_code, 200)
        self.assertEqual(len(res_filtered_empty.json()), 0)

        # 8. 訪客不可直接提交預約 -> 401
        res_book_unauth = self.client.post(
            '/api/reservations/',
            data=json.dumps({
                "venue_id": self.venue1.id,
                "start_time": (now + timedelta(days=5, hours=9)).isoformat(),
                "end_time": (now + timedelta(days=5, hours=12)).isoformat(),
                "reason": "未登入借用"
            }),
            content_type='application/json'
        )
        self.assertEqual(res_book_unauth.status_code, 401)

        # 9. 訪客按日期篩選租用資訊
        target_date_str = timezone.localdate(approved_res.start_time).strftime('%Y-%m-%d')
        res_date_match = self.client.get(f'/api/reservations/?date={target_date_str}')
        self.assertEqual(res_date_match.status_code, 200)
        self.assertEqual(len(res_date_match.json()), 1)

        other_date_str = (now + timedelta(days=10)).strftime('%Y-%m-%d')
        res_date_miss = self.client.get(f'/api/reservations/?date={other_date_str}')
        self.assertEqual(res_date_miss.status_code, 200)
        self.assertEqual(len(res_date_miss.json()), 0)



