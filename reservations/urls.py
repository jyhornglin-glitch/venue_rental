from django.urls import path
from . import views

urlpatterns = [
    # 首頁 Web UI
    path('', views.index_view, name='index'),

    # 認證 API
    path('api/auth/login/', views.auth_login_api, name='api_login'),
    path('api/auth/logout/', views.auth_logout_api, name='api_logout'),
    path('api/auth/me/', views.auth_me_api, name='api_me'),

    # 場地 CRUD (支援管理者 ACID 操作與限定時段停用)
    path('api/venues/', views.venue_list_create_api, name='api_venues'),
    path('api/venues/<int:pk>/', views.venue_detail_api, name='api_venue_detail'),
    path('api/venues/<int:venue_id>/closures/', views.venue_closure_list_create_api, name='api_venue_closures'),
    path('api/venues/<int:venue_id>/closures/<int:closure_id>/', views.venue_closure_delete_api, name='api_venue_closure_delete'),

    # 預約業務 API
    path('api/reservations/', views.reservation_list_create_api, name='api_reservations'),
    path('api/reservations/<int:pk>/', views.reservation_detail_patch_api, name='api_reservation_detail'),

    # 人員角色管理 API (最高管理者/管理者)
    path('api/users/', views.user_list_create_api, name='api_users'),
    path('api/users/<int:pk>/role/', views.user_role_update_api, name='api_user_role_update'),
]
