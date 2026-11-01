from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserProfile(models.Model):
    """人員擴充模型（支援最高管理者、管理者、一般申請者三級角色）"""

    class Role(models.TextChoices):
        SUPERADMIN = 'SUPERADMIN', '最高管理者'
        ADMIN = 'ADMIN', '管理者'
        USER = 'USER', '一般申請者'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name="關聯使用者"
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
        verbose_name="使用者角色"
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="聯絡電話")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")

    class Meta:
        verbose_name = "人員角色"
        verbose_name_plural = "人員角色列表"
        ordering = ['id']

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def is_superadmin(self):
        return self.role == self.Role.SUPERADMIN or self.user.is_superuser

    @property
    def is_admin_or_superadmin(self):
        return (
            self.role in [self.Role.ADMIN, self.Role.SUPERADMIN]
            or self.user.is_superuser
            or self.user.is_staff
        )


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """當 User 建立或儲存時，自動同步建立或維護 UserProfile"""
    if created:
        if instance.is_superuser:
            role = UserProfile.Role.SUPERADMIN
        elif instance.is_staff:
            role = UserProfile.Role.ADMIN
        else:
            role = UserProfile.Role.USER
        UserProfile.objects.create(user=instance, role=role)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()


class Venue(models.Model):
    """場地模型（支援管理者進行 ACID 交易操作與限定時段停用）"""
    name = models.CharField(max_length=100, verbose_name="場地名稱")
    capacity = models.PositiveIntegerField(
        validators=[MinValueValidator(1, message="場地容納人數至少為 1 人")],
        verbose_name="容納人數"
    )
    location = models.CharField(max_length=100, verbose_name="場地位址")
    description = models.TextField(blank=True, verbose_name="場地設備與說明")
    is_active = models.BooleanField(default=True, verbose_name="是否開放借用 (全局開關)")
    created_at = models.DateTimeField(auto_now_add=True, null=True, verbose_name="建立時間")
    updated_at = models.DateTimeField(auto_now=True, null=True, verbose_name="最後更新時間")

    class Meta:
        verbose_name = "場地"
        verbose_name_plural = "場地列表"
        ordering = ['id']

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({'name': "場地名稱不可為空白。"})
        if not self.location or not self.location.strip():
            raise ValidationError({'location': "場地位址不可為空白。"})
        if self.capacity is None or self.capacity < 1:
            raise ValidationError({'capacity': "場地容納人數必須大於 0。"})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def check_availability(self, start_time, end_time):
        """檢查特定時段是否開放（驗證全面停用與限定時段停用）"""
        if not self.is_active:
            raise ValidationError("該場地目前已全面暫停借用。")

        conflicting_closure = self.closures.filter(
            start_time__lt=end_time,
            end_time__gt=start_time
        ).first()

        if conflicting_closure:
            tz = timezone.get_current_timezone()
            s_str = conflicting_closure.start_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')
            e_str = conflicting_closure.end_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')
            reason_text = f"（事由：{conflicting_closure.reason}）" if conflicting_closure.reason else ""
            raise ValidationError(
                f"該場地於此時段已設定限定停用{reason_text}，停用期間：{s_str} 至 {e_str}。"
            )

    def __str__(self):
        return f"{self.name} ({self.location} - 容納 {self.capacity} 人)"


class VenueClosure(models.Model):
    """場地限定時段停用模型 (支援預排維護、消毒清潔或特定時段暫停借用)"""
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name='closures',
        verbose_name="所屬場地"
    )
    start_time = models.DateTimeField(db_index=True, verbose_name="停用開始時間")
    end_time = models.DateTimeField(db_index=True, verbose_name="停用結束時間")
    reason = models.CharField(max_length=200, blank=True, default="設備維護", verbose_name="停用事由")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="設定時間")

    class Meta:
        verbose_name = "場地停用時段"
        verbose_name_plural = "場地停用時段列表"
        ordering = ['start_time']

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': "停用結束時間必須晚於開始時間。"})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.venue.name} 停用 ({self.start_time} ~ {self.end_time})"


class Reservation(models.Model):
    """預約紀錄模型"""

    class Status(models.TextChoices):
        PENDING = 'PENDING', '待審核'
        APPROVED = 'APPROVED', '已核准'
        REJECTED = 'REJECTED', '已駁回'
        CANCELLED = 'CANCELLED', '已取消'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name="借用人"
    )
    venue = models.ForeignKey(
        Venue,
        on_delete=models.PROTECT,
        related_name='reservations',
        verbose_name="借用場地"
    )
    start_time = models.DateTimeField(db_index=True, verbose_name="借用開始時間")
    end_time = models.DateTimeField(db_index=True, verbose_name="借用結束時間")
    reason = models.TextField(blank=True, verbose_name="借用事由")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="預約狀態"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="申請時間")

    class Meta:
        verbose_name = "預約紀錄"
        verbose_name_plural = "預約紀錄列表"
        ordering = ['-start_time']

    def clean(self):
        super().clean()

        # 1. 驗證 start_time 必須早於 end_time
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': "借用結束時間必須晚於開始時間。"})

            # 2. 檢查場地可用性（驗證是否處於全面停用或限定時段停用）
            if self.venue_id:
                self.venue.check_availability(self.start_time, self.end_time)

            # 3. 防衝堂檢查：同一場地在狀態為 APPROVED 的情況下，時間區間不可重疊
            if self.venue_id and self.status == self.Status.APPROVED:
                conflicts = Reservation.objects.filter(
                    venue=self.venue,
                    status=self.Status.APPROVED,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time
                )
                if self.pk:
                    conflicts = conflicts.exclude(pk=self.pk)

                if conflicts.exists():
                    raise ValidationError("該時段此場地已有已核准的預約，時間區間不可重疊（防衝堂）。")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.venue.name} - {self.user.username} ({self.get_status_display()})"
