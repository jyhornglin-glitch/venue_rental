import json
import base64
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction, models
from .models import Venue, Reservation, UserProfile, VenueClosure


def get_authenticated_user(request):
    """
    取得已驗證使用者。支援 Session Cookie 與 Basic Auth。
    """
    if request.user.is_authenticated:
        return request.user

    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Basic '):
        try:
            auth_decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = auth_decoded.split(':', 1)
            user = authenticate(request, username=username, password=password)
            if user and user.is_active:
                return user
        except Exception:
            return None
    return None


def get_user_role_info(user):
    """取得使用者角色資訊（最高管理者、管理者、一般申請者）"""
    if not user or not user.is_authenticated:
        return {
            'role': None,
            'role_display': '訪客',
            'is_superadmin': False,
            'is_admin': False,
            'is_admin_or_superadmin': False
        }

    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'role': UserProfile.Role.SUPERADMIN if user.is_superuser else (
                UserProfile.Role.ADMIN if user.is_staff else UserProfile.Role.USER
            )
        }
    )

    is_superadmin = profile.is_superadmin
    is_admin_or_super = profile.is_admin_or_superadmin
    is_admin = is_admin_or_super and not is_superadmin

    return {
        'role': profile.role,
        'role_display': profile.get_role_display(),
        'is_superadmin': is_superadmin,
        'is_admin': is_admin,
        'is_admin_or_superadmin': is_admin_or_super
    }


def index_view(request):
    """根路徑 (/) 頁面渲染"""
    return render(request, 'index.html', {
        'current_user': request.user
    })


@csrf_exempt
@require_http_methods(["POST"])
def auth_login_api(request):
    """POST /api/auth/login/ 使用者登入"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        username = data.get('username')
        password = data.get('password')
    except Exception:
        return JsonResponse({'detail': '無效的請求格式'}, status=400)

    user = authenticate(request, username=username, password=password)
    if user and user.is_active:
        login(request, user)
        role_info = get_user_role_info(user)
        return JsonResponse({
            'detail': '登入成功',
            'user': {
                'id': user.id,
                'username': user.username,
                **role_info
            }
        }, status=200)
    return JsonResponse({'detail': '帳號或密碼錯誤'}, status=401)


@csrf_exempt
@require_http_methods(["POST"])
def auth_logout_api(request):
    """POST /api/auth/logout/ 使用者登出"""
    logout(request)
    return JsonResponse({'detail': '已登出'}, status=200)


@require_http_methods(["GET"])
def auth_me_api(request):
    """GET /api/auth/me/ 取得當前使用者角色與身分"""
    if request.user.is_authenticated:
        role_info = get_user_role_info(request.user)
        return JsonResponse({
            'is_authenticated': True,
            'id': request.user.id,
            'username': request.user.username,
            **role_info
        })
    return JsonResponse({
        'is_authenticated': False,
        'id': None,
        'username': '',
        'role': None,
        'role_display': '未登入',
        'is_superadmin': False,
        'is_admin': False,
        'is_admin_or_superadmin': False
    })


# -------------------------------------------------------------
# 場地管理 API（支援管理者 ACID 交易操作）
# -------------------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "POST"])
def venue_list_create_api(request):
    """
    GET /api/venues/ - 查詢場地（一般人與訪客查開放中，管理者支援查全部）
    POST /api/venues/ - 新增場地（管理者專屬，具備 ACID 交易保證）
    """
    user = get_authenticated_user(request)
    role_info = get_user_role_info(user) if user else {
        'role': None,
        'role_display': '訪客',
        'is_superadmin': False,
        'is_admin': False,
        'is_admin_or_superadmin': False
    }

    if request.method == "GET":
        manage_mode = request.GET.get('manage') in ('1', 'true', 'all')
        if manage_mode:
            if not role_info['is_admin_or_superadmin']:
                return JsonResponse({"detail": "僅管理者可檢視完整場地管理清單。"}, status=403)
            venues = Venue.objects.all().prefetch_related('closures')
        else:
            venues = Venue.objects.filter(is_active=True).prefetch_related('closures')

        now = timezone.now()
        data = []
        for v in venues:
            active_closures = list(v.closures.all().order_by('start_time'))
            is_closed_now = (not v.is_active) or any(c.start_time <= now <= c.end_time for c in active_closures)
            current_closure = next((c for c in active_closures if c.start_time <= now <= c.end_time), None)

            data.append({
                "id": v.id,
                "name": v.name,
                "capacity": v.capacity,
                "location": v.location,
                "description": v.description,
                "is_active": v.is_active,
                "is_closed_now": is_closed_now,
                "current_closure_reason": current_closure.reason if current_closure else ("全面暫停借用" if not v.is_active else None),
                "closures": [
                    {
                        "id": c.id,
                        "start_time": c.start_time.isoformat(),
                        "end_time": c.end_time.isoformat(),
                        "reason": c.reason
                    }
                    for c in active_closures
                ],
                "created_at": v.created_at.isoformat() if v.created_at else None,
            })
        return JsonResponse(data, safe=False, status=200)

    # POST: 建立場地 (ACID 交易操作)
    if request.method == "POST":
        if not user:
            return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)
        if not role_info['is_admin_or_superadmin']:
            return JsonResponse({"detail": "權限不足，僅管理者可新增場地。"}, status=403)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({"detail": "無效的 JSON 請求主體。"}, status=400)

        name = payload.get("name", "").strip()
        location = payload.get("location", "").strip()
        capacity = payload.get("capacity")
        description = payload.get("description", "").strip()
        is_active = payload.get("is_active", True)

        try:
            # 使用 transaction.atomic() 保障 Atomicity 與 Isolation
            with transaction.atomic():
                venue = Venue(
                    name=name,
                    location=location,
                    capacity=int(capacity) if capacity is not None else None,
                    description=description,
                    is_active=bool(is_active)
                )
                venue.full_clean()
                venue.save()
        except (ValueError, TypeError):
            return JsonResponse({"detail": "容納人數必須為有效整數。"}, status=400)
        except ValidationError as e:
            error_message = e.message_dict if hasattr(e, 'message_dict') else e.messages
            return JsonResponse({"detail": "場地資料驗證失敗", "errors": error_message}, status=400)
        except Exception as e:
            return JsonResponse({"detail": f"伺服器錯誤: {str(e)}"}, status=500)

        return JsonResponse({
            "id": venue.id,
            "name": venue.name,
            "capacity": venue.capacity,
            "location": venue.location,
            "description": venue.description,
            "is_active": venue.is_active,
            "message": "場地建立成功（ACID 交易已提交）。"
        }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def venue_detail_api(request, pk):
    """
    GET /api/venues/<pk>/ - 查詢單一場地 (支援訪客公開查詢)
    PUT/PATCH /api/venues/<pk>/ - 更新場地（管理者專屬，ACID 交易保證）
    DELETE /api/venues/<pk>/ - 刪除場地（管理者專屬，ACID 交易與關聯完整性保護）
    """
    user = get_authenticated_user(request)
    role_info = get_user_role_info(user) if user else {
        'role': None,
        'role_display': '訪客',
        'is_superadmin': False,
        'is_admin': False,
        'is_admin_or_superadmin': False
    }

    try:
        venue = Venue.objects.get(pk=pk)
    except Venue.DoesNotExist:
        return JsonResponse({"detail": f"找不到編號為 {pk} 的場地。"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": venue.id,
            "name": venue.name,
            "capacity": venue.capacity,
            "location": venue.location,
            "description": venue.description,
            "is_active": venue.is_active,
        }, status=200)

    # 僅管理者與最高管理者可進行 Update / Delete
    if not user:
        return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)

    if not role_info['is_admin_or_superadmin']:
        return JsonResponse({"detail": "權限不足，僅管理者可異動或刪除場地。"}, status=403)

    # UPDATE (PUT / PATCH)
    if request.method in ["PUT", "PATCH"]:
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({"detail": "無效的 JSON 請求主體。"}, status=400)

        try:
            with transaction.atomic():
                if "name" in payload:
                    venue.name = str(payload["name"]).strip()
                if "location" in payload:
                    venue.location = str(payload["location"]).strip()
                if "capacity" in payload:
                    venue.capacity = int(payload["capacity"])
                if "description" in payload:
                    venue.description = str(payload["description"]).strip()
                if "is_active" in payload:
                    venue.is_active = bool(payload["is_active"])

                venue.full_clean()
                venue.save()
        except (ValueError, TypeError):
            return JsonResponse({"detail": "容納人數必須為有效整數。"}, status=400)
        except ValidationError as e:
            error_message = e.message_dict if hasattr(e, 'message_dict') else e.messages
            return JsonResponse({"detail": "場地更新驗證失敗", "errors": error_message}, status=400)
        except Exception as e:
            return JsonResponse({"detail": f"交易失敗: {str(e)}"}, status=500)

        return JsonResponse({
            "id": venue.id,
            "name": venue.name,
            "capacity": venue.capacity,
            "location": venue.location,
            "description": venue.description,
            "is_active": venue.is_active,
            "message": "場地資訊已成功更新（ACID 交易已提交）。"
        }, status=200)

    # DELETE
    if request.method == "DELETE":
        try:
            with transaction.atomic():
                venue.delete()
        except models.ProtectedError:
            return JsonResponse({
                "detail": "無法刪除：該場地已有相關預約紀錄。為維護資料完整性，請將該場地設為「停用（不開放）」替代刪除。"
            }, status=400)
        except Exception as e:
            return JsonResponse({"detail": f"刪除交易失敗: {str(e)}"}, status=500)

        return JsonResponse({"detail": f"場地 #{pk} 已成功刪除（ACID 交易已持久化）。"}, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def venue_closure_list_create_api(request, venue_id):
    """
    GET /api/venues/<venue_id>/closures/ - 查詢特定場地的停用時段列表 (公開查詢)
    POST /api/venues/<venue_id>/closures/ - 設定限定時段停用 (管理者/最高管理者，ACID 交易操作)
    """
    user = get_authenticated_user(request)
    role_info = get_user_role_info(user) if user else {
        'role': None,
        'role_display': '訪客',
        'is_superadmin': False,
        'is_admin': False,
        'is_admin_or_superadmin': False
    }

    try:
        venue = Venue.objects.get(pk=venue_id)
    except Venue.DoesNotExist:
        return JsonResponse({"detail": f"找不到編號為 {venue_id} 的場地。"}, status=404)

    if request.method == "GET":
        closures = venue.closures.all().order_by('start_time')
        data = [
            {
                "id": c.id,
                "venue_id": c.venue_id,
                "start_time": c.start_time.isoformat(),
                "end_time": c.end_time.isoformat(),
                "reason": c.reason,
                "created_at": c.created_at.isoformat()
            }
            for c in closures
        ]
        return JsonResponse(data, safe=False, status=200)

    if request.method == "POST":
        if not user:
            return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)
        if not role_info['is_admin_or_superadmin']:
            return JsonResponse({"detail": "權限不足，僅管理者可設定限定停用時段。"}, status=403)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({"detail": "無效的 JSON 請求格式。"}, status=400)

        start_time_raw = payload.get("start_time")
        end_time_raw = payload.get("end_time")
        reason = payload.get("reason", "").strip() or "設備維護"

        if not start_time_raw or not end_time_raw:
            return JsonResponse({"detail": "停用開始時間與結束時間為必填欄位。"}, status=400)

        start_time = parse_datetime(str(start_time_raw))
        end_time = parse_datetime(str(end_time_raw))

        if not start_time or not end_time:
            return JsonResponse({"detail": "無效的時間格式。"}, status=400)

        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time)

        try:
            with transaction.atomic():
                closure = VenueClosure(
                    venue=venue,
                    start_time=start_time,
                    end_time=end_time,
                    reason=reason
                )
                closure.full_clean()
                closure.save()
        except ValidationError as e:
            error_message = e.message_dict if hasattr(e, 'message_dict') else e.messages
            return JsonResponse({"detail": "停用時段驗證失敗", "errors": error_message}, status=400)
        except Exception as e:
            return JsonResponse({"detail": f"交易失敗: {str(e)}"}, status=500)

        return JsonResponse({
            "id": closure.id,
            "venue_id": closure.venue_id,
            "start_time": closure.start_time.isoformat(),
            "end_time": closure.end_time.isoformat(),
            "reason": closure.reason,
            "message": f"已成功為場地「{venue.name}」設定限定停用時段（{closure.reason}）。"
        }, status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def venue_closure_delete_api(request, venue_id, closure_id):
    """
    DELETE /api/venues/<venue_id>/closures/<closure_id>/ - 移除限定停用時段 (恢復該時段借用)
    """
    user = get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)

    role_info = get_user_role_info(user)
    if not role_info['is_admin_or_superadmin']:
        return JsonResponse({"detail": "權限不足，僅管理者可移除停用時段。"}, status=403)

    try:
        closure = VenueClosure.objects.get(pk=closure_id, venue_id=venue_id)
    except VenueClosure.DoesNotExist:
        return JsonResponse({"detail": f"找不到指定編號 #{closure_id} 的停用時段紀錄。"}, status=404)

    try:
        with transaction.atomic():
            closure.delete()
    except Exception as e:
        return JsonResponse({"detail": f"移除失敗: {str(e)}"}, status=500)

    return JsonResponse({"detail": "已成功解除該時段之停用設定，場地恢復借用。"}, status=200)


# -------------------------------------------------------------
# 預約業務 API
# -------------------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "POST"])
def reservation_list_create_api(request):
    """
    GET /api/reservations/ - 依權限查詢預約清單 (未登入訪客可查詢場地租用資訊/已核准借用排程)
    POST /api/reservations/ - 提交新增預約 (需登入)
    """
    user = get_authenticated_user(request)
    role_info = get_user_role_info(user) if user else {
        'role': None,
        'role_display': '訪客',
        'is_superadmin': False,
        'is_admin': False,
        'is_admin_or_superadmin': False
    }

    if request.method == "GET":
        venue_id = request.GET.get('venue_id')
        scope = request.GET.get('scope')  # 'all', 'public', 'my', 'approved', 'pending'
        date_str = request.GET.get('date')  # 'YYYY-MM-DD'

        def apply_query_filters(qs):
            if venue_id:
                qs = qs.filter(venue_id=venue_id)
            if date_str:
                try:
                    from datetime import datetime
                    q_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    qs = qs.filter(
                        start_time__date__lte=q_date,
                        end_time__date__gte=q_date
                    )
                except ValueError:
                    pass
            return qs

        # 1. 未登入使用者 (訪客)：回傳公開場地租用資訊 (已核准之租用排程)
        if not user:
            reservations = Reservation.objects.filter(
                status=Reservation.Status.APPROVED
            ).select_related('venue', 'user')
            reservations = apply_query_filters(reservations)

            data = [
                {
                    "id": r.id,
                    "venue_id": r.venue_id,
                    "venue_name": r.venue.name,
                    "user_id": None,
                    "username": (r.user.username[0] + "***") if r.user.username else "志工大德",
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat(),
                    "reason": r.reason,
                    "status": r.status,
                    "status_display": r.get_status_display(),
                    "created_at": r.created_at.isoformat(),
                    "is_mine": False,
                    "is_public_view": True,
                }
                for r in reservations
            ]
            return JsonResponse(data, safe=False, status=200)

        # 2. 已登入使用者
        if role_info['is_admin_or_superadmin']:
            reservations = Reservation.objects.all().select_related('venue', 'user')
            if scope == 'approved':
                reservations = reservations.filter(status=Reservation.Status.APPROVED)
            elif scope == 'pending':
                reservations = reservations.filter(status=Reservation.Status.PENDING)
            reservations = apply_query_filters(reservations)
        else:
            # 一般申請者
            if scope in ('all', 'public'):
                # 檢視全道場場地借用現況 (已核准的租用 + 自己的申請)
                reservations = Reservation.objects.filter(
                    models.Q(status=Reservation.Status.APPROVED) | models.Q(user=user)
                ).select_related('venue', 'user')
            else:
                # 預設看自己的預約紀錄
                reservations = Reservation.objects.filter(user=user).select_related('venue', 'user')
            reservations = apply_query_filters(reservations)

        data = [
            {
                "id": r.id,
                "venue_id": r.venue_id,
                "venue_name": r.venue.name,
                "user_id": r.user_id,
                "username": r.user.username if (role_info['is_admin_or_superadmin'] or r.user_id == user.id) else ((r.user.username[0] + "***") if r.user.username else "志工大德"),
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat(),
                "reason": r.reason,
                "status": r.status,
                "status_display": r.get_status_display(),
                "created_at": r.created_at.isoformat(),
                "is_mine": (r.user_id == user.id),
                "is_public_view": False,
            }
            for r in reservations
        ]
        return JsonResponse(data, safe=False, status=200)

    if request.method == "POST":
        if not user:
            return JsonResponse({"detail": "未授權存取，請先登入後再進行預約。"}, status=401)
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"detail": "無效的 JSON 請求主體。"}, status=400)

        venue_id = payload.get("venue_id")
        start_time_raw = payload.get("start_time")
        end_time_raw = payload.get("end_time")
        reason = payload.get("reason", "").strip()

        if not venue_id or not start_time_raw or not end_time_raw:
            return JsonResponse({
                "detail": "缺少必要欄位：venue_id, start_time, end_time 為必填。"
            }, status=400)

        try:
            venue = Venue.objects.get(id=venue_id, is_active=True)
        except Venue.DoesNotExist:
            return JsonResponse({"detail": "指定的場地不存在或未開放借用。"}, status=404)

        start_time = parse_datetime(str(start_time_raw))
        end_time = parse_datetime(str(end_time_raw))

        if not start_time or not end_time:
            return JsonResponse({"detail": "時間格式錯誤，請提供正確的時間字串。"}, status=400)

        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time)

        try:
            with transaction.atomic():
                reservation = Reservation(
                    user=user,
                    venue=venue,
                    start_time=start_time,
                    end_time=end_time,
                    reason=reason,
                    status=Reservation.Status.PENDING
                )
                reservation.full_clean()
                reservation.save()
        except ValidationError as e:
            error_message = e.message_dict if hasattr(e, 'message_dict') else e.messages
            return JsonResponse({"detail": "驗證失敗", "errors": error_message}, status=400)
        except Exception as e:
            return JsonResponse({"detail": f"伺服器處理錯誤: {str(e)}"}, status=500)

        return JsonResponse({
            "id": reservation.id,
            "venue_id": reservation.venue.id,
            "venue_name": reservation.venue.name,
            "user_id": reservation.user.id,
            "username": reservation.user.username,
            "start_time": reservation.start_time.isoformat(),
            "end_time": reservation.end_time.isoformat(),
            "reason": reservation.reason,
            "status": reservation.status,
            "status_display": reservation.get_status_display(),
            "created_at": reservation.created_at.isoformat(),
            "message": "預約申請已成功提交。"
        }, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
def reservation_detail_patch_api(request, pk):
    """
    PATCH /api/reservations/<id>/ 更新預約狀態
    """
    user = get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)

    role_info = get_user_role_info(user)

    try:
        reservation = Reservation.objects.select_related('venue', 'user').get(pk=pk)
    except Reservation.DoesNotExist:
        return JsonResponse({"detail": f"找不到 ID 為 {pk} 的預約紀錄。"}, status=404)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({"detail": "無效的 JSON 請求主體。"}, status=400)

    target_status = payload.get("status")
    if not target_status:
        return JsonResponse({"detail": "缺少 status 欄位。"}, status=400)

    # 權限判定 (RBAC)
    if role_info['is_admin_or_superadmin']:
        if target_status not in [Reservation.Status.APPROVED, Reservation.Status.REJECTED, Reservation.Status.CANCELLED]:
            return JsonResponse({
                "detail": "管理者僅能將狀態更新為 APPROVED, REJECTED 或 CANCELLED。"
            }, status=403)
    else:
        if reservation.user_id != user.id:
            return JsonResponse({"detail": "您無權修改他人的預約紀錄。"}, status=403)

        if target_status != Reservation.Status.CANCELLED:
            return JsonResponse({"detail": "一般借用人僅能將預約狀態更新為 CANCELLED。"}, status=403)

    reservation.status = target_status

    try:
        with transaction.atomic():
            reservation.full_clean()
            reservation.save()
    except ValidationError as e:
        error_message = e.message_dict if hasattr(e, 'message_dict') else e.messages
        return JsonResponse({"detail": "狀態變更失敗", "errors": error_message}, status=400)
    except Exception as e:
        return JsonResponse({"detail": f"伺服器處理錯誤: {str(e)}"}, status=500)

    return JsonResponse({
        "id": reservation.id,
        "venue_id": reservation.venue_id,
        "venue_name": reservation.venue.name,
        "user_id": reservation.user_id,
        "username": reservation.user.username,
        "start_time": reservation.start_time.isoformat(),
        "end_time": reservation.end_time.isoformat(),
        "reason": reservation.reason,
        "status": reservation.status,
        "status_display": reservation.get_status_display(),
        "created_at": reservation.created_at.isoformat(),
        "message": f"預約狀態已更新為 {reservation.get_status_display()}。"
    }, status=200)


# -------------------------------------------------------------
# 人員管理 API (最高管理者 / 管理者)
# -------------------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_list_create_api(request):
    """
    GET /api/users/ - 檢視人員清單與角色 (管理者與最高管理者)
    POST /api/users/ - 新增人員並設定角色 (最高管理者專屬)
    """
    user = get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)

    role_info = get_user_role_info(user)

    if request.method == "GET":
        if not role_info['is_admin_or_superadmin']:
            return JsonResponse({"detail": "權限不足，僅管理者可查看人員名冊。"}, status=403)

        users = User.objects.all().select_related('profile').order_by('id')
        data = []
        for u in users:
            u_role = get_user_role_info(u)
            data.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u_role['role'],
                "role_display": u_role['role_display'],
                "is_active": u.is_active,
                "date_joined": u.date_joined.isoformat()
            })
        return JsonResponse(data, safe=False, status=200)

    # POST: 新增人員 (僅最高管理者 SUPERADMIN 可執行)
    if request.method == "POST":
        if not role_info['is_superadmin']:
            return JsonResponse({"detail": "權限不足，僅最高管理者可建立新使用者與指派角色。"}, status=403)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({"detail": "無效的 JSON 請求格式。"}, status=400)

        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        email = str(payload.get("email", "")).strip()
        phone = str(payload.get("phone", "")).strip()
        role = payload.get("role", UserProfile.Role.USER)

        if not username:
            return JsonResponse({"detail": "使用者帳號 (username) 不可為空白。"}, status=400)

        if not password:
            return JsonResponse({"detail": "使用者密碼 (password) 不可為空白。"}, status=400)

        if len(password) < 4:
            return JsonResponse({"detail": "密碼長度至少需 4 個字元。"}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"detail": f"帳號「{username}」已存在，請使用其他帳號名稱。"}, status=400)

        if role not in [UserProfile.Role.SUPERADMIN, UserProfile.Role.ADMIN, UserProfile.Role.USER]:
            return JsonResponse({"detail": "無效的角色選項。"}, status=400)

        try:
            with transaction.atomic():
                is_staff = (role in [UserProfile.Role.ADMIN, UserProfile.Role.SUPERADMIN])
                is_superuser = (role == UserProfile.Role.SUPERADMIN)

                new_user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email
                )
                new_user.is_staff = is_staff
                new_user.is_superuser = is_superuser
                new_user.save()

                profile, _ = UserProfile.objects.get_or_create(user=new_user)
                profile.role = role
                profile.phone = phone
                profile.save()
        except Exception as e:
            return JsonResponse({"detail": f"建立人員失敗: {str(e)}"}, status=500)

        return JsonResponse({
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": profile.role,
            "role_display": profile.get_role_display(),
            "message": f"人員「{new_user.username}」已成功建立，角色為：{profile.get_role_display()}。"
        }, status=201)


@csrf_exempt
@require_http_methods(["PATCH"])
def user_role_update_api(request, pk):
    """
    PATCH /api/users/<pk>/role/ - 變更人員角色
    權限：最高管理者專屬 (SUPERADMIN)
    """
    user = get_authenticated_user(request)
    if not user:
        return JsonResponse({"detail": "未授權存取，請先登入。"}, status=401)

    role_info = get_user_role_info(user)
    if not role_info['is_superadmin']:
        return JsonResponse({"detail": "權限不足，僅最高管理者可指派與變更角色。"}, status=403)

    try:
        target_user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return JsonResponse({"detail": f"找不到使用者 #{pk}。"}, status=404)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({"detail": "無效的 JSON 請求主體。"}, status=400)

    new_role = payload.get("role")
    if new_role not in [UserProfile.Role.SUPERADMIN, UserProfile.Role.ADMIN, UserProfile.Role.USER]:
        return JsonResponse({"detail": "無效的角色選項。"}, status=400)

    try:
        with transaction.atomic():
            profile, _ = UserProfile.objects.get_or_create(user=target_user)
            profile.role = new_role
            profile.save()

            # 同步更新 Django 內建權限旗標
            if new_role == UserProfile.Role.SUPERADMIN:
                target_user.is_superuser = True
                target_user.is_staff = True
            elif new_role == UserProfile.Role.ADMIN:
                target_user.is_superuser = False
                target_user.is_staff = True
            else:
                target_user.is_superuser = False
                target_user.is_staff = False
            target_user.save()
    except Exception as e:
        return JsonResponse({"detail": f"變更失敗: {str(e)}"}, status=500)

    return JsonResponse({
        "id": target_user.id,
        "username": target_user.username,
        "new_role": new_role,
        "new_role_display": profile.get_role_display(),
        "message": f"已成功將 {target_user.username} 的角色變更為 {profile.get_role_display()}。"
    }, status=200)
